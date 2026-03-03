# Known Debt (意図的負債)

Last updated: 2026-03-02

## 1. CI E2E が実PDF抽出経路を通らない

- 既存E2Eは `FNL_E2E_FIXTURE_DIR` 環境変数で指定されたディレクトリの実PDFを使用（未設定時は skip）
- smoke E2Eは `extract_pdf_text` をモックしており、pdftotext/pypdf の実経路は未検証
- **再検討トリガー**: 匿名化PDFを安全に配布できるようになったら、CIで実抽出E2Eを追加

## 2. mypy --strict が UI モジュールを除外

- `src/fnl_builder/ui/app.py` は streamlit に依存し、CI環境では型チェック対象外
- ローカルでは `pip install ".[ui]"` 済みの環境で検証可能
- **再検討トリガー**: CI時間予算が増えたら `.[ui]` 込みの検証に切り替え

## 3. Facade/Callable注入パターンの残存

- `room_merge.py` は Facade構成、`room_merge_name_flow.py` は Callable注入を使用
- テスタビリティのための意図的DI。現時点で実害なし
- **再検討トリガー**: モジュール構成の大規模リファクタ時に統合を検討

## 4. GitHub運用テンプレ未整備

- `.github` 配下は CI workflow と Dependabot のみ（PR/Issue テンプレなし）
- **再検討トリガー**: 開発人数が増えたら導入
