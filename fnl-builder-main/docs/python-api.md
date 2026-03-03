# Python API Guide

> **Note**: 本ドキュメントは内部開発者向けです。外部向けの正式な入出力契約は CLI (`fnl-builder --help`) および README を参照してください。Python API は内部実装の都合で引数のオプショナリティが CLI と異なる場合があります。

fnl-builder はCLIだけでなく、Pythonライブラリとしても利用できます。

## インストール

```bash
pip install fnl-builder
# または開発用
pip install -e ".[dev]"
```

LLM抽出を使う場合は `OPENAI_API_KEY` 環境変数を設定してください。
外部SDKは不要です（OpenAI APIへはurllib経由で直接通信します）。

## 最小コード例

```python
from pathlib import Path
from fnl_builder import run, PipelineConfig, InputPaths

config = PipelineConfig(
    llm_provider="none",  # "openai" | "mock" | "none"
    input_paths=InputPaths(
        rooming=Path("rooming.pdf"),
        passenger=Path("passenger.pdf"),     # optional
        messagelist=Path("messagelist.pdf"),  # optional
        template=Path("template.xlsx"),
        output=Path("final_list.xlsx"),
        audit=Path("audit.json"),            # optional
    ),
)
result = run(config)
print(f"Output: {result.output_path}")
print(f"Issues: {len(result.audit.issues)}")
```

## 主要な型

### `PipelineConfig`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `llm_provider` | `"none" \| "openai" \| "mock"` | LLMバックエンド選択 |
| `input_mode` | `"zip" \| "files"` | 入力モード（デフォルト: `"files"`） |
| `input_paths` | `InputPaths` | 入出力パス |

### `InputPaths`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `rooming` | `Path` | ルーミングリストPDF（必須） |
| `passenger` | `Path \| None` | パッセンジャーリストPDF |
| `messagelist` | `Path \| None` | メッセージリストPDF/CSV |
| `template` | `Path` | テンプレートExcel |
| `output` | `Path` | 出力先Excel |
| `audit` | `Path \| None` | 監査ログJSON出力先 |

### `RenderResult`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `output_path` | `Path` | 生成されたExcelファイルのパス |
| `audit` | `AuditLog` | 実行監査ログ |

### `AuditLog`

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `started_at` | `str` | ISO 8601 UTC タイムスタンプ |
| `input_mode` | `str` | `"zip"` or `"files"` |
| `input_files_sha256` | `dict[str, str]` | 入力ファイルのSHA-256ハッシュ |
| `llm_extraction` | `LLMExtractionMeta \| None` | LLM抽出メタデータ |
| `counts` | `PipelineCounts` | ゲスト数の集計 |
| `issues` | `list[Issue]` | 検出された問題 |

## エラーハンドリング

fnl-builder は以下のエラー階層を使います:

```
FnlError (基底)
├── InputError   # 入力ファイルの問題（存在しない、形式不正等）
├── ParseError   # PDF/CSV解析の問題（想定外のフォーマット等）
└── LLMError     # LLM呼び出しの問題（API障害、レスポンス不正等）
```

### 推奨パターン

```python
from fnl_builder import run, FnlError, InputError, LLMError

try:
    result = run(config)
except InputError as e:
    # ユーザーに入力ファイルの修正を促す
    print(f"入力エラー: {e}")
except LLMError as e:
    # LLMなしで再試行、またはリトライ
    print(f"LLMエラー: {e}")
except FnlError as e:
    # その他のパイプラインエラー
    print(f"エラー: {e}")
```

`llm_provider="none"` を使えば `LLMError` は発生しません。

## 型チェック

fnl-builder は `py.typed` マーカーを同梱しています（PEP 561）。
mypy / pyright で型情報が自動的に認識されます。
