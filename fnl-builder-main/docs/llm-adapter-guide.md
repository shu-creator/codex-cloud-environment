# LLM Adapter Implementation Guide

fnl-builder の LLM 層は Protocol ベースで設計されており、別の LLM プロバイダに差し替えることができます。

## LLMAdapter Protocol

定義: `src/fnl_builder/llm/adapter.py`

```python
class LLMAdapter(Protocol):
    def extract_remarks(
        self, text: str, pages: list[object], prompts: PromptConfig,
    ) -> list[LLMItem]: ...

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None: ...
```

### `extract_remarks`

メッセージリストのテキストと分割済みページを受け取り、ゲストごとの備考（特記事項）を抽出します。

- `text`: メッセージリスト全体のテキスト
- `pages`: ページ単位のデータ（`list[tuple[int, str]]` 等、チャンク分割後の入力）
- `prompts`: システムプロンプトと抽出プロンプト
- 戻り値: `list[LLMItem]` — カテゴリ・フェーズ・エビデンス付きの抽出結果

### `extract_tour_header`

ルーミングリストの冒頭からツアーメタデータ（ツアー番号、出発日等）を抽出します。

- `excerpt`: ルーミングリスト先頭部分のテキスト
- 戻り値: `TourHeaderData | None` — 抽出できなければ `None`

## 既存実装

| クラス | ファイル | 用途 |
|--------|---------|------|
| `OpenAIAdapter` | `src/fnl_builder/llm/openai.py` | 本番用。OpenAI Responses API を urllib で直接呼び出し |
| `FullMockAdapter` | `src/fnl_builder/llm/mock.py` | テスト用。決定論的な結果を返す |
| `NullAdapter` | `src/fnl_builder/llm/adapter.py` | LLM無効時。空リストを返す |
| `MockAdapter` | `src/fnl_builder/llm/adapter.py` | 単体テスト用。固定アイテムを返す |

## 新しいアダプターの作成手順

### 1. アダプタークラスを実装

```python
# src/fnl_builder/llm/my_provider.py
from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.shared.types import LLMItem, TourHeaderData


class MyProviderAdapter:
    """Protocol に合致していれば継承不要（structural subtyping）。"""

    def extract_remarks(
        self, text: str, pages: list[object], prompts: PromptConfig,
    ) -> list[LLMItem]:
        # pages を LLM に送り、LLMItem のリストを返す
        ...

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        # ツアーメタデータを返す（対応しない場合は None）
        return None
```

### 2. RunState.from_config に登録

現状、アダプターの切り替えは `src/fnl_builder/config.py` の `RunState.from_config()` 内の
分岐で行っています。新しいプロバイダを追加するにはコード変更が必要です:

```python
# config.py の RunState.from_config() 内
elif config.llm_provider == "my_provider":
    from fnl_builder.llm.my_provider import MyProviderAdapter
    llm = MyProviderAdapter()
```

`PipelineConfig.llm_provider` の `Literal` 型にも値を追加してください。

> **Note**: 将来的に `run(..., llm_adapter=...)` のような外部注入ポイントの追加を検討しています。
> これが実装されれば、コード変更なしでアダプターを差し替えられるようになります。

### 3. テスト

`MockAdapter` を参考にした単体テストの例:

```python
from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.shared.types import Category, LLMItem, Phase


def test_my_adapter_returns_items() -> None:
    adapter = MyProviderAdapter()
    prompts = PromptConfig(system="...", extract_base="...")
    items = adapter.extract_remarks("sample text", [], prompts)
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, LLMItem)
        assert isinstance(item.category, Category)
        assert isinstance(item.phase, Phase)
```

## 関連ファイル

- `src/fnl_builder/llm/extraction.py` — LLM抽出のオーケストレーション
- `src/fnl_builder/llm/response_parser.py` — JSONレスポンスのパーサー
- `src/fnl_builder/llm/chunking.py` — ページ分割ユーティリティ
- `src/fnl_builder/llm/schema.json` — 構造化出力のJSONスキーマ
