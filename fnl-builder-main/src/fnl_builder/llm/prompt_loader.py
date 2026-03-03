"""Prompt loading and course-code resolution for LLM extraction."""
from __future__ import annotations

import re
from importlib import resources
from fnl_builder.llm.adapter import PromptConfig

_PROMPTS_PKG = "fnl_builder.llm.prompts"
_COURSE_NUMBER_RE = re.compile(r"^[A-Za-z]{1,3}(\d+)")


def _read_resource(package: str, filename: str) -> str:
    """Read a text resource file from the given package."""
    ref = resources.files(package).joinpath(filename)
    return ref.read_text(encoding="utf-8")


def _extract_course_number(code: str) -> str | None:
    """Extract the numeric part from a course code after the letter prefix.

    E417 -> 417, ET470 -> 470, EH417 -> 417, E417Z -> 417
    """
    m = _COURSE_NUMBER_RE.search(code)
    return m.group(1) if m else None


def _load_course_supplement(course_codes: list[str]) -> str:
    """Load and merge course-specific prompt supplements.

    Resolution:
    1. Extract trailing digits from each course code
    2. Look for courses/{number}.md for each unique number
    3. Merge found files in ascending number order (deduplicate lines)
    4. If no course file found, fall back to courses/_default.md
    """
    numbers: set[str] = set()
    for code in course_codes:
        num = _extract_course_number(code)
        if num:
            numbers.add(num)

    courses_pkg = f"{_PROMPTS_PKG}.courses"
    found_texts: list[tuple[int, str]] = []

    for num in numbers:
        filename = f"{num}.md"
        try:
            text = _read_resource(courses_pkg, filename)
            found_texts.append((int(num), text))
        except (FileNotFoundError, TypeError):
            continue

    if not found_texts:
        return _read_resource(courses_pkg, "_default.md")

    found_texts.sort(key=lambda t: t[0])

    seen_lines: set[str] = set()
    merged_lines: list[str] = []
    for _, text in found_texts:
        for line in text.splitlines():
            if line not in seen_lines:
                seen_lines.add(line)
                merged_lines.append(line)

    return "\n".join(merged_lines)


def load_taxonomy() -> str:
    """Load the taxonomy YAML."""
    return _read_resource(_PROMPTS_PKG, "taxonomy.yaml")


def load_prompts(course_codes: list[str] | None = None) -> PromptConfig:
    """Load prompt assets and build a PromptConfig.

    Args:
        course_codes: Course codes found in the PDF (e.g. ["E417", "ET470"]).
            Used to resolve course-specific prompt supplements.
    """
    system = _read_resource(_PROMPTS_PKG, "base_system.txt")
    extract_base = _read_resource(_PROMPTS_PKG, "base_extract.md")
    course_supplement = _load_course_supplement(course_codes or [])
    return PromptConfig(
        system=system,
        extract_base=extract_base,
        course_supplement=course_supplement,
    )
