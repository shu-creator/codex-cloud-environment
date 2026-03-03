"""Generate golden data for E2E tests. Run manually, not via pytest.

Usage:
    FNL_E2E_FIXTURE_DIR=/path/to/pdfs python tests/e2e/generate_golden.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fnl_builder.config import InputPaths, PipelineConfig  # noqa: E402

_FIXTURES = Path(__file__).parent / "fixtures" / "e417_1008"


def main() -> None:
    fixture_dir_str = os.environ.get("FNL_E2E_FIXTURE_DIR")
    if not fixture_dir_str:
        print("Error: Set FNL_E2E_FIXTURE_DIR to the directory containing E417 PDFs.")
        sys.exit(1)
    fixture_dir = Path(fixture_dir_str)
    rl = fixture_dir / "ルーミングリスト_E417_20261008.pdf"
    pl = fixture_dir / "PSGリスト_E417_20261008.pdf"
    ml = fixture_dir / "MSGリスト_E417_20261008.pdf"
    template = _FIXTURES / "template.xlsx"
    out_xlsx = _FIXTURES / "output.xlsx"

    for f in [rl, pl, ml, template]:
        if not f.exists():
            print(f"Missing: {f}")
            sys.exit(1)

    config = PipelineConfig(
        llm_provider="none",
        input_paths=InputPaths(
            rooming=rl,
            passenger=pl,
            messagelist=ml,
            template=template,
            output=out_xlsx,
        ),
    )
    from fnl_builder.config import RunState
    from fnl_builder.pipeline import integrate_stage, parse_stage, render_stage

    state = RunState.from_config(config)
    parsed, ml_pages = parse_stage(state)
    integrated = integrate_stage(parsed, state, ml_pages=ml_pages)
    render_stage(integrated, state, rooming=parsed.rooming)

    golden = {
        "guest_count": len(integrated.guests),
        "stats": {
            "candidates": integrated.stats.candidates,
            "applied": integrated.stats.applied,
            "fallback": integrated.stats.fallback,
        },
        "guests": [
            {
                "inquiry_main": g.inquiry.main,
                "inquiry_branch": g.inquiry.branch,
                "family_name": g.family_name,
                "given_name": g.given_name,
                "room_type": g.room_type,
                "room_number": g.room_number,
                "passport_no": g.passport_no,
                "course_code": g.course_code,
                "remarks_count": len(g.remarks_parts),
            }
            for g in integrated.guests
        ],
        "issue_count": len(state.issues),
        "issue_codes": sorted({i.code for i in state.issues}),
    }

    golden_path = _FIXTURES / "expected.json"
    golden_path.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Golden data written to {golden_path}")
    print(f"  Guests: {golden['guest_count']}")
    print(f"  Issues: {golden['issue_count']}")
    print(f"  Issue codes: {golden['issue_codes']}")


if __name__ == "__main__":
    main()
