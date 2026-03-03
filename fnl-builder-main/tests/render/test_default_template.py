"""Tests for bundled default template."""
from __future__ import annotations

from importlib.resources import as_file

from fnl_builder.render.excel import default_template_ref


def test_default_template_ref_readable() -> None:
    with as_file(default_template_ref()) as p:
        assert p.exists()
        assert p.stat().st_size > 0
        assert p.suffix == ".xlsx"
