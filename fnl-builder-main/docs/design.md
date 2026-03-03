# fnl-builder 設計方針ドキュメント

> **注意**: 本ドキュメントは初期設計時の記録です。実装の真実源は `docs/dev-spec.md` を参照してください。
> ファイル名・シグネチャ等の詳細は実装と乖離している場合があります。

## 目的
fnl-mockのPR #154-184のリファクタリングで得た知見を踏まえ、ゼロから設計し直す。
既に解消された問題（モジュール分割、テスト分割、C901、import境界）は前提とし、
**残存する3つの根本問題**に集中する。

---

## 現状分析（fnl-mock PR #184時点）

### 解消済み（新設計でも継承する成果）
- モジュール分割: 45ファイル、各500行以下
- テスト分割: 70+ファイル、ドメイン別に整理
- C901: baseline許容ゼロ
- import境界: private import guardで防止
- ファサード: 純粋なre-exportに限定
- models.py: 7モデル中6つがtyped dataclass

### 残存する根本問題

| # | 問題 | 深刻度 | 影響 |
|---|---|---|---|
| 1 | **Callable注入の爆発** | Critical | 32引数関数、13+個のCallable、型ヒントなし |
| 2 | **dict[str, Any]の蔓延** | High | 205箇所、LLMItem型定義なし |
| 3 | **エラー処理の混在** | Medium | SystemExit 17箇所 + issues.append 46箇所が混在 |

補足:
- collapse_ws重複（12箇所）は低優先度。import cycle回避の側面もある
- ファサード負債は新リポでは発生しない（後方互換不要）

---

## 1. パイプラインの流れ

### 現状（fnl-mock）
```
orchestrator → orchestrator_io → orchestrator_integrate → orchestrator_integrate_flow
  → guest_integration_flow → guest_integration_rewrite
```
分割は進んだが、委譲チェーンが深く、各層が13+個のCallableを中継している。

### 新設計
```
CLI → Pipeline → [Stage1: Parse] → [Stage2: Integrate] → [Stage3: Render]
```

3ステージの線形パイプライン。ステージ間はtyped dataclassでデータを受け渡す。

```python
@dataclass(frozen=True)
class ParseResult:
    rooming: RoomingData                    # 必須 — 欠損時はParseErrorで停止
    passenger: PassengerData               # 欠損時はIssue記録して空インスタンス（PassengerData.empty()）
    messagelist: MessageListData           # 欠損時はIssue記録して空インスタンス（MessageListData.empty()）
    tour_header: TourHeaderData

@dataclass(frozen=True)
class IntegrationResult:
    guests: list[GuestRecord]
    stats: RewriteStats
    # issuesはRunStateに一本化。IntegrationResultには持たない

@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    audit: AuditLog
```

```python
def run(config: PipelineConfig) -> RenderResult:
    state = RunState.from_config(config)
    parsed = parse_stage(state)
    integrated = integrate_stage(parsed, state)
    return render_stage(integrated, state)
```

---

## 2. 依存注入（根本問題 #1 の解決）

### 現状の問題
```python
# orchestrator_integrate_flow._process_extracted_files に渡される引数（31個）
def _process_extracted_files(
    *, rl_text, pl_text, ml_text, ml_text_for_llm, tpl_xlsx, out_xlsx,
    llm_provider, llm_rewrite_medical, issues, audit, guests,
    parse_rooming_list, parse_passenger_list, parse_message_list,  # Callable
    apply_tour_header_fallback,                                     # Callable
    process_merge_room_groups, process_llm_guest_remarks,           # Callable
    process_integrate_guest_data, process_post_room_grouping,       # Callable
    ...
): ...
```

### 新設計: PipelineConfig(frozen) + RunState(mutable)

```python
@dataclass(frozen=True)
class PipelineConfig:
    llm_provider: Literal["none", "openai", "mock"]
    input_mode: Literal["zip", "files"]
    input_paths: InputPaths

@dataclass
class RunState:
    config: PipelineConfig
    llm: LLMAdapter           # Protocol — テスト時はMockAdapter
    issues: list[Issue]
    audit: AuditLog
```

**Callableの注入は原則廃止**し、必要最小限のみ残す。各ステージは必要なモジュールを直接importする。
テスト時の差し替えは主に `RunState.llm`（Protocol）で行う。

```python
# Before: 13個のCallable注入
_process_extracted_files(
    parse_rooming_list=_parse_rooming_list,
    parse_passenger_list=_parse_passenger_list,
    ...
)

# After: 直接import + RunState
from fnl_builder.parse import rooming, passenger, messagelist

def integrate_stage(parsed: ParseResult, state: RunState) -> IntegrationResult:
    # rooming, passenger, messagelist は直接importされている
    # LLMだけstate.llm経由（差し替え可能）
    ...
```

### LLMAdapter Protocol

```python
class LLMAdapter(Protocol):
    def extract_remarks(self, text: str, pages: list[Page], prompts: PromptConfig) -> list[LLMItem]: ...
    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None: ...

class OpenAIAdapter:
    """OpenAI APIを使った実装"""
    ...

class MockAdapter:
    """テスト用。固定レスポンスを返す"""
    ...

class NullAdapter:
    """LLM不使用時。空リストを返す"""
    ...
```

---

## 3. データモデル（根本問題 #2 の解決）

### 現状の問題
```python
# LLMExtractionResult.by_guest の型
dict[tuple[str, str], list[dict[str, Any]]]
#                           ^^^^^^^^^^^^^^^^ スキーマ不明
```

`dict[str, Any]` が205箇所。LLMレスポンスのフィールド（category, who_id, confidence, phase, handoff_text, evidence_quote）が暗黙的。

### 新設計: 全てtyped

```python
# shared/types.py

@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning", "info"]
    code: str
    message: str

class Category(StrEnum):
    MEDICAL = "medical"
    MEAL = "meal"
    MOBILITY = "mobility"
    # ... 実装時に全カテゴリを列挙

class Phase(StrEnum):
    EXTRACT = "extract"
    REWRITE = "rewrite"
    # ... 実装時に全フェーズを列挙

@dataclass(frozen=True)
class LLMItem:
    category: Category
    who_id: str
    confidence: float
    phase: Phase
    handoff_text: str
    evidence_quote: str
    summary: str = ""

@dataclass(frozen=True)
class RewriteStats:
    candidates: int = 0
    applied: int = 0
    fallback: int = 0

@dataclass
class AuditLog:
    started_at: str
    input_mode: str
    input_files_sha256: dict[str, str]
    llm_extraction: LLMExtractionAudit | None = None
    counts: PipelineCounts = field(default_factory=PipelineCounts)
    issues: list[Issue] = field(default_factory=list)
```

**ルール**:
- `dict[str, Any]` は外部I/O境界（JSONシリアライズ/デシリアライズ）のみ
- LLM JSONレスポンスは即座に `LLMItem` に変換。変換失敗はIssue記録してスキップ
- 内部関数間のデータ受け渡しは全てtyped
- `RunState.issues` がパイプライン実行中の唯一のissue蓄積先。render stage完了時に `audit.issues = state.issues.copy()` で転記

### PII型強制

監査ログにPII（個人情報）が混入しないことを型で担保する。

```python
@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    stage: str
    event_type: str
    detail: str           # PIIを含まない要約のみ
    # NG: guest_name, phone, passport 等のフィールドは定義しない

class PIIField:
    """PIIを含むフィールドのマーカー型。AuditEventへの混入をテストで検出"""
    ...
```

- `AuditEvent` にPIIフィールドを持たせない設計とする（型レベル防御）
- `detail: str` 等の自由記述フィールドへの実データPII混入を防ぐため、AuditLog出力前にサニタイズ関数を通す（電話番号・パスポート番号等の既知パターンをマスキング）
- CIテストで (1) フィールド型にPII型が含まれないこと、(2) 実データfixture使用時に監査ログJSON内にPIIパターンが検出されないこと、の2層で検証
- 「ログはPII-Free」を型+サニタイズ+テストの3層で担保

---

## 4. エラー処理（根本問題 #3 の解決）

### 現状の問題
- `raise SystemExit` 17箇所: ファイルI/O、ZIP検証、テンプレート不在
- `issues.append({"level": ..., "code": ..., "message": ...})` 46箇所: 軽微な警告
- 混在により、どのエラーが回復可能か不明

### 新設計: 例外階層 + Issue型

```python
# shared/errors.py
class FnlError(Exception):
    """基底例外"""

class InputError(FnlError):
    """入力ファイルの問題（回復不可）"""

class ParseError(FnlError):
    """PDF/CSV解析失敗（回復不可）"""

class LLMError(FnlError):
    """LLM呼び出し失敗（フォールバックで続行）"""
```

| 状況 | 処理 |
|---|---|
| ファイルが存在しない | `raise InputError(...)` |
| PDF解析で文字化け | `raise ParseError(...)` |
| LLM APIタイムアウト | `raise LLMError(...)` → Pipeline内でcatch → rule-basedのみで続行（NullAdapter相当）+ Issue記録（level="warning", code="llm_fallback"）。リトライなし |
| PL/ML PDFが欠損 | `state.issues.append(Issue("warning", "input_missing", "..."))` → 空データで続行 |
| 枝番照合が曖昧 | `state.issues.append(Issue("warning", "branch_ambiguous", "..."))` |
| Remarks禁止語句検出 | `state.issues.append(Issue("error", "remarks_banned", "..."))` |

**CLIでの一元処理**:
```python
def main():
    try:
        result = pipeline.run(config)
    except FnlError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
```

`argparse` の usage error（必須引数不足・不正オプション・不正choice）は
CLIロジックに入る前に `SystemExit(2)` となる。
SystemExitはCLI層のみ。ライブラリとして使う場合は例外がそのまま伝播。

**Issue(level="error") の扱い**:
- error Issueは例外ではなく、パイプラインは最後まで実行する（Excel出力も行う）
- CLIは `state.issues` に level="error" が1件以上ある場合、終了メッセージ付きで失敗扱い（プロセス終了コードは1）
- exit code: 0=成功、1=アプリケーションエラー、2=usage error（argparse）

---

## 5. プロンプト管理

### 設計方針
- **共通原則**（base）は全コースで共有。変更頻度: 低
- **コース固有の抽出指示**はファイルを置くだけで追加。コード変更不要
- コース固有指示は**5-10行に制限**（多すぎると精度低下）

### ディレクトリ構成
```
llm/prompts/
  base_system.txt          # 全コース共通のシステムプロンプト
  base_extract.md          # 共通の抽出指示
  courses/
    _default.md            # コース固有ファイルがない場合
    417.md                 # E417, EH417 等（番号417系）
```

### コースコードの解決ルール

**原則: PDF内のコースコードから番号を抽出し、対応するプロンプトを適用**。
E417のPDF内にET470が記載されていれば、ET470にもE417（=417）のルールが適用される。
キャッシュや外部状態は不要 — PDF内容を見れば実行時に判定できる。

```
Step 1: PDF内のコースコードを抽出（E417, ET470, EH417...）
Step 2: プレフィックス（英字1-2文字）を除去し末尾の連続数字を抽出
        例: E417→417, ET470→470, EH417→417
Step 3: 各番号の courses/XXX.md を探す → 見つかったものを番号昇順で連結（重複行除去）
        _default.md は併用しない（1つでもcoursesファイルがあれば_defaultは使わない）
Step 4: どの番号にも該当ファイルがなければ → courses/_default.md
```

### データ型

```python
@dataclass(frozen=True)
class PromptConfig:
    system: str              # base_system.txt
    extract_base: str        # base_extract.md
    course_supplement: str   # courses/417.md 等

class LLMAdapter(Protocol):
    def extract_remarks(
        self, text: str, pages: list[Page], prompts: PromptConfig
    ) -> list[LLMItem]: ...
```

### コース固有ファイルの例（courses/417.md）
```markdown
## コース固有の抽出事項
- シェンゲン協定圏のビザ要件に関する記載を重点抽出
- 複数都市移動のため離団・合流の記載に注意
- 現地ガイドの言語対応に関する記載を抽出
```

### 運用
- 新コースの追加: `courses/XXX.md` ファイルを置くだけ
- 番号違いの同一コース（例: E417とET470）: 同一PDF内に両方記載されていれば自動で同じルール適用。手動設定不要
- プロンプトのバージョン管理: gitで追跡可能
- 処理速度への影響: コース固有指示は数百トークン。入力テキスト（数千〜数万トークン）の1%以下で無視できる
- 外部状態（キャッシュ/DB）不要: 実行時にPDF内容から判定するためステートレス

---

## 6. モジュール構成（全体図）

```
src/
  fnl_builder/
    __init__.py
    cli.py                    # CLI → PipelineConfig
    pipeline.py               # 3ステージオーケストレーション
    config.py                 # PipelineConfig, InputPaths

    parse/                    # Stage 1
      __init__.py
      rooming.py              # RoomingList PDF解析
      passenger.py            # PassengerList PDF解析
      messagelist.py          # MessageList rule-based解析
      messagelist_rules.py    # カテゴリ分類ルール
      messagelist_companion.py # 同行者グループ
      tour_header.py          # ツアーヘッダー抽出
      input_extract.py        # PDF/CSVテキスト抽出

    integrate/                # Stage 2
      __init__.py
      guest_builder.py        # ゲスト統合メインロジック
      remark_rewrite.py       # remarks書き換え
      vip.py                  # VIP判定・汎化
      category.py             # カテゴリ精緻化
      room_merge.py           # 部屋マージ統合
      room_sharing.py         # 同室備考
      p_markers.py            # Pマーカー再割当

    resolve/                  # 横断的な解決ロジック
      who_id.py               # who_id → inquiry解決
      inquiry_match.py        # 枝番照合

    llm/                      # LLMアダプター層
      __init__.py
      adapter.py              # LLMAdapter Protocol
      openai.py               # OpenAI実装
      mock.py                 # テスト用
      extraction.py           # LLM抽出オーケストレーション
      prompt_loader.py        # プロンプト読み込み・組み立て
      prompts/                # プロンプトテンプレート
        base_system.txt       # 全コース共通の原則
        base_extract.md       # 共通の抽出指示
        courses/              # コース固有の追加指示
          _default.md         # フォールバック
          417.md              # 例: E417/EH417用

    render/                   # Stage 3
      excel.py                # Excel書き込み
      audit.py                # 監査ログ

    shared/                   # 横断ユーティリティ
      types.py                # 全データモデル
      text.py                 # collapse_ws, contains_any 等（1箇所のみ）
      errors.py               # 例外階層
```

### ルール
- **新規ファサード禁止** — 後方互換ラッパーは作らない（既存の `room_merge.py` は技術的負債として管理）
- **依存方向**: shared ← resolve ← parse ← integrate ← render。逆方向禁止
- **各モジュール400行以下**
- **collapse_ws は shared/text.py に1箇所のみ**

---

## 7. テスト戦略

### 方針
全移植はしないが「捨てる」のではなく**優先順位をつける**。
fnl-mockの592件は実質的な仕様書であり、未移植の判断には説明責任を持つ。

### 移行優先度（must / should / could）

旧テスト592件を以下の基準でスコア化し、3段階に分類する。
**スコア = 失敗時の業務影響 × 変更頻度 × 検出困難性**

| 優先度 | 対象 | 方針 |
|--------|------|------|
| **must** | E2E、VIP判定、カテゴリ分類、remarks書き換え | 必須移植。全体の約8割をカバー |
| **should** | room_merge、who_id解決、tour_header | Phase完了時に移植 |
| **could** | ユーティリティ単体テスト（collapse_ws等） | 再実装の方が速い。移植しない場合は理由を記録 |

未移植テストは `docs/known-debt.md` などに理由を記録し、回帰時に追跡可能にする。

### テスト層別（種類 × 対象）

| 層 | テスト種類 | 対象 | 実行頻度 |
|----|-----------|------|---------|
| shared/ | プロパティテスト | 型変換、テキスト処理の不変条件 | 毎CI |
| parse/, integrate/ | ユニットテスト + goldenテスト | 業務ルール（VIP、カテゴリ等） | 毎CI |
| llm/ | 契約テスト | MockAdapter/NullAdapterが Protocol準拠か | 毎CI |
| e2e/ | goldenテスト | パイプライン全体の入出力一致 | 毎CI |
| e2e/ | **プロンプト回帰テスト** | LLM抽出品質（recall/precision） | `pytest -m llm_quality` で手動実行 |

### プロンプト回帰テスト

プロンプト（`courses/XXX.md`）を編集した際に、抽出品質の変化を検証する。
独立したML評価システムは作らず、goldenテストの拡張として実装する。

```
tests/e2e/
  fixtures/
    e417_1008/
      input/          # テスト用PDF（RL/PL/ML）
      expected.json   # 期待される抽出結果（goldenファイル）
  test_pipeline_smoke_minimum.py # CI常時実行のsmoke E2E（MockAdapter）
  test_pipeline_e2e.py           # 実PDFを使うE2E（ローカル）
  test_llm_quality.py # プロンプト回帰テスト（実LLM使用）
```

```python
@pytest.mark.llm_quality
def test_extraction_quality():
    """プロンプト変更時に手動実行。LLM抽出結果をgoldenと比較"""
    result = run_with_real_llm(fixtures / "e417_1008")
    golden = load_golden("e417_1008/expected.json")

    assert recall(result, golden) >= 0.90    # 見逃し率
    assert precision(result, golden) >= 0.85  # 誤抽出率
```

- 通常CIでは実行しない（LLM APIコスト＋非決定的出力のため）
- `pytest -m llm_quality` で明示的に実行
- 閾値ベース（厳密一致を求めない）。初期値はfnl-mockでの手動品質検証（E417 1008等）に基づく。rule-basedのみでrecall 0.75/precision 0.90程度 → LLM補助で recall 0.90+/precision 0.85+ を目標。閾値はベータ運用中に調整
- goldenファイルはgitで管理。更新は `pytest --update-golden` で実行し、PRレビューでdiffを確認。golden更新PRには変更理由を必須とする

### テスト構成
```
tests/
  parse/
    test_rooming.py
    test_passenger.py
    test_messagelist.py
  integrate/
    test_guest_builder.py
    test_remark_rewrite.py
    test_vip.py
    test_category.py
  resolve/
    test_who_id.py
    test_inquiry_match.py
  llm/
    test_openai.py         # 契約テスト
    test_mock_adapter.py   # 契約テスト
  render/
    test_excel.py
    test_audit.py
  e2e/
    test_pipeline_smoke_minimum.py # goldenテスト（MockAdapter）
    test_pipeline_e2e.py    # 実PDF E2E（ローカル）
    test_llm_quality.py     # プロンプト回帰テスト（実LLM）
    fixtures/
      e417_1008/
        input/              # テスト用PDF
        expected.json       # golden出力
```

- テストファイルはモジュールと1:1対応
- E2Eテストは `RunState` に `MockAdapter` / `FullMockAdapter` を使い分けて実行
- LLM差し替えは `RunState` 経由でモック可能
- 各テストファイル300行以下を目標
- fixtureは `tests/e2e/fixtures/` に集約

---

## 8. 移行計画

### Phase 1: スケルトン
- リポジトリ作成、ディレクトリ構成
- shared/types.py（全データモデル）、config.py（PipelineConfig）、shared/errors.py
- CI設定（pytest, ruff, mypy --strict）
- LLMAdapter Protocol + NullAdapter + MockAdapter
- **完了条件**: mypy --strict pass, ruff pass, CI green

### Phase 2: Parse Stage
- rooming.py, passenger.py, messagelist.py を移植
- dict → typed dataclass に変換
- テスト移植（tests/parse/）
- **完了条件**: parse系テスト全通過、ParseResult型の全フィールドが有効値または空インスタンス（Noneは使わない）

### Phase 3: Integrate Stage
- guest_builder.py, remark_rewrite.py, vip.py, category.py
- **Callable注入 → 直接import + RunState に変換**（最大の変更点）
- テスト移植（tests/integrate/）
- **完了条件**: integrate系テスト全通過、不要なCallable注入の解消と残存箇所の明示

### Phase 4: Render Stage + E2E
- excel.py, audit.py
- E2Eテスト（E417 1008で検証、MockAdapter使用）
- **完了条件**: E2E goldenテスト通過（E417 1008）

### Phase 5: LLM Adapter
- OpenAI adapter移植
- プロンプト管理（prompts/ ディレクトリ）
- **完了条件**: 契約テスト通過、`pytest -m llm_quality` でプロンプト回帰テスト実行可能

### 並行運用方針
- fnl-mockはPhase 4完了（E2E通過）まで本番稼働を継続
- 並行期間中のfnl-mockバグ修正: (1) fnl-mockで修正+リリース、(2) 該当テストケースをfnl-builderのmustテストに追加
- fnl-builderへのロジック移植はPhase進行に合わせて行い、fnl-mockのパッチを即座にバックポートする義務は負わない

---

## 決定事項（Codexレビュー反映）

| 項目 | 決定 | 理由 |
|------|------|------|
| パッケージ名 | `fnl_builder` | 短さと意味の両立 |
| Context可変性 | RunState(mutable) + PipelineConfig(frozen) 分離 | 設定は不変、状態は更新 |
| LLMAdapter粒度 | 2メソッド維持、将来は同階層追加 | 汎用1メソッドは境界が曖昧 |
| テスト移行 | must/should/could 3段階。未移植は理由記録 | 592件は仕様書。「捨てる」ではなく優先順位 |
| Python最低 | 3.11+（3.11未満はサポート対象外と明文化） | ExceptionGroup前提。環境確認済みが条件 |
| mypy --strict | `src/` は最初からstrict必須 | 新規リポなので後付けより初期strictが低コスト |
