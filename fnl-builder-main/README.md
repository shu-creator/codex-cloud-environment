# fnl-builder

3種の入力書類から添乗用 `final_list.xlsx` を生成するパイプラインです。

- RoomingList (PDF)
- PassengerList (PDF)
- MessageList (PDF or CSV)

内部は `parse -> integrate -> render` の3ステージで実行されます。

## Requirements

- Python 3.11+

## Install

```bash
pip install -e ".[dev]"
```

UIを使う場合:

```bash
pip install -e ".[ui]"
```

## CLI Usage

公開エントリポイント:

```bash
fnl-builder --help
```

モジュール実行:

```bash
python -m fnl_builder --help
```

### files モード

filesモードでは `--roominglist`, `--passengerlist`, `--messagelist`, `--out` が必須です。

```bash
fnl-builder \
  --roominglist /path/to/rooming.pdf \
  --passengerlist /path/to/passenger.pdf \
  --messagelist /path/to/messagelist.pdf \
  --out /path/to/final_list.xlsx \
  --audit /path/to/final_list_audit.json \
  --llm-provider none
```

`--messagelist` は `.csv` も指定できます。

### zip モード（実装済み）

zipモードでは `--zip` と `--out` が必須です。`--zip` と個別入力オプションは排他です。`--template` は省略可（省略時はデフォルトテンプレートを使用）。

```bash
fnl-builder \
  --zip /path/to/fnl_bundle.zip \
  --out /path/to/final_list.xlsx \
  --audit /path/to/final_list_audit.json \
  --llm-provider none
```

### Exit Codes

- `0`: 正常終了（`--help` を含む）
- `2`: usage error（`argparse` による必須引数不足・不正オプション・不正choice）
- `1`: アプリケーションエラー（入力モード検証失敗、`FnlError`、error Issue）

## Development Commands

テスト:

```bash
pytest tests/ -q --tb=short
```

Lint:

```bash
ruff check src/ tests/
```

型検査:

```bash
mypy src/ --strict
```

LLM品質テスト（手動）:

```bash
pytest tests/ -m llm_quality -q
```

## CI Gates

CIは以下を実行します。

1. `pip install ".[dev]"`
2. `ruff check src/ tests/`
3. `mypy src/ --strict`
4. `pytest tests/ -q --tb=short`
5. `python -m build`
6. wheel install smoke（`fnl-builder --help`, `fnl-builder --version`, `python -m fnl_builder --help`, `python -m fnl_builder --version`, 資産読込確認）

## Limitations / Known Simplifications

- **ZIP入力**: 各書類種別につきZIP内1ファイルを前提とします。複数候補がある場合は `sorted(rglob("*"))` 順で最初にマッチしたものを採用し、エラーにはなりません。必須なのは RoomingList のみ（PassengerList/MessageList は欠落可）。ファイル名に `ルーミングリスト`/`rooming`, `PSGリスト`/`パッセンジャー`/`passenger`, `MSGリスト`/`メッセージリスト`/`messagelist` を含めてください（大文字小文字不問）。
- **終了コードと audit**: exit 0 は「error レベルの issue がない」ことを意味し、warning（`missing_guest_data`, `rooms_mismatch_total` 等）が残っている可能性があります。`--audit` で出力される JSON の `issues` を必ず確認してください。
- **PDF抽出の環境依存**: RoomingList/PassengerList は `pdftotext` が PATH にあればそちらを優先し、なければ `pypdf` にフォールバックします。MessageList(PDF) は常に `pypdf` を使用します。環境間の抽出差異を避けるには `FNL_DISABLE_PDFTOTEXT_SUBPROCESS=1` で全て pypdf に統一できます。
- **外部契約は CLI**: Python API (`from fnl_builder import run`) は内部開発者向けです。外部向けの正式な入出力契約は CLI (`fnl-builder --help`) および本 README を参照してください。

## Sample Data

動作確認用のダミーデータが `fixtures/` に同梱されています。実在の個人情報は含まれていません。

- `fixtures/sample_bundle/` — PDF 3種（RoomingList, PassengerList, MessageList）+ 期待 audit JSON
- `fixtures/sample_bundle_csv/` — PDF 2種 + CSV MessageList + 期待 audit JSON

各ディレクトリの README に実行コマンドと検証方法が記載されています。

## Notes

- `tests/e2e/test_pipeline_e2e.py` は実PDFを使うE2Eです。環境変数 `FNL_E2E_FIXTURE_DIR` でPDFディレクトリを指定します（未設定時はスキップ）。
- `tests/e2e/test_pipeline_smoke_minimum.py` は CIで常時実行する合成smoke E2Eです。
