from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fnl_builder.shared.types import LLMItem, TourHeaderData


@dataclass(frozen=True)
class PromptConfig:
    system: str
    extract_base: str
    course_supplement: str = ""


class LLMAdapter(Protocol):
    def extract_remarks(self, text: str, pages: list[object], prompts: PromptConfig) -> list[LLMItem]:
        ...

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        ...


class NullAdapter:
    def extract_remarks(self, text: str, pages: list[object], prompts: PromptConfig) -> list[LLMItem]:
        return []

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        return None


class MockAdapter:
    def __init__(self, items: list[LLMItem]) -> None:
        self._items = items

    def extract_remarks(self, text: str, pages: list[object], prompts: PromptConfig) -> list[LLMItem]:
        return self._items

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        return None
