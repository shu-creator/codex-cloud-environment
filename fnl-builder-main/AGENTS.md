# AGENTS.md — Codex workspace rules

## Env
- Python 3.11+, venv at `.venv/`
- Test: `pytest tests/ -q --tb=short`
- Lint: `ruff check src/ tests/`
- Type: `mypy src/ --strict`

## Code rules
- mypy --strict, no `# type: ignore` without justification
- frozen dataclass for cross-stage data; mutable internal accumulators with `.freeze()`
- Dependency direction: shared ← resolve ← parse ← integrate ← render (no reverse)
- Max 400 lines per module
- No `dict[str, Any]` except at I/O boundaries (JSON serialize/deserialize)
- No Callable injection except `remarks_has_banned`, `store_remark`, and `NameLlmResolver`
- No new facade modules / backward-compat wrappers (existing debt is tracked separately)
- `collapse_ws` lives only in `shared/text.py`

## Patterns
- Parse result types: `@dataclass(frozen=True)` with `@classmethod empty(cls) -> Self`
- Internal parser state: `@dataclass` (mutable), never exposed outside module
- Protocol-based duck typing for cross-module interop (see messagelist_fnl.py)
- `normalize_inquiry_main(raw)`: `raw.lstrip("0") or "0"`

## File map (src/fnl_builder/)
```
shared/types.py    — ParseResult, MessageListData, RoomingData, PassengerData, TourHeaderData, LLMItem, etc.
shared/text.py     — collapse_ws, normalize_inquiry_main, contains_any
shared/errors.py   — FnlError hierarchy
config.py          — PipelineConfig, InputPaths
parse/input_extract.py — PDF/CSV text extraction
parse/rooming.py       — RoomingList parser → RoomingData
parse/passenger.py     — PassengerList parser → PassengerData
parse/messagelist.py   — MessageList parser → MessageListData (via _MutableMessageListResult)
parse/messagelist_rules.py   — regex constants, remark extraction
parse/messagelist_companion.py — companion group detection
parse/messagelist_fnl.py      — FNL shared block handling
parse/course_code.py   — course code extraction
parse/tour_header.py   — tour header extraction (rule-based only)
```

## Test conventions
- Mirror src structure: `tests/parse/test_messagelist.py` etc.
- Use `lambda _: False` for `remarks_has_banned` in tests unless testing ban logic
- No test file > 300 lines
