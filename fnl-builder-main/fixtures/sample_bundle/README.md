# Sample Bundle

fnl-builder の動作確認用ダミーデータです。実在の個人情報は含まれていません。

## 含まれるファイル

| ファイル | 説明 |
|---------|------|
| `ルーミングリスト_E417_20261008.pdf` | RoomingList（ダミー） |
| `PSGリスト_E417_20261008.pdf` | PassengerList（ダミー） |
| `MSGリスト_E417_20261008.pdf` | MessageList（ダミー） |
| `expected_audit.json` | 期待される audit 出力（環境依存フィールド除去済み） |

## 実行例

```bash
fnl-builder \
  --roominglist fixtures/sample_bundle/ルーミングリスト_E417_20261008.pdf \
  --passengerlist fixtures/sample_bundle/PSGリスト_E417_20261008.pdf \
  --messagelist fixtures/sample_bundle/MSGリスト_E417_20261008.pdf \
  --out /tmp/final_list.xlsx \
  --audit /tmp/audit.json \
  --llm-provider none
```

終了コード 0 で正常終了し、`/tmp/final_list.xlsx` と `/tmp/audit.json` が生成されます。

## 検証方法

生成された audit JSON から環境依存フィールド（`started_at`, `finished_at`, `extraction_meta`）を除いた内容が `expected_audit.json` と一致することを確認してください。

主な期待値:
- `counts.total_guests`: 9
- `status`: "completed"
- `issues`: warning のみ（error なし）→ 終了コード 0

注意: `expected_audit.json` は `pdftotext` が利用可能な環境で生成されています。`pypdf` フォールバック環境（`pdftotext` 未インストール、または `FNL_DISABLE_PDFTOTEXT_SUBPROCESS=1`）では PDF 抽出結果が異なり、`issues` の内容が変わる場合があります。`counts` と `status` は抽出方法に依存しません。
