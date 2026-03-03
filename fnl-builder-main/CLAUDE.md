# fnl-builder Project Instructions

## Project Overview
ツアー添乗用 final_list.xlsx を3種PDF（RoomingList / PassengerList / MessageList）から自動生成するパイプライン。
Rule-based抽出 + LLM補助抽出の2パス構成。fnl-mock をゼロから再設計した後継リポジトリ。

## Design Document
設計方針は `docs/design.md` を参照。変更時はCodexレビューを通すこと。

## Module Structure
```
src/fnl_builder/
  cli.py              # CLI → PipelineConfig
  pipeline.py          # 3ステージオーケストレーション
  config.py            # PipelineConfig, InputPaths
  parse/               # Stage 1: PDF解析
  integrate/           # Stage 2: ゲスト統合
  resolve/             # 横断的な解決ロジック
  llm/                 # LLMアダプター層
  render/              # Stage 3: Excel出力
  shared/              # types, errors, text utils
```

## Commands

### Test
```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q --tb=short
```

### Lint & Type Check
```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/ --strict
```

### Prompt Regression Test (manual, uses real LLM)
```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -m llm_quality -q
```

## PR Workflow
1. Branch naming: `refactor/xxx`, `fix/xxx`, `feat/xxx`
2. Implementation -> test -> commit -> push -> `gh pr create`
3. **影響するドキュメント（dev-spec.md, README.md等）の更新を確認する**
4. **PR作成後は自動で `/codex-review` を実行する**（ユーザーの指示不要）
5. Merge: `gh pr merge <number> --merge`（ユーザーの承認後）
6. Post-merge: `git checkout main && git pull origin main` -> verify tests

## Role Division
- **Claude**: 設計、タスク分解、レビュー、意思決定
- **Codex**: 実装、テスト生成（`/codex-review` でレビュー）
- Claudeは原則としてアプリケーションコードを直接書かない。Codexに委譲する
- 例外: Codexが使えない緊急時のみ直接編集可（理由を記録すること）

## Implementation Rules
- 真実源は Git。作業は1タスク1ブランチで隔離する
- 変更ファイル数が12を超えたらタスク分割を検討する
- 差分が500行を超えたらタスク分割を検討する
- 2回連続でテスト失敗したら実装継続ではなく再計画する
- 不明点は短い質問を1つだけ行い、それでも不明なら仮定を明示して進む
- 最小変更を優先する。不要なリファクタを混ぜない

## Python
- Python 3.11+
- mypy --strict（初日から全体適用）
- 依存方向: shared ← resolve ← parse ← integrate ← render（逆方向禁止）
- 各モジュール400行以下

## Codex指示の書き方
AGENTS.md にCodex共通規約を集約済み。Codex exec プロンプトでは以下だけ書く:
1. **タスク**: 何を作る/変える（1-2文）
2. **参照ファイル**: `Read src/...` で読むべきファイルパス（全文ペースト禁止）
3. **ポート元**: fnl-mockからの移植時は旧パスのみ記載。Codexが自分で読む
4. **テスト**: 期待するテストケース名（あれば）
5. **制約**: タスク固有の注意点のみ。AGENTS.mdと重複する規約は書かない
