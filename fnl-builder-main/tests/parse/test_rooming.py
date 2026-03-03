from __future__ import annotations

from fnl_builder.parse.rooming import parse_rooming_list


class TestParseRoomingList:
    def test_extracts_name_from_line_start(self) -> None:
        text = """E417 26-10-27 ～26-11-05
1 MATSUMOTO CHIAKI 0067368202-001 TWN A
2 SUZUKI TARO 0067368203-001 TWN 101
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 2
        assert result.guests[0].family_name == "MATSUMOTO"
        assert result.guests[0].given_name == "CHIAKI"
        assert result.guests[1].family_name == "SUZUKI"
        assert result.guests[1].given_name == "TARO"

    def test_japanese_line_preserves_given_name(self) -> None:
        """Given name must not be eaten as room number when Japanese chars follow."""
        text = """E417Z 26-10-27 ～26-11-05
1 MR. HANKYU TARO 阪急 太郎 A 26 日本 TWN HK 01-09 0067368202 A A
2 MS. KOBAYASHI HIDEKO 小林 秀子 A 75 日本 TWN MK 12-20 0067210265 A A
3 MR. UMEDA HAJIME 梅田 一 A 24 日本 TWN HK 01-14 0067421418 A A
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 3
        assert result.guests[0].full_name == "MR. HANKYU TARO"
        assert result.guests[0].family_name == "HANKYU"
        assert result.guests[0].given_name == "TARO"
        assert result.guests[1].full_name == "MS. KOBAYASHI HIDEKO"
        assert result.guests[1].family_name == "KOBAYASHI"
        assert result.guests[1].given_name == "HIDEKO"
        assert result.guests[2].full_name == "MR. UMEDA HAJIME"
        assert result.guests[2].family_name == "UMEDA"
        assert result.guests[2].given_name == "HAJIME"

    def test_same_inquiry_with_mixed_room_types_gets_separate_room_groups(self) -> None:
        text = """E417Z 26-10-27 ～26-11-05
1 MR. HANKYU TARO 阪急 太郎 A 68 日本 SGL HK 01-09 0067368202 A A
2 MS. HANKYU HANAKO 阪急 花子 A 30 日本 TWN HK 01-09 0067368202 A A
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 2
        assert result.guests[0].room_type == "SGL"
        assert result.guests[1].room_type == "TWN"
        assert result.guests[0].room_group_id != result.guests[1].room_group_id

    def test_split_rooming_line_merges_inquiry(self) -> None:
        """Split lines (room type + inquiry on next line) should still parse."""
        text = """E417Z 26-10-27 ～26-11-05
MR. HANKYU TARO 阪急 太郎 26 日本 TWN HK 01-09 A
0067368202 A 関西国際空港
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 1
        assert result.guests[0].full_name == "MR. HANKYU TARO"
        assert result.guests[0].family_name == "HANKYU"
        assert result.guests[0].given_name == "TARO"

    def test_split_rooming_line_merges_with_intermediate_companion_markers(self) -> None:
        """同行/GRP lines between split rows must not break inquiry merge."""
        text = """E417Z 26-10-27 ～26-11-05
MR. ALPHA TARO アルファ 太郎 26 日本 TWN HK 01-09 A
同行
GRP
0012345678 A 関西国際空港
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 1
        guest = result.guests[0]
        assert guest.inquiry.main == "0012345678"
        assert guest.full_name == "MR. ALPHA TARO"

    def test_split_rooming_line_merges_with_companion_grp_variants(self) -> None:
        """Marker variants like 同行 GRP or 同行ＧＲＰ有 should keep pending rows."""
        text = """E417Z 26-10-27 ～26-11-05
MR. ALPHA TARO アルファ 太郎 26 日本 TWN HK 01-09 A
同行 GRP
同行ＧＲＰ有
0012345678 A 関西国際空港
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 1
        guest = result.guests[0]
        assert guest.inquiry.main == "0012345678"
        assert guest.full_name == "MR. ALPHA TARO"

    def test_split_rooming_line_with_grp_token_in_inquiry_line_is_not_dropped(self) -> None:
        """Inquiry lines that include GRP-like tokens must still merge with pending."""
        text = """E417Z 26-10-27 ～26-11-05
MR. ALPHA TARO アルファ 太郎 26 日本 TWN HK 01-09 A
0012345678 A GRP01 関西国際空港
"""
        result = parse_rooming_list(text)
        assert len(result.guests) == 1
        guest = result.guests[0]
        assert guest.inquiry.main == "0012345678"
        assert guest.full_name == "MR. ALPHA TARO"

    def test_extracts_headers_notes_groups_and_course_code(self) -> None:
        text = """E417Z 26-10-27 ～26-11-05
ADT - 2
Note: 0067368202-001 糖尿病あり
同行 0067368202-001 0067368203-001
1 MATSUMOTO CHIAKI 0067368202-001 TWN A
2 SUZUKI TARO 0067368203-001 TWN 101
"""
        result = parse_rooming_list(text)
        assert result.tour_ref == "E417Z 1027"
        assert result.depart_date == "2026-10-27"
        assert result.notes_by_inquiry["0067368202-001"] == ["糖尿病あり"]
        assert result.group_ids_by_inquiry["0067368202-001"] == "GRP01"
        assert result.group_ids_by_inquiry["0067368203-001"] == "GRP01"
        assert len(result.guests) == 2
        assert result.guests[0].course_code == "E417Z"
        assert result.guests[1].course_code == "E417Z"
        assert result.guests[0].group_id == "GRP01"
        assert result.guests[1].group_id == "GRP01"

    def test_extracts_tour_ref_when_course_header_has_leading_spaces(self) -> None:
        text = """  E417Z 26-10-27 ～26-11-05
  E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS
ADT - 1
1 MATSUMOTO CHIAKI 0067368202-001 TWN A
"""
        result = parse_rooming_list(text)
        assert result.tour_ref == "E417Z 1027"
        assert result.tour_name == "E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS"
