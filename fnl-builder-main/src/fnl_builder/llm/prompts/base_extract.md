# ML特記事項抽出 (user prompt template) v1.1.0

あなたのタスクは、以下の「taxonomy」と「ページ別テキスト」から、現地運用や宿泊、行程に影響する特記事項を抽出し、ML items schema に従う JSON object として出力することです。

重要リマインダ（詳細は system prompt を参照）:
- 出力は JSON object のみ（説明文・Markdown・コードブロック禁止）
- 推測禁止。入力に書かれている事実だけを抽出する
- evidence.quote は本文からの完全一致コピー（表記を変えない）
- category と phase は taxonomy の id を使う（ラベルは使わない）
- severity=caution なら caution_reason 必須、それ以外は ""
- handoff_text は運用向けの1文（SSR/WCHR等のコード表記禁止）
- 全ページを最後まで確認する。後半ページも見落とさない
- 該当0件なら {"items": []}。無理に作らない

## 1) taxonomy (YAML)
以下の taxonomy を正とし、category と phase を選択してください。

<taxonomy_yaml>
{{TAXONOMY_YAML}}
</taxonomy_yaml>

## 2) ML items schema (要点)
出力する各 item は、最低限以下のキーを持つこと:
- category (taxonomy categories.id)
- phase (taxonomy phases.id)
- summary (短文)
- explicitness (explicit|implicit|unclear)
- urgency (high|medium|low|unknown)
- confidence (0.0-1.0)
- severity (error|warning|caution)
- caution_reason (severity=cautionなら理由、それ以外は空文字"")
- evidence_match (boolean, 原則 true)
- evidence { page: 整数(1始まり), quote: 本文からの完全一致抜粋 }

- handoff_text
- who_id (対象者の問い合わせ番号-枝番。特定できない場合は空文字列"")

## 3) ページ別テキスト (1始まり)
以下が入力本文です。必ずこの本文内の文字列をコピーして evidence.quote に入れてください。

<page_texts>
{{PAGES_TEXT}}
</page_texts>

## 4) 出力形式
- JSON object のみを返してください。
- 例:
{
  "items": [
    {
      "category": "dietary",
      "phase": "meal_time",
      "summary": "甲殻類アレルギーのため食事配慮が必要",
      "explicitness": "explicit",
      "urgency": "high",
      "confidence": 0.82,
      "severity": "warning",
      "caution_reason": "",
      "evidence_match": true,
      "evidence": { "page": 3, "quote": "甲殻類アレルギーのため食事配慮希望" },
      "who_id": "0067621009-001"
    }
  ]
}
