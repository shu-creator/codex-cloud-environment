# Security Policy

## Reporting a Vulnerability

脆弱性は公開Issueではなく、下記連絡先へ私的に報告してください。

- Contact: `iwata89215690@icloud.com`
- Include: 影響範囲、再現手順、想定インパクト、暫定回避策（あれば）

## Sensitive Data and PII

本リポジトリはPIIを含みうる業務文書を扱うため、以下を必須とします。

- 実顧客データをコード、テスト、ログ、ドキュメントに含めない
- fixtureは匿名化・架空データのみを使用する
- audit/diagnostic出力は必要最小限の情報に留める

## Supported Versions

セキュリティ修正は原則 `main` ブランチを対象に実施します。
