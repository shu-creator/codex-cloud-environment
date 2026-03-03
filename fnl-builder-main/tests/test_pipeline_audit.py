from __future__ import annotations

import json
from pathlib import Path

from fnl_builder.render.audit import write_audit_log
from fnl_builder.shared.types import AuditLog, PipelineCounts


def _make_audit() -> AuditLog:
    return AuditLog(
        started_at="2026-01-01T00:00:00Z",
        input_mode="files",
        input_files_sha256={},
        counts=PipelineCounts(),
    )


def test_audit_extraction_meta_field_default() -> None:
    audit = _make_audit()
    assert audit.extraction_meta == {}


def test_audit_extraction_meta_in_json(tmp_path: Path) -> None:
    audit = _make_audit()
    audit.extraction_meta = {
        "rooming": {
            "method": "pypdf",
            "total_pages": 5,
            "failed_pages": [],
        }
    }
    out = tmp_path / "audit.json"
    write_audit_log(audit, out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["extraction_meta"] == {
        "rooming": {
            "method": "pypdf",
            "total_pages": 5,
            "failed_pages": [],
        }
    }
    assert "llm_extraction" in data


def test_audit_llm_extraction_in_json(tmp_path: Path) -> None:
    audit = _make_audit()
    audit.llm_extraction = {
        "provider": "none",
        "success": False,
        "item_count": 0,
    }
    out = tmp_path / "audit.json"
    write_audit_log(audit, out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["llm_extraction"] == {
        "provider": "none",
        "success": False,
        "item_count": 0,
    }
