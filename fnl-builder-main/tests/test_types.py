from __future__ import annotations

from fnl_builder.shared.types import (
    GuestRecord,
    InquiryKey,
    MessageListData,
    ParseResult,
    PassengerData,
    PassportRecord,
    RoomingData,
    TourHeaderData,
)


def test_inquiry_key_normalized() -> None:
    assert InquiryKey("123", "001").normalized() == "123-001"


def test_inquiry_key_no_branch() -> None:
    assert InquiryKey("123").normalized() == "123"


def test_rooming_data_empty() -> None:
    data = RoomingData.empty()
    assert isinstance(data, RoomingData)
    assert data.guests == []


def test_passenger_data_empty() -> None:
    data = PassengerData.empty()
    assert isinstance(data, PassengerData)
    assert data.guests_by_inquiry == {}


def test_messagelist_data_empty() -> None:
    data = MessageListData.empty()
    assert isinstance(data, MessageListData)
    assert data.remarks_by_inquiry == {}


def test_tour_header_data_empty() -> None:
    data = TourHeaderData.empty()
    assert isinstance(data, TourHeaderData)
    assert data.confidence == 0.0


def test_parse_result_with_empties() -> None:
    result = ParseResult(
        rooming=RoomingData.empty(),
        passenger=PassengerData.empty(),
        messagelist=MessageListData.empty(),
        tour_header=TourHeaderData.empty(),
    )
    assert isinstance(result, ParseResult)
    assert result.rooming.guests == []


def test_passport_record_defaults() -> None:
    record = PassportRecord()
    assert record.passport_no is None
    assert record.issue_date is None
    assert record.expiry_date is None
    assert record.full_name is None
    assert record.family_name is None
    assert record.given_name is None


def test_guest_record_mutable() -> None:
    guest = GuestRecord(
        inquiry=InquiryKey("123", "001"),
        full_name="John Doe",
        family_name="Doe",
        given_name="John",
    )
    guest.remarks_parts.append("note")
    assert guest.remarks_parts == ["note"]
