from __future__ import annotations

from fnl_builder.parse.passenger import parse_passenger_list


class TestParsePassengerList:
    def test_extracts_guest_info(self) -> None:
        """Test basic guest info extraction (passport + name combined)."""
        text = """0067368202
01,JAN,2000 TS1234567 01,OCT,2020
A (26) 01,OCT,2030
MR. HANKYU TARO
JAPAN"""
        result = parse_passenger_list(text)
        assert "0067368202" in result.guests_by_inquiry
        info = result.guests_by_inquiry["0067368202"][0]
        assert info.passport_no == "TS1234567"
        assert info.issue_date == "2020-10-01"
        assert info.expiry_date == "2030-10-01"
        assert info.full_name == "MR. HANKYU TARO"
        assert info.family_name == "HANKYU"
        assert info.given_name == "TARO"

    def test_ppt_missing_flag(self) -> None:
        """Test PPT未 flag is set for guests without passport."""
        text = """0067368305
01,JUL,2004 1
A (22)
MR. HANSHIN JIRO
JAPAN"""
        result = parse_passenger_list(text)
        assert "0067368305" in result.guests_by_inquiry
        assert result.guests_by_inquiry["0067368305"][0].passport_no is None
        assert "0067368305" in result.flags_by_inquiry
        assert "PPT未" in result.flags_by_inquiry["0067368305"]

    def test_year_not_parsed_as_inquiry(self) -> None:
        """Test that years like 2000, 2030 are not treated as inquiry numbers."""
        text = """0067368202
01,JAN,2000 TS1234567 01,OCT,2020
A (26) 01,OCT,2030
MR. HANKYU TARO"""
        result = parse_passenger_list(text)
        assert "0067368202" in result.guests_by_inquiry
        assert "2000" not in result.guests_by_inquiry
        assert "2020" not in result.guests_by_inquiry
        assert "2030" not in result.guests_by_inquiry

    def test_multiple_guests_same_inquiry(self) -> None:
        """Test multiple guests with same inquiry number get separate records."""
        text = """0067421418
01,NOV,2002 TS3456789 2
A (23)
MS. UMEDA YOSHIKO
JAPAN
0067421418
01,JUN,2002 TS3456788 3
A (24)
MR. UMEDA HAJIME
JAPAN"""
        result = parse_passenger_list(text)
        assert "0067421418" in result.guests_by_inquiry
        guests = result.guests_by_inquiry["0067421418"]
        assert len(guests) == 2
        assert guests[0].passport_no == "TS3456789"
        assert guests[0].family_name == "UMEDA"
        assert guests[0].given_name == "YOSHIKO"
        assert guests[1].passport_no == "TS3456788"
        assert guests[1].family_name == "UMEDA"
        assert guests[1].given_name == "HAJIME"

    def test_branch_inquiry_separate_guests(self) -> None:
        """Test guests with branch inquiry numbers (12345-1, 12345-2) get separate records."""
        text = """0067368202-1
01,JAN,1980 TS1111111 01,OCT,2020
A (45) 01,OCT,2030
MR. TANAKA TARO
JAPAN
0067368202-2
01,FEB,1985 TS2222222 01,NOV,2021
A (40) 01,NOV,2031
MS. TANAKA HANAKO
JAPAN"""
        result = parse_passenger_list(text)
        assert "0067368202-1" in result.guests_by_inquiry
        assert "0067368202-2" in result.guests_by_inquiry
        assert len(result.guests_by_inquiry["0067368202-1"]) == 1
        assert len(result.guests_by_inquiry["0067368202-2"]) == 1
        guest1 = result.guests_by_inquiry["0067368202-1"][0]
        guest2 = result.guests_by_inquiry["0067368202-2"][0]
        assert guest1.passport_no == "TS1111111"
        assert guest2.passport_no == "TS2222222"
        assert guest1.family_name == "TANAKA"
        assert guest1.given_name == "TARO"
        assert guest2.family_name == "TANAKA"
        assert guest2.given_name == "HANAKO"

    def test_extracts_name_without_title(self) -> None:
        """Test name extraction without MR/MS title line."""
        text = """0067368202
01,JAN,2000 TS1234567 01,OCT,2020
A (26) 01,OCT,2030
MATSUMOTO CHIAKI
JAPAN"""
        result = parse_passenger_list(text)
        info = result.guests_by_inquiry["0067368202"][0]
        assert info.full_name == "MATSUMOTO CHIAKI"
        assert info.family_name == "MATSUMOTO"
        assert info.given_name == "CHIAKI"

    def test_extracts_indented_inquiry_line(self) -> None:
        """Indented inquiry lines should still start a passenger block."""
        text = """A (31) 0012345678 01,JAN,2000 TS1234567 01,OCT,2020
MR. ALPHA TARO
JAPAN"""
        result = parse_passenger_list(text)
        assert "0012345678" in result.guests_by_inquiry
        info = result.guests_by_inquiry["0012345678"][0]
        assert info.passport_no == "TS1234567"
        assert info.family_name == "ALPHA"
        assert info.given_name == "TARO"

    def test_indented_inquiry_without_passport_sets_ppt_missing(self) -> None:
        """Indented inquiry lines without passport should get PPT未 flag."""
        text = """A (22) 0012345699 1
MR. BETA JIRO
JAPAN"""
        result = parse_passenger_list(text)
        assert "0012345699" in result.guests_by_inquiry
        assert result.guests_by_inquiry["0012345699"][0].passport_no is None
        assert "PPT未" in result.flags_by_inquiry.get("0012345699", [])

    def test_age_hint_date_like_number_is_not_treated_as_inquiry(self) -> None:
        """Date-like 8-digit values must not split a valid inquiry block."""
        text = """0067368202
01,JAN,2000 TS1234567 01,OCT,2020
A (26) 20261027
MR. HANKYU TARO
JAPAN"""
        result = parse_passenger_list(text)
        assert "0067368202" in result.guests_by_inquiry
        assert "20261027" not in result.guests_by_inquiry
        assert len(result.guests_by_inquiry["0067368202"]) == 1
