from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypedDict


class Category(StrEnum):
    MEDICAL = "MEDICAL"
    MEAL = "MEAL"
    MOBILITY = "MOBILITY"
    ANNIVERSARY = "ANNIVERSARY"
    REPEAT = "REPEAT"
    VIP_SENSITIVE = "VIP_SENSITIVE"
    OTHER = "OTHER"


class Phase(StrEnum):
    EXTRACT = "EXTRACT"
    REWRITE = "REWRITE"
    DEPARTURE_AIRPORT = "DEPARTURE_AIRPORT"
    FLIGHT = "FLIGHT"
    ARRIVAL_AIRPORT = "ARRIVAL_AIRPORT"
    TRANSFER = "TRANSFER"
    ON_TOUR = "ON_TOUR"
    HOTEL_STAY = "HOTEL_STAY"
    MEAL_TIME = "MEAL_TIME"
    FREE_TIME_OPTIONAL = "FREE_TIME_OPTIONAL"
    RETURN_TRIP = "RETURN_TRIP"
    PRE_DEPARTURE = "PRE_DEPARTURE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning", "info"]
    code: str
    message: str


@dataclass(frozen=True)
class LLMItem:
    category: Category
    who_id: str
    confidence: float
    phase: Phase
    handoff_text: str
    evidence_quote: str
    summary: str = ""
    evidence_page: int | None = None


@dataclass(frozen=True)
class RewriteStats:
    candidates: int = 0
    applied: int = 0
    fallback: int = 0


@dataclass
class PipelineCounts:
    total_guests: int = 0
    matched: int = 0
    unmatched: int = 0


class LLMExtractionMeta(TypedDict, total=False):
    """LLM extraction stage metadata recorded in the audit log."""

    provider: Literal["none", "openai", "mock"]
    success: bool
    item_count: int


@dataclass
class AuditLog:
    """Pipeline execution audit log.

    Captures timing, input fingerprints, LLM extraction metadata,
    guest counts, and any issues encountered during the run.
    """

    started_at: str
    input_mode: str
    input_files_sha256: dict[str, str]
    extraction_meta: dict[str, object] = field(default_factory=dict)
    llm_extraction: LLMExtractionMeta | None = None
    counts: PipelineCounts = field(default_factory=PipelineCounts)
    issues: list[Issue] = field(default_factory=list)


@dataclass(frozen=True)
class InquiryKey:
    main: str
    branch: str | None = None

    def normalized(self) -> str:
        return f"{self.main}-{self.branch}" if self.branch else self.main


@dataclass(frozen=True)
class PassportRecord:
    passport_no: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    full_name: str | None = None
    family_name: str | None = None
    given_name: str | None = None


@dataclass
class GuestRecord:
    """A single guest after integration of rooming, passenger, and message list data."""

    inquiry: InquiryKey
    full_name: str
    family_name: str
    given_name: str
    room_type: str | None = None
    room_number: str | None = None
    room_group_id: str | None = None
    group_id: str | None = None
    passport_no: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    remarks_parts: list[str] = field(default_factory=list)
    course_code: str | None = None


@dataclass(frozen=True)
class RoomingData:
    tour_ref: str | None = None
    tour_name: str | None = None
    depart_date: str | None = None
    return_date: str | None = None
    declared_total_pax: int | None = None
    declared_rooms_text: str | None = None
    declared_rooms_by_type: dict[str, int] = field(default_factory=dict)
    guests: list[GuestRecord] = field(default_factory=list)
    notes_by_inquiry: dict[str, list[str]] = field(default_factory=dict)
    group_ids_by_inquiry: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> RoomingData:
        return cls()


@dataclass(frozen=True)
class PassengerData:
    guests_by_inquiry: dict[str, list[PassportRecord]] = field(default_factory=dict)
    flags_by_inquiry: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> PassengerData:
        return cls()


@dataclass(frozen=True)
class MessageListData:
    remarks_by_inquiry: dict[str, list[str]] = field(default_factory=dict)
    remarks_by_inquiry_guest: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    course_by_inquiry: dict[str, str] = field(default_factory=dict)
    companion_groups: dict[str, set[str]] = field(default_factory=dict)
    fnl_check_required_by_guest: dict[tuple[str, str], int] = field(default_factory=dict)
    fnl_shared_meta_stripped_count: int = 0

    @classmethod
    def empty(cls) -> MessageListData:
        return cls()


@dataclass(frozen=True)
class TourHeaderData:
    tour_ref: str | None = None
    tour_name: str | None = None
    depart_date: str | None = None
    return_date: str | None = None
    confidence: float = 0.0

    @classmethod
    def empty(cls) -> TourHeaderData:
        return cls()


@dataclass(frozen=True)
class RoomMergeInfo:
    inquiries: frozenset[str]
    room_type: str | None = None
    source: str = "rule_id"
    confidence: float | None = None


@dataclass
class NameRoomCandidate:
    candidate_id: int
    line_no: int
    line_text: str
    name_a: str
    name_b: str
    room_type: str | None
    context_inquiry: str | None
    aliases_by_name: dict[str, set[str]]
    aliases_by_name_global: dict[str, dict[str, set[str]]]


@dataclass(frozen=True)
class NameMergeStats:
    candidates: int = 0
    rule_resolved: int = 0
    llm_resolved: int = 0
    unresolved: int = 0


class NameResolution(TypedDict):
    """LLM name-based room resolution output."""

    candidate_id: int
    inquiry_a: str | None
    inquiry_b: str | None
    room_type: str | None
    confidence: float


@dataclass(frozen=True)
class ParseResult:
    rooming: RoomingData
    passenger: PassengerData
    messagelist: MessageListData
    tour_header: TourHeaderData


@dataclass(frozen=True)
class IntegrationResult:
    guests: list[GuestRecord]
    companion_groups: dict[str, set[str]]
    stats: RewriteStats


@dataclass(frozen=True)
class RenderResult:
    """Final pipeline output: path to generated Excel and the audit log."""

    output_path: Path
    audit: AuditLog
