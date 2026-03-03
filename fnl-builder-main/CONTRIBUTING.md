# Contributing

## Prerequisites

- Python 3.11+
- virtualenv (`.venv`)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

UIを触る場合:

```bash
pip install -e ".[ui]"
```

## Required Local Checks

```bash
.venv/bin/python -m pytest tests/ -q --tb=short
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/ --strict
```

LLM品質テスト（任意・手動）:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/ -m llm_quality -q
```

## Change Rules

- 最小変更を優先する
- `src/` の依存方向ルールを守る
- `dict[str, Any]` はI/O境界以外で増やさない
- 実データ（顧客情報、実PDF）をコミットしない

## Pull Requests

- 変更理由と影響範囲を明記
- 追加・更新したテストを明記
- CI green を確認してからレビュー依頼
