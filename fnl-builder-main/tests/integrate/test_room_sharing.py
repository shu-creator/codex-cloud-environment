from __future__ import annotations

from fnl_builder.integrate import room_sharing
from fnl_builder.shared.types import GuestRecord, InquiryKey


def _make_guest(
    *,
    inquiry_main: str = "67368202",
    full_name: str = "山田 太郎",
    family_name: str = "山田",
    given_name: str = "太郎",
    room_type: str | None = "TWN",
    room_group_id: str | None = "R1",
    room_number: str | None = None,
    remarks_parts: list[str] | None = None,
) -> GuestRecord:
    return GuestRecord(
        inquiry=InquiryKey(main=inquiry_main),
        full_name=full_name,
        family_name=family_name,
        given_name=given_name,
        room_type=room_type,
        room_group_id=room_group_id,
        room_number=room_number,
        remarks_parts=remarks_parts if remarks_parts is not None else [],
    )


def test_is_tour_conductor() -> None:
    tc_guest = _make_guest(full_name="T/C 佐藤 花子")
    japanese_tc_guest = _make_guest(full_name="佐藤 花子", remarks_parts=["添乗員"])
    normal_guest = _make_guest(full_name="山田 太郎", remarks_parts=["一般参加者"])

    assert room_sharing.is_tour_conductor(tc_guest)
    assert room_sharing.is_tour_conductor(japanese_tc_guest)
    assert not room_sharing.is_tour_conductor(normal_guest)


def test_convert_sgl_to_tsu() -> None:
    sgl_guest = _make_guest(room_type="SGL")
    tc_guest = _make_guest(room_type="SGL", remarks_parts=["添乗員"])
    twn_guest = _make_guest(room_type="TWN")
    guests = [sgl_guest, tc_guest, twn_guest]

    room_sharing.convert_sgl_to_tsu(guests)

    assert sgl_guest.room_type == "TSU"
    assert tc_guest.room_type == "SGL"
    assert twn_guest.room_type == "TWN"


def test_assign_room_numbers() -> None:
    guests = [
        _make_guest(room_type="TWN", room_group_id="R1"),
        _make_guest(room_type="TWN", room_group_id="R2"),
        _make_guest(room_type="SGL", room_group_id="R3"),
        _make_guest(room_type="TWN", room_group_id="R2"),
    ]

    room_sharing.assign_room_numbers(guests)

    assert guests[0].room_number == "1"
    assert guests[1].room_number == "2"
    assert guests[2].room_number == "1"
    assert guests[3].room_number is None


def test_build_same_room_note() -> None:
    guest = _make_guest(inquiry_main="0067368202", full_name="山田 太郎", room_type="TWN")
    roommate = _make_guest(
        inquiry_main="67368203",
        full_name="佐藤 花子",
        family_name="佐藤",
        given_name="花子",
        room_type="TWN",
        room_group_id="R1",
    )

    note = room_sharing._build_same_room_note(guest, [guest, roommate])

    assert note == "[同室] 佐藤 花子様とTWN同室"


def test_apply_same_room_notes() -> None:
    g1 = _make_guest(inquiry_main="0067368202", room_group_id="R1", room_type="TWN")
    g2 = _make_guest(
        inquiry_main="67368203",
        full_name="佐藤 花子",
        family_name="佐藤",
        given_name="花子",
        room_group_id="R1",
        room_type="TWN",
    )
    room_groups = {"R1": [g1, g2]}

    room_sharing._apply_same_room_notes(room_groups)

    assert g1.remarks_parts[0] == "[同室] 佐藤 花子様とTWN同室"
    assert g2.remarks_parts[0] == "[同室] 山田 太郎様とTWN同室"


def test_add_room_sharing_remarks_full() -> None:
    g1 = _make_guest(
        inquiry_main="0067368202",
        full_name="山田 太郎",
        family_name="山田",
        given_name="太郎",
        room_type="TWN",
        room_group_id="R1",
        room_number="1",
    )
    g2 = _make_guest(
        inquiry_main="67368203",
        full_name="佐藤 花子",
        family_name="佐藤",
        given_name="花子",
        room_type="TWN",
        room_group_id="R1",
        room_number="1",
    )
    g3 = _make_guest(
        inquiry_main="67368204",
        full_name="田中 一郎",
        family_name="田中",
        given_name="一郎",
        room_type="SGL",
        room_group_id="R2",
        room_number="2",
    )
    guests = [g1, g2, g3]
    companion_groups = {
        "67368202": {"67368202", "67368204"},
        "67368203": {"67368203"},
        "67368204": {"67368204", "67368202"},
    }

    room_sharing.add_room_sharing_remarks(guests, companion_groups)

    assert g1.remarks_parts[0] == "[同室] 佐藤 花子様とTWN同室"
    assert g1.remarks_parts[1] == "[同行GRP別室] 田中 一郎様(SGL/No.2)"
    assert g2.remarks_parts == ["[同室] 山田 太郎様とTWN同室"]
    assert g3.remarks_parts[0] == "[同行GRP別室] 山田 太郎様(TWN/No.1)"


def test_collect_companions_in_other_rooms() -> None:
    me = _make_guest(
        inquiry_main="67368202",
        full_name="山田 太郎",
        family_name="山田",
        given_name="太郎",
        room_group_id="R1",
    )
    c1 = _make_guest(
        inquiry_main="67368203",
        full_name="佐藤 花子",
        family_name="佐藤",
        given_name="花子",
        room_type="TWN",
        room_group_id="R2",
    )
    c2 = _make_guest(
        inquiry_main="67368204",
        full_name="鈴木 次郎",
        family_name="鈴木",
        given_name="次郎",
        room_type="SGL",
        room_group_id="R1",
    )
    guests_by_inquiry = {
        "67368203": [c1],
        "67368204": [c2],
    }
    room_group_info = {
        "R2": ("TWN", "3"),
    }

    companion_names = room_sharing._collect_companions_in_other_rooms(
        me,
        {"67368203", "67368204"},
        guests_by_inquiry,
        room_group_info,
    )

    assert companion_names == ["佐藤 花子様(TWN/No.3)"]
