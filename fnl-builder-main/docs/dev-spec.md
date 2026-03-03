# fnl-builder 開発仕様書

本書は fnl-builder の技術仕様を記載した開発委託先向けドキュメントです。

---

## 1. プロジェクト概要

fnl-builder は、ツアー添乗用のファイナルリスト（Excel）を3種の入力書類（Rooming/PassengerはPDF、MessageListはPDF/CSV）から自動生成するパイプラインです。

### 入力

| ファイル | 形式 | 必須 | 内容 |
|---------|------|------|------|
| ルーミングリスト | PDF | 必須 | 部屋割り・ゲスト名・受付番号 |
| パッセンジャーリスト | PDF | CLI files: 必須 / Python API: 任意 | パスポート情報 |
| メッセージリスト | PDF/CSV | CLI files: 必須 / Python API: 任意 | 特記事項・備考 |
| テンプレート | Excel | CLI: 任意 / Python API: 指定推奨 | 出力レイアウト（CLIは省略時にバンドル済みデフォルトを使用） |

注: `InputPaths` 型は `passenger` / `messagelist` を optional として保持する。  
CLIは別レイヤーで、filesモード時に `--roominglist --passengerlist --messagelist --out` を必須として検証する。

### 出力

- `final_list.xlsx` — ゲスト情報を統合したExcelファイル
- `audit.json` — 処理記録・検出問題の監査ログ（任意）

### アーキテクチャ

```
CLI / Python API
  │
  ▼
Pipeline.run(config)
  ├─ Stage 1: Parse     … PDF/CSVからデータ抽出
  ├─ Stage 2: Integrate … 3書類の照合・統合・LLM補助抽出
  └─ Stage 3: Render    … Excel出力 + 監査ログ
```

ステージ間は frozen dataclass でデータを受け渡す。各ステージは独立しており、単体テスト可能。

---

## 2. 環境構築

### 要件

- Python 3.11+
- OS: macOS / Linux / Windows

### セットアップ

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

UI（Streamlit）を触る場合:

```bash
pip install -e ".[ui]"
```

### 依存パッケージ

| パッケージ | 用途 |
|-----------|------|
| `pypdf>=4.0,<7.0` | PDF テキスト抽出 |
| `openpyxl>=3.1.0,<4.0` | Excel 読み書き |

dev依存: `pytest`, `ruff`, `mypy`, `build`

### 開発コマンド

```bash
# テスト
pytest tests/ -q --tb=short

# Lint
ruff check src/ tests/

# 型検査
mypy src/ --strict

# LLM品質テスト（手動・APIキー必要）
pytest tests/ -m llm_quality -q
```

---

## 3. モジュール構成と依存方向

### ディレクトリツリー

```
src/fnl_builder/
├── __init__.py              # 公開API re-export
├── __main__.py              # python -m fnl_builder
├── cli.py                   # CLIエントリポイント
├── config.py                # PipelineConfig, InputPaths, RunState
├── pipeline.py              # 3ステージオーケストレーション
│
├── parse/                   # Stage 1: PDF解析
│   ├── rooming.py           # RoomingList → RoomingData
│   ├── passenger.py         # PassengerList → PassengerData
│   ├── messagelist.py       # MessageList → MessageListData
│   ├── messagelist_rules.py # カテゴリ分類ルール定数
│   ├── messagelist_companion.py # 同行者グループ検出
│   ├── messagelist_fnl.py   # FNL共有ブロック処理
│   ├── tour_header.py       # ツアーヘッダー抽出（rule-based）
│   ├── tour_header_llm.py   # ツアーヘッダー抽出（LLM補助）
│   ├── input_extract.py     # PDF/CSVテキスト抽出
│   ├── course_code.py       # コースコード抽出
│   └── zip_extract.py       # ZIPアーカイブ展開
│
├── integrate/               # Stage 2: ゲスト統合
│   ├── guest_builder.py     # ゲスト統合メインロジック
│   ├── remark_rewrite.py    # remarks書き換え・フォーマット
│   ├── vip.py               # VIP判定
│   ├── category.py          # カテゴリ精緻化
│   ├── room_merge.py        # 部屋マージ（ファサード）
│   ├── room_merge_group.py  # グループIDベースマージ
│   ├── room_merge_name.py   # 名前ベースマージ分析
│   ├── room_merge_name_flow.py # 名前ベースマージフロー
│   ├── room_merge_name_llm.py  # LLM名前解析
│   ├── room_merge_parse.py  # MLテキストからマージ対象抽出
│   ├── room_sharing.py      # 同室備考処理
│   └── p_markers.py         # Pマーカー再割当
│
├── llm/                     # LLMアダプター層
│   ├── adapter.py           # LLMAdapter Protocol + NullAdapter
│   ├── openai.py            # OpenAI実装（urllib直接通信）
│   ├── mock.py              # FullMockAdapter（テスト用）
│   ├── extraction.py        # LLM抽出オーケストレーション
│   ├── response_parser.py   # JSONレスポンスパーサー
│   ├── chunking.py          # ページ分割ユーティリティ
│   ├── quote.py             # 引用抽出
│   ├── prompt_loader.py     # プロンプト読み込み
│   ├── schema.json          # 構造化出力のJSONスキーマ
│   └── prompts/             # プロンプトテンプレート
│       ├── base_system.txt  # 共通システムプロンプト
│       ├── base_extract.md  # 共通抽出指示
│       └── courses/         # コース固有プロンプト
│
├── render/                  # Stage 3: Excel出力
│   ├── excel.py             # Excel書き込み + default_template_ref()
│   ├── excel_text.py        # Excelテキスト処理
│   ├── audit.py             # 監査ログ処理
│   ├── remarks_format.py    # remarksフォーマット
│   └── template.xlsx        # デフォルトテンプレート
│
├── resolve/                 # 横断的な解決ロジック
│   ├── who_id.py            # who_id → inquiry 解決
│   └── inquiry_match.py     # 枝番照合
│
├── shared/                  # 横断ユーティリティ
│   ├── types.py             # 全データモデル定義
│   ├── errors.py            # 例外階層
│   ├── text.py              # テキスト処理（collapse_ws等）
│   └── io.py                # I/Oユーティリティ
│
├── py.typed                 # PEP 561 マーカー
│
└── ui/                      # Streamlit Web UI
    └── app.py
```

### 依存方向（厳守）

```
shared ← resolve ← parse ← integrate ← render
                                          ↑
                                    llm（Protocol経由）
                                          ↑
                                      pipeline
                                          ↑
                                       config
                                          ↑
                                        cli
```

**逆方向の依存は禁止**。例: parse が integrate をimportしてはならない。

### 制約

- 各モジュール **400行以下**
- `dict[str, Any]` は **I/O境界（JSON serialize/deserialize）のみ** 許可
- `collapse_ws` は `shared/text.py` に1箇所のみ定義

---

## 4. データモデル

すべて `src/fnl_builder/shared/types.py` に定義。

### ステージ間データ（frozen dataclass）

```python
@dataclass(frozen=True)
class ParseResult:
    rooming: RoomingData
    passenger: PassengerData
    messagelist: MessageListData
    tour_header: TourHeaderData

@dataclass(frozen=True)
class IntegrationResult:
    guests: list[GuestRecord]
    companion_groups: dict[str, set[str]]
    stats: RewriteStats

@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    audit: AuditLog
```

### 主要な型

| 型 | 用途 | パターン |
|----|------|---------|
| `GuestRecord` | 統合後の1ゲスト情報 | mutable dataclass |
| `RoomingData` | RL解析結果 | frozen + `empty()` classmethod |
| `PassengerData` | PL解析結果 | frozen + `empty()` classmethod |
| `MessageListData` | ML解析結果（`remarks_by_inquiry`, `remarks_by_inquiry_guest`, `course_by_inquiry`, `companion_groups` 等） | frozen + `empty()` classmethod |
| `TourHeaderData` | ツアーメタ情報 | frozen + `empty()` classmethod |
| `LLMItem` | LLM抽出1件 | frozen（category, who_id, confidence, phase, handoff_text 等） |
| `InquiryKey` | 受付番号（main + branch） | frozen |
| `PassportRecord` | パスポート情報 | frozen |
| `Issue` | 検出された問題1件 | frozen（level, code, message） |
| `AuditLog` | 監査ログ全体 | mutable |
| `PipelineCounts` | ゲスト数集計 | mutable |

### エラー階層

```python
FnlError (基底)
├── InputError   # 入力ファイルの問題（回復不可）
├── ParseError   # PDF/CSV解析失敗（回復不可）
└── LLMError     # LLM呼び出し失敗（フォールバックで続行）
```

定義: `src/fnl_builder/shared/errors.py`

### エラー処理方針

| 状況 | 処理 |
|------|------|
| ファイルが存在しない | `raise InputError(...)` |
| PDF解析失敗 | `raise ParseError(...)` |
| LLM APIタイムアウト | `raise LLMError(...)` → catch → Issue記録して続行 |
| PL/ML PDFが欠損（Python API経由） | `state.issues.append(Issue(...))` → 空データで続行 |
| remarks禁止語句検出 | `state.issues.append(Issue("error", ...))` |

CLI終了コード契約:

- `0`: 正常終了（`--help` 含む）
- `2`: usage error（`argparse` による必須引数不足・不正オプション・不正choice）
- `1`: アプリケーションエラー（`_validate_input_mode` 失敗、`FnlError`、error Issue）

---

## 5. パイプライン処理フロー

エントリポイント: `src/fnl_builder/pipeline.py`

```python
def run(config: PipelineConfig) -> RenderResult:
    state = RunState.from_config(config)
    parsed, ml_pages = parse_stage(state)
    _record_input_hashes(state)
    integrated = integrate_stage(parsed, state, ml_pages=ml_pages)
    return render_stage(integrated, state, rooming=parsed.rooming)
```

### RunState

```python
@dataclass
class RunState:
    config: PipelineConfig
    llm: LLMAdapter          # Protocol — テスト時はMockAdapter
    issues: list[Issue]       # 検出問題を蓄積
    audit: AuditLog           # 監査ログを蓄積

    @classmethod
    def from_config(cls, config: PipelineConfig) -> RunState:
        # llm_provider に応じて OpenAIAdapter / FullMockAdapter / NullAdapter を選択
```

定義: `src/fnl_builder/config.py`

### Stage 1: Parse

入力PDFからテキストを抽出し、各パーサーで構造化データに変換。

- `extract_pdf_text()` / `extract_messagelist_text()` でテキスト抽出
- `parse_rooming_list()` → `RoomingData`
- `parse_passenger_list()` → `PassengerData`
- `parse_message_list()` → `MessageListData`
- `extract_tour_header()` → `TourHeaderData`

### Stage 2: Integrate

3書類のデータを受付番号で照合・統合し、LLM補助抽出を実行。

1. LLM抽出（`run_llm_extraction()` — オプション）
2. ゲスト統合（`process_integrate_guest_data()`）
3. Pマーカー割当（`assign_initial_who_id()`）
4. 部屋マージ（`apply_room_merges()`）
5. 後処理（`process_post_room_grouping()`）

#### 備考(Remarks)統合ロジック

`_append_messagelist_remarks()` は以下の優先順位で備考を取得する:

1. **ゲスト単位** (`remarks_by_inquiry_guest[(inquiry, guest_position)]`) — PDF MLで個人特定可能な場合
2. **受付番号単位フォールバック** (`remarks_by_inquiry[inquiry]`) — CSV MLなどゲスト単位データが存在しない場合のみ適用

フォールバック条件: 当該受付番号に対してゲスト単位エントリが1件も存在しないこと。
これにより、PDF由来のゲスト固有備考が他ゲストへ漏洩することを防ぎつつ、
CSV由来の受付番号単位備考が全ゲストに配布される。

### Stage 3: Render

統合データをExcelテンプレートに書き込み、監査ログを出力。

- `render_final_list_workbook()` — Excel生成
- `process_audit_warnings()` — ゲスト数・部屋数の整合性チェック
- `write_audit_log()` — JSON監査ログ出力

---

## 6. LLMアダプター層

### Protocol定義

```python
# src/fnl_builder/llm/adapter.py

class LLMAdapter(Protocol):
    def extract_remarks(
        self, text: str, pages: list[object], prompts: PromptConfig,
    ) -> list[LLMItem]: ...

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None: ...
```

Structural subtyping（継承不要）。Protocol に一致するメソッドを持てばアダプターとして使える。

### 既存実装

| クラス | ファイル | 用途 |
|--------|---------|------|
| `OpenAIAdapter` | `llm/openai.py` | 本番用。OpenAI Responses API を urllib で直接呼び出し |
| `FullMockAdapter` | `llm/mock.py` | テスト用。決定論的な結果を返す |
| `NullAdapter` | `llm/adapter.py` | LLM不使用時。空リスト/Noneを返す |
| `MockAdapter` | `llm/adapter.py` | 単体テスト用。任意のLLMItemリストを返す |

### 新プロバイダの追加手順

1. `src/fnl_builder/llm/` に新ファイルを作成（例: `anthropic.py`）
2. `LLMAdapter` Protocol に適合する2メソッドを実装
3. `src/fnl_builder/config.py` の `RunState.from_config()` に分岐を追加:
   ```python
   elif config.llm_provider == "anthropic":
       from fnl_builder.llm.anthropic import AnthropicAdapter
       llm = AnthropicAdapter()
   ```
4. `cli.py` の `--llm-provider` choices にも追加
5. テスト: 既存の `tests/llm/test_mock_adapter.py` を参考に契約テストを作成

---

## 7. プロンプト管理

### ディレクトリ構造

```
src/fnl_builder/llm/prompts/
├── base_system.txt      # 全コース共通のシステムプロンプト
├── base_extract.md      # 共通の抽出指示
└── courses/
    ├── _default.md      # デフォルトコース補足
    └── 417.md           # E417/EH417用
```

### コースコード解決ルール

1. PDF内のコースコードを抽出（E417, ET470, EH417...）
2. プレフィックス除去・末尾連続数字を抽出（E417 → 417）
3. 各番号の `courses/XXX.md` を探す → 番号昇順で連結（重複行除去）
4. 1つでも courses ファイルがあれば `_default.md` は使わない
5. どの番号にも該当ファイルがなければ → `courses/_default.md`

### 新コース追加

コード変更不要。`courses/` に `{番号}.md` を作成するだけ。

例: コース E521 → `courses/521.md` を作成

```markdown
## コース固有の抽出事項
- シェンゲン協定圏のビザ要件に関する記載を重点抽出
- 複数都市移動のため離団・合流の記載に注意
```

---

## 8. 公開API

### インポート

```python
from fnl_builder import run, PipelineConfig, InputPaths
from fnl_builder import FnlError, InputError, LLMError, ParseError
from fnl_builder import AuditLog, GuestRecord, RenderResult
```

### 最小コード例

```python
from pathlib import Path
from fnl_builder import run, PipelineConfig, InputPaths

config = PipelineConfig(
    llm_provider="none",
    input_paths=InputPaths(
        rooming=Path("rooming.pdf"),
        passenger=Path("passenger.pdf"),
        messagelist=Path("messagelist.pdf"),
        template=Path("template.xlsx"),  # CLIでは省略可（Python APIでは指定推奨）
        output=Path("final_list.xlsx"),
        audit=Path("audit.json"),
    ),
)

result = run(config)
print(f"Output: {result.output_path}")
print(f"Total guests: {result.audit.counts.total_guests}")
for issue in result.audit.issues:
    print(f"  [{issue.level}] {issue.code}: {issue.message}")
```

### PipelineConfig

| フィールド | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `llm_provider` | `"none" \| "openai" \| "mock"` | — | LLMバックエンド |
| `input_mode` | `"zip" \| "files"` | `"files"` | 入力モード |
| `input_paths` | `InputPaths` | `InputPaths(rooming=Path())` | ファイルパス |

### InputPaths

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| `rooming` | `Path` | 必須 | ルーミングリストPDF |
| `passenger` | `Path \| None` | 任意 | パッセンジャーリストPDF |
| `messagelist` | `Path \| None` | 任意 | メッセージリストPDF/CSV |
| `template` | `Path` | 任意（型上はデフォルトあり） | テンプレートExcel（CLIは省略時にデフォルト補完） |
| `output` | `Path` | 運用上必須（型上はデフォルトあり） | 出力Excel |
| `audit` | `Path \| None` | 任意 | 監査ログJSON |

型チェック: `py.typed` マーカー同梱（PEP 561）。mypy/pyright で自動認識。

注: 上表は Python API の型定義。CLI filesモードは運用契約として  
`--roominglist --passengerlist --messagelist --out` を必須にする。

---

## 9. テスト戦略

### テスト層

| 層 | 種類 | 対象 | 頻度 |
|----|------|------|------|
| shared/ | プロパティテスト | 型変換・テキスト処理 | 毎CI |
| parse/, integrate/ | ユニット + golden | 業務ルール | 毎CI |
| llm/ | 契約テスト | MockAdapter が Protocol 準拠か | 毎CI |
| e2e/ | goldenテスト | パイプライン全体の入出力 | 毎CI |
| e2e/ | プロンプト回帰 | LLM抽出品質（recall/precision） | 手動 |

### テストファイル配置

src のミラー構造。例:

- `src/fnl_builder/parse/rooming.py` → `tests/parse/test_rooming.py`
- `src/fnl_builder/integrate/vip.py` → `tests/integrate/test_vip.py`

### LLM品質テスト

```bash
pytest tests/ -m llm_quality -q
```

- 通常CIでは実行しない（APIコスト + 非決定的出力）
- 閾値ベース: recall >= 0.90, precision >= 0.85

### E2Eテスト

- `tests/e2e/test_pipeline_smoke_minimum.py` — CI用（MockAdapter使用）
- `tests/e2e/test_pipeline_e2e.py` — ローカル用（実PDF、環境変数 `FNL_E2E_FIXTURE_DIR` で指定）

---

## 10. コーディング規約

### 型安全性

- **mypy --strict 必須**（src 全体）
- `# type: ignore` は正当な理由がある場合のみ（コメントで理由を記載）
- `dict[str, Any]` は I/O境界以外で使用禁止

### データクラスパターン

- **ステージ間データ**: `@dataclass(frozen=True)` + `@classmethod empty(cls) -> Self`
- **内部accumulator**: `@dataclass`（mutable）、モジュール外に公開しない

### Callable注入

原則禁止。以下の3箇所のみ許可:

- `remarks_has_banned`
- `store_remark`
- `NameLlmResolver`

### その他

- ファサードモジュール禁止（後方互換ラッパーなし）
- テストファイルは300行以下
- ruff によるフォーマット・lint（line-length=120, target-version=py311）

---

## 11. 既知の技術的負債

| 項目 | 状況 | 再検討トリガー |
|------|------|--------------|
| CI E2E が実PDF抽出経路を通らない | smoke E2E は `extract_pdf_text` をモック | 匿名化PDFを安全に配布できるようになったら |
| mypy --strict が UI モジュールを除外 | `ui/app.py` は CI 対象外 | CI時間予算が増えたら `.[ui]` 込みの検証に切り替え |
| Facade/Callable注入パターン残存 | `room_merge.py` Facade、`room_merge_name_flow.py` Callable注入 | 大規模リファクタ時に統合 |
| GitHub運用テンプレ未整備 | `.github` は CI workflow と Dependabot のみ | 開発人数が増えたら導入 |

---

## 12. CI/PRワークフロー

### CIゲート（`.github/workflows/ci.yml`）

| ステップ | コマンド |
|---------|---------|
| 1. Install | `pip install ".[dev]"` |
| 2. Lint | `ruff check src/ tests/` |
| 3. Type check | `mypy src/ --strict` |
| 4. Test | `pytest tests/ -q --tb=short` |
| 5. Build | `python -m build` |
| 6. Wheel smoke | `pip install dist/*.whl && fnl-builder --help && python -m fnl_builder --help` + 資産読込スモーク |

### PRルール

- ブランチ命名: `feat/xxx`, `fix/xxx`, `refactor/xxx`
- **差分 500行 / 12ファイルを超えたらタスク分割を検討**
- テスト全件パス + lint/mypy クリーンが必須
- 実データ（顧客情報、実PDF）はコミット禁止
