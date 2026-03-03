from __future__ import annotations

from fnl_builder.parse.course_code import extract_course_code, find_course_codes
from fnl_builder.parse.messagelist_companion import (
    companion_marker_flags,
    extract_companion_inquiries,
    prune_companion_groups,
)
from fnl_builder.parse.messagelist import (
    parse_message_list,
)
from fnl_builder.parse.messagelist_rules import (
    _has_remark_keyword,
    _is_pdf_banner_line,
    _is_pdf_noise_line,
    _is_pdf_report_header_line,
    _repair_pdf_jp_spacing,
)
from fnl_builder.shared.text import normalize_inquiry_main


class TestNormalizeInquiryMain:
    def test_strips_leading_zeros(self) -> None:
        assert normalize_inquiry_main("0067368202") == "67368202"

    def test_preserves_single_zero(self) -> None:
        assert normalize_inquiry_main("0") == "0"

    def test_no_leading_zeros(self) -> None:
        assert normalize_inquiry_main("67368202") == "67368202"


class TestExtractCourseCode:
    def test_standard_code(self) -> None:
        assert extract_course_code("コースNO：E417Z some text") == "E417Z"

    def test_two_letter_prefix(self) -> None:
        assert extract_course_code("コースNO：EH417 some text") == "EH417"

    def test_spaced_format(self) -> None:
        assert extract_course_code("コースNo：E H 417 some text") == "EH417"

    def test_q_series(self) -> None:
        assert extract_course_code("コースNO：EQ99999") == "EQ99999"

    def test_no_marker(self) -> None:
        assert extract_course_code("E417Z some text") is None

    def test_multiple_codes_returns_none(self) -> None:
        text = "コースNO：E417Z コースNO：E327AY"
        assert extract_course_code(text) is None

    def test_find_course_codes_returns_list(self) -> None:
        text = "コースNO：E417Z コースNO：E327AY"
        assert find_course_codes(text) == ["E417Z", "E327AY"]


class TestRemarkKeywords:
    def test_allergy_detected(self) -> None:
        assert _has_remark_keyword("えびアレルギーあり")

    def test_diabetes_detected(self) -> None:
        assert _has_remark_keyword("糖尿病のお伺い書返送あり")

    def test_elevator_detected(self) -> None:
        assert _has_remark_keyword("エレベーター近く希望")

    def test_land_only_detected(self) -> None:
        assert _has_remark_keyword("ランドオンリー")

    def test_no_keyword_returns_false(self) -> None:
        assert not _has_remark_keyword("通常の旅行情報")


class TestPdfNoiseDetection:
    def test_banner_line(self) -> None:
        assert _is_pdf_banner_line("メ ッ セ ー ジ リ ス ト 26-02-18 16:30:05")

    def test_page_footer(self) -> None:
        assert _is_pdf_noise_line("1 / 2")

    def test_page_marker(self) -> None:
        assert _is_pdf_noise_line("[page 9]")

    def test_course_header(self) -> None:
        assert _is_pdf_report_header_line("コースNo：E417Z")

    def test_departure_header(self) -> None:
        assert _is_pdf_report_header_line("出発日：26-10-08 帰着日：26-10-17")

    def test_grp_line(self) -> None:
        assert _is_pdf_report_header_line("GRP")


class TestRepairPdfJpSpacing:
    def test_removes_cjk_cjk_space(self) -> None:
        assert _repair_pdf_jp_spacing("提 供") == "提供"

    def test_removes_cjk_digit_space(self) -> None:
        assert _repair_pdf_jp_spacing("第 1回") == "第1回"


class TestCompanionMarkerFlags:
    def test_explicit_marker(self) -> None:
        has_explicit, has_end = companion_marker_flags("別問合せ番号同行ＧＲＰ有")
        assert has_explicit
        assert not has_end

    def test_end_marker(self) -> None:
        has_explicit, has_end = companion_marker_flags("と同ｸﾞﾙｰﾌﾟ")
        assert not has_explicit
        assert has_end

    def test_no_markers(self) -> None:
        has_explicit, has_end = companion_marker_flags("通常テキスト")
        assert not has_explicit
        assert not has_end


class TestExtractCompanionInquiries:
    def test_hash_prefix(self) -> None:
        result = extract_companion_inquiries("#67368244 ﾊﾝｷｭｳ ﾊﾅｺ様")
        assert "67368244" in result

    def test_fullwidth_hash_prefix(self) -> None:
        result = extract_companion_inquiries("＃67621040 ﾊﾝｷｭｳﾅｺﾞﾔ")
        assert "67621040" in result

    def test_no_hash_not_extracted(self) -> None:
        result = extract_companion_inquiries("67368244 ﾊﾝｷｭｳ ﾊﾅｺ様")
        assert len(result) == 0


class TestPruneCompanionGroups:
    def test_drops_missing_inquiries(self) -> None:
        companion_groups = {
            "10000001": {"10000002", "99999999"},
            "99999999": {"10000001"},
        }
        known = {"10000001", "10000002"}
        pruned, removed = prune_companion_groups(companion_groups, known)
        assert pruned == {"10000001": {"10000002"}}
        assert removed == 2


class TestParseMessageListCsv:
    def test_csv_format_inquiry_and_course(self) -> None:
        text = """コースNo：E417Z
[問合せNO: 67368202] 部屋割り：1TWN
糖尿病のお伺い書返送あり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        assert "67368202" in result.course_by_inquiry
        assert result.course_by_inquiry["67368202"] == "E417Z"
        assert "67368202" in result.remarks_by_inquiry
        assert any("糖尿病" in r for r in result.remarks_by_inquiry["67368202"])

    def test_csv_row_without_inquiry_does_not_inherit(self) -> None:
        text = """[問合せNO: 67368202] [確認手配事項] 糖尿病あり

[確認手配事項] 卵アレルギーあり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        remarks = result.remarks_by_inquiry["67368202"]
        assert any("糖尿病" in remark for remark in remarks)
        assert not any("卵アレルギー" in remark for remark in remarks)

    def test_filters_banned_remarks(self) -> None:
        text = """コースNo：E417Z
顧客 0067368202-001
旅行保険の追加案内"""
        result = parse_message_list(text, remarks_has_banned=lambda value: "保険" in value)
        assert result.remarks_by_inquiry == {}


class TestParseMessageListPdf:
    def test_pdf_format_inquiry_and_course(self) -> None:
        text = """コースNo：E417ZC
阪急 花子 0067368202-001
えびｱﾚﾙｷﾞｰ"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        assert "67368202" in result.course_by_inquiry
        assert result.course_by_inquiry["67368202"] == "E417ZC"

    def test_pdf_multiline_block_extraction(self) -> None:
        text = """コースNo：E417Z
MR. HANKYU TARO 0067368202-001
01-13 病人、身体障害者
☆☆ダミー記録です☆☆
糖尿病のお伺い書返送あり
・治療法：インシュリン療法
・糖尿病用特別機内食は「希望しない」"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        key = ("67368202", "1")
        assert key in result.remarks_by_inquiry_guest
        remarks = result.remarks_by_inquiry_guest[key]
        assert len(remarks) == 1
        assert remarks[0].startswith("[問合せNO: 67368202] [病人、身体障害者] ")
        assert "糖尿病のお伺い書返送あり" in remarks[0]
        assert "インシュリン療法" in remarks[0]

    def test_pdf_block_with_banned_text_excluded(self) -> None:
        text = """コースNo：E417Z
MS. HANKYU HANAKO 0067368244-001
01-13 関連事項
えびｱﾚﾙｷﾞｰ
支払いはクレジットカード予定"""
        result = parse_message_list(text, remarks_has_banned=lambda v: "クレジットカード" in v)
        key = ("67368244", "1")
        assert key not in result.remarks_by_inquiry_guest

    def test_pdf_block_skips_noise_lines(self) -> None:
        text = """コースNo：E417Z
MR. HANSHIN HACHIRO 0067621010-001
02-18 関連事項
できればエレベーター近くの部屋希望
1 / 2
メ ッ セ ー ジ リ ス ト 26-02-18 16:30:05
コースNo：E417ZC
ア大周遊10日間
出発日：26-10-08 帰着日：26-10-17
FLTパターン：全て HTLパターン：全て バス号車：全て
GRP No N A M E メ ッ セ ー ジ
卵アレルギーあり
2 / 2
1      1 MR. NEXT GUEST             02-17 各地発着申込
阪急 次郎 0067621011-001
02-18 病人、身体障害者
糖尿病あり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        key = ("67621010", "1")
        assert key in result.remarks_by_inquiry_guest
        remark = result.remarks_by_inquiry_guest[key][0]
        assert "エレベーター近くの部屋希望" in remark
        assert "卵アレルギーあり" in remark
        assert "1 / 2" not in remark
        assert "メ ッ セ ー ジ リ ス ト" not in remark


class TestParseMessageListCompanion:
    def test_companion_group_parsing(self) -> None:
        text = """コースNo：E417Z
MR. HANKYU TARO 0067368202-001
01-13 別問合せ番号同行ＧＲＰ有
#67368244 ﾊﾝｷｭｳ ﾊﾅｺ様
#67368305 ﾊﾝｼﾝ ｼﾞﾛｳ様
と同ｸﾞﾙｰﾌﾟ
部屋割り：1TWN+1SGL"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        assert "67368202" in result.companion_groups
        assert "67368244" in result.companion_groups["67368202"]
        assert "67368305" in result.companion_groups["67368202"]


class TestParseMessageListFnl:
    def test_fnl_shared_block_extraction(self) -> None:
        text = """顧客 0067368202-001
02-17 関連事項
☆☆☆FNL時 記載PLZ☆☆☆
料金案内・承諾後に正式手配希望
02-17 病人、身体障害者
糖尿病あり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        key = ("67368202", "1")
        assert key in result.remarks_by_inquiry_guest
        fnl_remarks = [r for r in result.remarks_by_inquiry_guest[key] if "[fnl_shared_plz]" in r]
        assert len(fnl_remarks) == 1
        assert "料金案内・承諾後に正式手配希望" in fnl_remarks[0]
        assert "糖尿病あり" not in fnl_remarks[0]

    def test_fnl_shared_strips_signature(self) -> None:
        text = """顧客 0010000001-001
02-17 関連事項
FNL時 記載PLZ
料金案内後に手配希望
2025/12/12 13:13:32 西営業3課 伊藤 麻衣
02-17 病人、身体障害者
糖尿病あり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        key = ("10000001", "1")
        fnl_remarks = [r for r in result.remarks_by_inquiry_guest.get(key, []) if "[fnl_shared_plz]" in r]
        assert len(fnl_remarks) == 1
        assert "伊藤 麻衣" not in fnl_remarks[0]
        assert result.fnl_shared_meta_stripped_count == 1

    def test_non_action_fnl_check_flagged(self) -> None:
        text = """顧客 0010000001-001
02-17 関連事項
FNL時CHK お客様連絡があれば確認しておく
02-17 病人、身体障害者
糖尿病あり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        key = ("10000001", "1")
        assert result.fnl_check_required_by_guest == {key: 1}

    def test_actionable_fnl_check_not_flagged(self) -> None:
        text = """顧客 0010000001-001
02-17 関連事項
FNL確認 ランドオペレーターへ共有
02-17 病人、身体障害者
糖尿病あり"""
        result = parse_message_list(text, remarks_has_banned=lambda _: False)
        assert result.fnl_check_required_by_guest == {}
