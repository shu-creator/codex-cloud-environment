"""CLI entry point for fnl-builder."""
from __future__ import annotations

import argparse
import sys
import tempfile
from contextlib import ExitStack
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import as_file
from pathlib import Path

from fnl_builder.config import InputPaths, PipelineConfig
from fnl_builder.parse.zip_extract import extract_zip
from fnl_builder.pipeline import run
from fnl_builder.render.excel import default_template_ref
from fnl_builder.shared.errors import FnlError


def _get_version() -> str:
    try:
        return version("fnl-builder")
    except PackageNotFoundError:
        return "unknown"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build final guest list from FNL documents (ZIP or individual files).",
    )
    parser.add_argument(
        "--version", action="version", version=f"fnl-builder {_get_version()}",
    )
    parser.add_argument(
        "--zip", dest="zip_path", type=Path,
        help="FNL ZIP path (alternative to individual files)",
    )
    parser.add_argument(
        "--roominglist", "--rl", dest="roominglist_path", type=Path,
        help="RoomingList PDF path",
    )
    parser.add_argument(
        "--passengerlist", "--pl", dest="passengerlist_path", type=Path,
        help="PassengerList PDF path",
    )
    parser.add_argument(
        "--messagelist", "--ml", dest="messagelist_path", type=Path,
        help="MessageList file path (PDF or CSV)",
    )
    parser.add_argument(
        "--template", dest="template_path", type=Path,
        help="Template Excel file path (default: bundled template)",
    )
    parser.add_argument(
        "--out", dest="out_path", type=Path, required=True,
        help="Output final_list.xlsx path",
    )
    parser.add_argument(
        "--audit", dest="audit_path", type=Path, default=None,
        help="Optional output path for final_list_audit.json",
    )
    parser.add_argument(
        "--llm-provider", choices=["openai", "none", "mock"], default="none",
        help="LLM provider for MessageList extraction (default: none = rule-based only)",
    )
    return parser.parse_args(argv)


def _validate_input_mode(args: argparse.Namespace) -> None:
    """Validate that either --zip or all individual file args are given."""
    has_zip = args.zip_path is not None
    individual_input = [
        args.roominglist_path, args.passengerlist_path,
        args.messagelist_path,
    ]
    has_any = any(f is not None for f in individual_input)

    if has_zip and has_any:
        raise SystemExit(
            "Error: --zip and individual file options are mutually exclusive.",
        )
    if has_zip:
        return
    if not has_any:
        raise SystemExit(
            "Error: Either --zip or all individual file options are required.",
        )
    # Individual mode: rl/pl/ml must all be present
    missing: list[str] = []
    if args.roominglist_path is None:
        missing.append("--roominglist")
    if args.passengerlist_path is None:
        missing.append("--passengerlist")
    if args.messagelist_path is None:
        missing.append("--messagelist")
    if missing:
        raise SystemExit(
            f"Error: Missing required individual file options: {', '.join(missing)}",
        )


def _run_and_check(config: PipelineConfig) -> None:
    result = run(config)
    errors = [i for i in result.audit.issues if i.level == "error"]
    if errors:
        raise SystemExit(
            f"Completed with {len(errors)} error(s); see audit log for details.",
        )


def main(argv: list[str] | None = None) -> None:
    """Parse CLI args, build config, and run the pipeline."""
    args = _parse_args(argv)
    _validate_input_mode(args)

    try:
        with ExitStack() as stack:
            if args.template_path:
                template = args.template_path
            else:
                template = stack.enter_context(as_file(default_template_ref()))

            if args.zip_path:
                tmp = stack.enter_context(tempfile.TemporaryDirectory())
                zip_paths = extract_zip(args.zip_path, Path(tmp))
                paths = InputPaths(
                    rooming=zip_paths.rooming,
                    passenger=zip_paths.passenger,
                    messagelist=zip_paths.messagelist,
                    template=template,
                    output=args.out_path,
                    audit=args.audit_path,
                )
                config = PipelineConfig(
                    llm_provider=args.llm_provider,
                    input_mode="zip",
                    input_paths=paths,
                )
                _run_and_check(config)
            else:
                paths = InputPaths(
                    rooming=args.roominglist_path or Path(),
                    passenger=args.passengerlist_path,
                    messagelist=args.messagelist_path,
                    template=template,
                    output=args.out_path,
                    audit=args.audit_path,
                )
                config = PipelineConfig(
                    llm_provider=args.llm_provider,
                    input_mode="files",
                    input_paths=paths,
                )
                _run_and_check(config)
    except FnlError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
