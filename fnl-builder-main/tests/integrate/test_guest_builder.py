from __future__ import annotations

from fnl_builder.integrate import guest_builder
from fnl_builder.shared.types import GuestRecord, InquiryKey, Issue, PassportRecord, RewriteStats


def _make_guest(
    *,
    inquiry_main: str = "0067368202",
    inquiry_branch: str | None = None,
    full_name: str = "山田 太郎",
    family_name: str = "山田",
    given_name: str = "太郎",
    room_type: str | None = "TWN",
    room_group_id: str | None = "R1",
    remarks_parts: list[str] | None = None,
) -> GuestRecord:
    return GuestRecord(
        inquiry=InquiryKey(main=inquiry_main, branch=inquiry_branch),
        full_name=full_name,
        family_name=family_name,
        given_name=given_name,
        room_type=room_type,
        room_group_id=room_group_id,
        remarks_parts=remarks_parts if remarks_parts is not None else [],
    )


def test_build_guest_integration_state() -> None:
    guests = [
        _make_guest(inquiry_main="0067368202"),
        _make_guest(inquiry_main="0067368202"),
        _make_guest(inquiry_main="0067368203"),
    ]

    state = guest_builder._build_guest_integration_state(guests)

    assert state.guest_count_by_main == {"0067368202": 2, "0067368203": 1}
    assert state.guest_index_by_match_key == {}
    assert state.guest_position_by_main == {}


def test_resolve_guest_position() -> None:
    state = guest_builder.GuestIntegrationState(guest_count_by_main={"0067368202": 2})
    guest1 = _make_guest(inquiry_main="0067368202")
    guest2 = _make_guest(inquiry_main="0067368202", inquiry_branch="002")

    key1 = guest_builder._resolve_guest_position(guest1, state)
    key2 = guest_builder._resolve_guest_position(guest2, state)

    assert key1 == ("67368202", "1")
    assert key2 == ("67368202", "2")


def test_process_integrate_guest_data_basic() -> None:
    guest = _make_guest(inquiry_main="0067368202", room_type="TWN", room_group_id="RG1")
    guests_out: list[GuestRecord] = []
    issues: list[Issue] = []

    stats = guest_builder.process_integrate_guest_data(
        rooming_guests=[guest],
        rooming_notes_by_inquiry={"67368202": ["[rooming] 窓側希望"]},
        passenger_flags_by_inquiry={"67368202": ["[flag] PPT未"]},
        passenger_guests_by_inquiry={
            "67368202": [
                PassportRecord(
                    passport_no="TK1234567",
                    issue_date="2020-01-01",
                    expiry_date="2030-01-01",
                    full_name="YAMADA TARO",
                    family_name="YAMADA",
                    given_name="TARO",
                )
            ]
        },
        remarks_by_inquiry={},
        remarks_by_inquiry_guest={("67368202", "1"): ["[hotel] 高層階希望"]},
        course_by_inquiry={"67368202": "A1"},
        llm_notes_by_guest={},
        llm_items_by_guest={},
        llm_extraction_success=False,
        issues=issues,
        guests_out=guests_out,
        remarks_has_banned=lambda _: False,
    )

    assert stats == RewriteStats(candidates=1, applied=0, fallback=1)
    assert len(issues) == 0
    assert len(guests_out) == 1
    integrated = guests_out[0]
    assert integrated.passport_no == "TK1234567"
    assert integrated.full_name == "YAMADA TARO"
    assert integrated.course_code == "A1"
    assert "[rooming] 窓側希望" in integrated.remarks_parts
    assert "[hotel] 高層階希望" in integrated.remarks_parts
    assert all("PPT未" not in part for part in integrated.remarks_parts)


def test_remarks_by_inquiry_fallback() -> None:
    """When remarks_by_inquiry_guest is empty, remarks_by_inquiry should be used."""
    guest = _make_guest(inquiry_main="0067368202", room_type="TWN", room_group_id="RG1")
    guests_out: list[GuestRecord] = []
    issues: list[Issue] = []

    guest_builder.process_integrate_guest_data(
        rooming_guests=[guest],
        rooming_notes_by_inquiry={},
        passenger_flags_by_inquiry={},
        passenger_guests_by_inquiry={},
        remarks_by_inquiry={"67368202": ["[msg] 病人情報あり", "[msg] 食事リクエスト"]},
        remarks_by_inquiry_guest={},
        course_by_inquiry={},
        llm_notes_by_guest={},
        llm_items_by_guest={},
        llm_extraction_success=False,
        issues=issues,
        guests_out=guests_out,
        remarks_has_banned=lambda _: False,
    )

    assert len(guests_out) == 1
    # "msg" is not in _RULE_LABEL_TO_CATEGORY → falls back to "other",
    # and content-based refinement does not promote these → relabeled [other].
    assert "[other] 病人情報あり" in guests_out[0].remarks_parts
    assert "[other] 食事リクエスト" in guests_out[0].remarks_parts


def test_process_post_room_grouping() -> None:
    g_sgl = _make_guest(
        inquiry_main="0067368204",
        full_name="田中 一郎",
        family_name="田中",
        given_name="一郎",
        room_type="SGL",
        room_group_id="R2",
    )
    g_a = _make_guest(
        inquiry_main="0067368202",
        full_name="山田 太郎",
        family_name="山田",
        given_name="太郎",
        room_type="TWN",
        room_group_id="R1",
    )
    g_b = _make_guest(
        inquiry_main="0067368203",
        full_name="佐藤 花子",
        family_name="佐藤",
        given_name="花子",
        room_type="TWN",
        room_group_id="R1",
    )
    guests = [g_sgl, g_b, g_a]
    companion_groups = {
        "67368202": {"67368202", "67368204"},
        "67368204": {"67368204", "67368202"},
    }

    guest_builder.process_post_room_grouping(guests=guests, companion_groups=companion_groups)

    assert guests[0].room_group_id == "R1"
    assert guests[1].room_group_id == "R1"
    assert guests[2].room_group_id == "R2"
    assert g_sgl.room_type == "TSU"
    assert {g_a.room_number, g_b.room_number} == {"1", None}
    assert g_sgl.room_number == "1"
    assert any(part.startswith("[同室]") for part in g_a.remarks_parts)
    assert any(part.startswith("[同行GRP別室]") for part in g_a.remarks_parts)


def test_companion_group_sort_adjacency() -> None:
    """Guests in the same companion group (different rooms) should be adjacent."""
    g1 = _make_guest(
        inquiry_main="0067621009",
        full_name="HANKYU HANAKO",
        family_name="HANKYU",
        given_name="HANAKO",
        room_type="TWN",
        room_group_id="R1",
    )
    g2 = _make_guest(
        inquiry_main="0067621010",
        full_name="HANSHIN HACHIRO",
        family_name="HANSHIN",
        given_name="HACHIRO",
        room_type="TWN",
        room_group_id="R2",
    )
    g3 = _make_guest(
        inquiry_main="0067621040",
        full_name="HANKYU NAGOYA",
        family_name="HANKYU",
        given_name="NAGOYA",
        room_type="TWN",
        room_group_id="R3",
    )
    guests = [g2, g3, g1]
    companion_groups = {
        "67621009": {"67621009", "67621040"},
        "67621040": {"67621040", "67621009"},
    }

    guest_builder.process_post_room_grouping(guests=guests, companion_groups=companion_groups)

    names = [g.full_name for g in guests]
    idx_hanako = names.index("HANKYU HANAKO")
    idx_nagoya = names.index("HANKYU NAGOYA")
    idx_hanshin = names.index("HANSHIN HACHIRO")
    assert abs(idx_hanako - idx_nagoya) == 1, (
        f"Companion group members should be adjacent: HANAKO@{idx_hanako}, NAGOYA@{idx_nagoya}"
    )
    assert idx_hanshin != idx_hanako - 1 and idx_hanshin != idx_hanako + 1 or idx_hanshin == idx_nagoya + 1 or idx_hanshin == idx_nagoya - 1, (
        "Non-companion guest should not be between companion members"
    )


def test_companion_sort_no_companions_unchanged() -> None:
    """Without companion groups, sort order should be by room_group min inquiry."""
    g_a = _make_guest(inquiry_main="0067368205", room_type="TWN", room_group_id="R2")
    g_b = _make_guest(inquiry_main="0067368202", room_type="TWN", room_group_id="R1")
    guests = [g_a, g_b]

    guest_builder.process_post_room_grouping(guests=guests, companion_groups={})

    assert guests[0].inquiry.main == "0067368202"
    assert guests[1].inquiry.main == "0067368205"


def test_substitute_inquiry_refs_with_names() -> None:
    """Inquiry number references in remarks should be replaced with names."""
    g1 = _make_guest(
        inquiry_main="0067621010",
        inquiry_branch="001",
        full_name="HANSHIN HACHIRO",
        family_name="HANSHIN",
        given_name="HACHIRO",
        room_type="TWN",
        room_group_id="R1",
        remarks_parts=["[hotel] 0067621010-001は、エレベーター近くの部屋希望"],
    )
    g2 = _make_guest(
        inquiry_main="0067621011",
        inquiry_branch="001",
        full_name="HANSHIN TORAKO",
        family_name="HANSHIN",
        given_name="TORAKO",
        room_type="TWN",
        room_group_id="R1",
        remarks_parts=["[other] 0067621011-001は#67621010と同室"],
    )
    guests = [g1, g2]

    guest_builder.process_post_room_grouping(guests=guests, companion_groups={})

    all_remarks_g1 = "\n".join(guests[0].remarks_parts)
    all_remarks_g2 = "\n".join(guests[1].remarks_parts)
    assert "HANSHIN HACHIRO様は、エレベーター近くの部屋希望" in all_remarks_g1
    assert "0067621010-001" not in all_remarks_g1
    assert "HANSHIN TORAKO様は" in all_remarks_g2
    assert "HANSHIN HACHIRO様と同室" in all_remarks_g2


def test_substitute_skips_ambiguous_inquiry() -> None:
    """Short inquiry ref should NOT be replaced when multiple guests share the inquiry."""
    g1 = _make_guest(
        inquiry_main="0067621010",
        inquiry_branch="001",
        full_name="HANSHIN HACHIRO",
        family_name="HANSHIN",
        given_name="HACHIRO",
        room_type="TWN",
        room_group_id="R1",
    )
    g2 = _make_guest(
        inquiry_main="0067621010",
        inquiry_branch="002",
        full_name="HANSHIN TORAKO",
        family_name="HANSHIN",
        given_name="TORAKO",
        room_type="TWN",
        room_group_id="R1",
        remarks_parts=["[other] #67621010参照"],
    )
    guests = [g1, g2]

    guest_builder.process_post_room_grouping(guests=guests, companion_groups={})

    assert "#67621010参照" in guests[1].remarks_parts[0]


def test_substitute_full_who_id_works_with_multiple_guests() -> None:
    """Full who_id (with branch) should still resolve even when inquiry has multiple guests."""
    g1 = _make_guest(
        inquiry_main="0067621010",
        inquiry_branch="001",
        full_name="HANSHIN HACHIRO",
        family_name="HANSHIN",
        given_name="HACHIRO",
        room_type="TWN",
        room_group_id="R1",
        remarks_parts=["[other] 0067621010-002はアレルギーあり"],
    )
    g2 = _make_guest(
        inquiry_main="0067621010",
        inquiry_branch="002",
        full_name="HANSHIN TORAKO",
        family_name="HANSHIN",
        given_name="TORAKO",
        room_type="TWN",
        room_group_id="R1",
    )
    guests = [g1, g2]

    guest_builder.process_post_room_grouping(guests=guests, companion_groups={})

    assert "HANSHIN TORAKO様はアレルギーあり" in guests[0].remarks_parts[0]


def test_substitute_branchless_duplicate_skips_full_id() -> None:
    """When multiple branchless guests share an inquiry, full-ID substitution should be skipped."""
    g1 = _make_guest(
        inquiry_main="0067621012",
        full_name="HANKYU OKOTARO",
        family_name="HANKYU",
        given_name="OKOTARO",
        room_type="TWN",
        room_group_id="R1",
        remarks_parts=["[vip] 0067621012-001は重要顧客"],
    )
    g2 = _make_guest(
        inquiry_main="0067621012",
        full_name="HABISU ENTO",
        family_name="HABISU",
        given_name="ENTO",
        room_type="TWN",
        room_group_id="R1",
    )
    guests = [g1, g2]

    guest_builder.process_post_room_grouping(guests=guests, companion_groups={})

    all_remarks = "\n".join(guests[0].remarks_parts)
    assert "0067621012-001は重要顧客" in all_remarks
