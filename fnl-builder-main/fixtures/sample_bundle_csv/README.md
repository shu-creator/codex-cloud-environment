# Sample Bundle (CSV MessageList)

fnl-builder の動作確認用ダミーデータです。MessageList が CSV 形式のパターンです。
実在の個人情報は含まれていません。

## 含まれるファイル

| ファイル | 説明 |
|---------|------|
| `1027_E417_ROOMINGLIST.pdf` | RoomingList（ダミー） |
| `1027_E417_PASSENGERLIST.pdf` | PassengerList（ダミー） |
| `1027_E417_MessageList(CSV).csv` | MessageList CSV形式（ダミー） |
| `expected_audit.json` | 期待される audit 出力（環境依存フィールド除去済み） |

## 実行例

```bash
fnl-builder \
  --roominglist fixtures/sample_bundle_csv/1027_E417_ROOMINGLIST.pdf \
  --passengerlist fixtures/sample_bundle_csv/1027_E417_PASSENGERLIST.pdf \
  --messagelist "fixtures/sample_bundle_csv/1027_E417_MessageList(CSV).csv" \
  --out /tmp/final_list.xlsx \
  --audit /tmp/audit.json \
  --llm-provider none
```

終了コード 0 で正常終了し、`/tmp/final_list.xlsx` と `/tmp/audit.json` が生成されます。

## PDF版との違い

- MessageList が CSV 形式（`--messagelist` に `.csv` を指定）
- CSV では備考が受付番号単位（`remarks_by_inquiry`）で格納され、ゲスト単位への自動フォールバックが適用されます

## 検証方法

生成された audit JSON から環境依存フィールド（`started_at`, `finished_at`, `extraction_meta`）を除いた内容が `expected_audit.json` と一致することを確認してください。

主な期待値:
- `counts.total_guests`: 7
- `status`: "completed"
- `issues`: warning のみ（error なし）→ 終了コード 0

注意: `expected_audit.json` は `pdftotext` が利用可能な環境で生成されています。`pypdf` フォールバック環境（`pdftotext` 未インストール、または `FNL_DISABLE_PDFTOTEXT_SUBPROCESS=1`）では PDF 抽出結果が異なり、`issues` の内容が変わる場合があります。`counts` と `status` は抽出方法に依存しません。
