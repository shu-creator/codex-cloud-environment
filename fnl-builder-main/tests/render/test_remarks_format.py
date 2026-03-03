from __future__ import annotations

from fnl_builder.render.remarks_format import format_guest_remarks


def test_format_empty_parts() -> None:
    assert format_guest_remarks([]) == ""


def test_format_single_category() -> None:
    assert format_guest_remarks(["[medical] 糖尿病対応"]) == "[medical] 糖尿病対応"


def test_format_merges_same_category() -> None:
    remarks = ["[medical] 糖尿病対応", "[medical] 注射器は機内持ち込み"]
    assert format_guest_remarks(remarks) == "[medical] 糖尿病対応\n  注射器は機内持ち込み"


def test_format_multi_category_newline() -> None:
    remarks = ["[medical] 糖尿病対応", "[hotel] 高層階希望"]
    assert format_guest_remarks(remarks) == "[medical] 糖尿病対応\n[hotel] 高層階希望"


def test_format_uncategorized_becomes_other() -> None:
    assert format_guest_remarks(["車椅子サポート希望"]) == "[other] 車椅子サポート希望"


def test_format_semicolons_split() -> None:
    assert format_guest_remarks(["[other] 備考1; 備考2；備考3"]) == "[other] 備考1\n  備考2\n  備考3"


def test_format_ppt_mi_category() -> None:
    assert format_guest_remarks(["PPT未"]) == "[ppt] PPT未"


def test_format_strips_inquiry_prefix() -> None:
    parts = ["[問合せNO:1234567890] [medical] 糖尿病対応"]
    assert format_guest_remarks(parts) == "[medical] 糖尿病対応"


def test_format_removes_companion_suffix() -> None:
    parts = ["糖尿病のお伺い書返送あり; と同グループ"]
    assert format_guest_remarks(parts) == "[other] 糖尿病のお伺い書返送あり"


def test_format_dedupes_stable() -> None:
    parts = ["[medical] 糖尿病対応", "[medical] 糖尿病対応", "[medical] 注射器は機内持ち込み"]
    assert format_guest_remarks(parts) == "[medical] 糖尿病対応\n  注射器は機内持ち込み"


def test_format_full_integration() -> None:
    parts = [
        "[同室] HANKYU HANAKO様とTWN同室",
        "[同行GRP別室] HANSHIN JIRO様(TSU/No.1)",
        "[medical] 糖尿病対応が必要",
        "[medical] 注射器は機内持ち込み",
        "[baggage] 血糖測定器具の持ち込みあり",
        "[group] 同行グループ（別問合せ番号）として同一扱い",
        "フルーツバスケット手配; ベジ対応希望",
    ]
    assert format_guest_remarks(parts) == (
        "[同室] HANKYU HANAKO様とTWN同室\n"
        "[同行grp別室] HANSHIN JIRO様(TSU/No.1)\n"
        "[medical] 糖尿病対応が必要\n  注射器は機内持ち込み\n"
        "[baggage] 血糖測定器具の持ち込みあり\n"
        "[group] 同行グループ（別問合せ番号）として同一扱い\n"
        "[other] フルーツバスケット手配\n  ベジ対応希望"
    )

