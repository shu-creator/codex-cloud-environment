from __future__ import annotations

import pytest

from fnl_builder.integrate import remark_rewrite as rewrite
from fnl_builder.shared.types import Category, LLMItem, Phase, RewriteStats


def _make_item(
    *,
    category: Category = Category.OTHER,
    confidence: float = 0.90,
    evidence_quote: str = "根拠あり",
    handoff_text: str = "補足",
) -> LLMItem:
    return LLMItem(
        category=category,
        who_id="0067368202-001",
        confidence=confidence,
        phase=Phase.ON_TOUR,
        handoff_text=handoff_text,
        evidence_quote=evidence_quote,
        summary="",
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "連絡事項 2025/02/11 10:20:30 東京営業所 山田太郎",
            "連絡事項",
        ),
        (
            "連絡事項 東京営業所 〇〇",
            "連絡事項",
        ),
        (
            "連絡事項 2025/02/11 10:20:30東京営業所山田太郎",
            "連絡事項",
        ),
        (
            "連絡事項 2025/02/11 10:20:30 東京営業所 山田様",
            "連絡事項 2025/02/11 10:20:30 東京営業所 山田様",
        ),
        (
            "テキスト 03-06-18ｶｳﾝﾀｰ吉井",
            "テキスト",
        ),
        (
            "テキスト 03-06-18カウンター吉井",
            "テキスト",
        ),
        (
            "テキスト 2025-01-15ｾﾝﾀｰ田中",
            "テキスト",
        ),
    ],
)
def test_strip_internal_signature_suffix(text: str, expected: str) -> None:
    assert rewrite._strip_internal_signature_suffix(text) == expected


@pytest.mark.parametrize(
    ("remark", "expected"),
    [
        ("[medical] ペースメーカー使用", True),
        ("[other] 車椅子利用", True),
        ("[other] 一般連絡", False),
    ],
)
def test_is_medical_like_remark(remark: str, expected: bool) -> None:
    assert rewrite._is_medical_like_remark(remark) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("糖尿病 ※営業へ連絡メモにてレラ済み。", "糖尿病"),
        ("杖持参予定 →連絡ﾒﾓ送信せず ｲﾗ済", "杖持参予定"),
        ("HC登録あり お伺い書待ち", ""),
        ("→【営業様】ＲＱ→HKにされる際、上記ご確認下さい。", "ＲＱ→HKにされる際、上記ご確認下さい。"),
        ("DEP先の為連絡メモ送信せず。", ""),
        ("一般連絡", "一般連絡"),
        ("営業へ回送済み。 インシュリン持参", "インシュリン持参"),
        ("→【営業様】ＲＱ→HKにされる際、上記ご確認下さい。インシュリン持参", "ＲＱ→HKにされる際、上記ご確認下さい。インシュリン持参"),
        ("糖尿病 営業へ連絡メモにてレラ済み インシュリン持参", "糖尿病インシュリン持参"),
        ("糖尿病 営業へ連絡メモにてレラ済み。インシュリン持参", "糖尿病インシュリン持参"),
    ],
)
def test_strip_internal_memo_phrases(text: str, expected: str) -> None:
    assert rewrite._strip_internal_memo_phrases(text) == expected


def test_sanitize_remarks_parts_strips_memo_phrases() -> None:
    remarks_parts = [
        "[病人] 糖尿病 ※営業へ連絡メモにてレラ済み。 →お伺い書待ち。",
        "HC登録あり",
    ]
    result = rewrite._sanitize_remarks_parts(remarks_parts)
    assert result == ["[病人] 糖尿病"]


def test_sanitize_remarks_parts_dedup_and_strip_signature() -> None:
    remarks_parts = [
        " [other] 連絡事項 2025/02/11 10:20:30 東京営業所 山田太郎 ",
        "[other] 連絡事項",
        "",
    ]

    assert rewrite._sanitize_remarks_parts(remarks_parts) == ["[other] 連絡事項"]


def test_group_rule_rewritable_remarks_categorization() -> None:
    candidate_remarks = [
        "[問合せNO: 0067368202] [fnl_shared_plz] 共通連絡",
        "[medical] インシュリン使用",
        "[ルーミング変更] 高層階希望",
        "[その他] 一般連絡",
    ]

    keep_raw, grouped, count = rewrite._group_rule_rewritable_remarks(
        candidate_remarks,
    )

    assert keep_raw == [
        "[問合せNO: 0067368202] [fnl_shared_plz] 共通連絡",
    ]
    assert grouped["medical"] == ["[medical] インシュリン使用"]
    assert grouped["hotel"] == ["[ルーミング変更] 高層階希望"]
    assert grouped["other"] == ["[その他] 一般連絡"]
    assert count == 3


def test_rewrite_remarks_full_rewrite_with_llm() -> None:
    remarks, stats = rewrite._rewrite_remarks(
        ["[ルーミング変更] 高層階希望", "[その他] 共有事項"],
        guest_llm_remarks=["[hotel] エレベーター近く希望", "[group] 同行者と近い部屋希望"],
        guest_llm_items=[_make_item(category=Category.OTHER)],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert remarks == [
        "[hotel] エレベーター近く希望",
        "[その他] 共有事項",
        "[group] 同行者と近い部屋希望",
    ]
    assert stats == RewriteStats(candidates=2, applied=1, fallback=1)


def test_rewrite_remarks_fallback_when_no_extraction() -> None:
    remarks, stats = rewrite._rewrite_remarks(
        ["[ルーミング変更] 高層階希望", "[その他] 共有事項"],
        guest_llm_remarks=["[hotel] 置換されない"],
        guest_llm_items=[_make_item(category=Category.OTHER)],
        llm_extraction_success=False,
        skip_vip_label=True,
    )

    assert remarks == ["[ルーミング変更] 高層階希望", "[その他] 共有事項"]
    assert stats == RewriteStats(candidates=2, applied=0, fallback=2)


def test_reliable_medical_remark_labels_covers_meal_and_dietary() -> None:
    items = [
        _make_item(category=Category.MEAL, confidence=0.90, evidence_quote="アレルギー"),
    ]
    labels = rewrite._reliable_medical_remark_labels(items)
    assert "meal" in labels
    assert "dietary" in labels


def test_rewrite_remarks_meal_reliable_llm_no_rule_supplement() -> None:
    """meal は LLM 版のみ出力し、ルール原文は補足しない。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[食事制限] アレルギーあり"],
        guest_llm_remarks=["[meal] 卵アレルギー対応必要"],
        guest_llm_items=[
            _make_item(category=Category.MEAL, confidence=0.90, evidence_quote="卵アレルギー", handoff_text="卵アレルギー対応必要"),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[meal] 卵アレルギー対応必要" in remarks
    assert "[食事制限] アレルギーあり" not in remarks
    assert stats.applied == 1
    assert stats.fallback == 0


def test_rewrite_remarks_medical_unreliable_llm_fallback() -> None:
    """信頼度の低い医療LLMはfallbackし、Rule抽出テキストを維持する。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[食事制限] アレルギーあり"],
        guest_llm_remarks=["[meal] 卵アレルギー対応必要"],
        guest_llm_items=[
            _make_item(category=Category.MEAL, confidence=0.50, evidence_quote="卵アレルギー", handoff_text="卵アレルギー対応必要"),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[食事制限] アレルギーあり" in remarks
    assert "[meal] 卵アレルギー対応必要" not in remarks
    assert stats.fallback == 1
    assert stats.applied == 0


def test_rewrite_remarks_medical_no_evidence_fallback() -> None:
    """evidence_quoteがない医療LLMはfallbackする。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[食事制限] アレルギーあり"],
        guest_llm_remarks=["[meal] 卵アレルギー対応必要"],
        guest_llm_items=[
            _make_item(category=Category.MEAL, confidence=0.90, evidence_quote="", handoff_text="卵アレルギー対応必要"),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[食事制限] アレルギーあり" in remarks
    assert stats.fallback == 1
    assert stats.applied == 0


def test_rewrite_remarks_medical_mixed_confidence_filters_unreliable() -> None:
    """同カテゴリに信頼/非信頼が混在する場合、非信頼remarkは除外される。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[食事制限] アレルギーあり"],
        guest_llm_remarks=["[meal] 卵アレルギー対応必要", "[meal] 牛乳アレルギー対応必要"],
        guest_llm_items=[
            _make_item(category=Category.MEAL, confidence=0.95, evidence_quote="卵", handoff_text="卵アレルギー対応必要"),
            _make_item(category=Category.MEAL, confidence=0.10, evidence_quote="", handoff_text="牛乳アレルギー対応必要"),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[meal] 卵アレルギー対応必要" in remarks
    assert "[meal] 牛乳アレルギー対応必要" not in remarks
    assert "[食事制限] アレルギーあり" not in remarks
    assert stats.applied == 1
    assert stats.fallback == 0


def test_rewrite_remarks_medical_llm_only_supplement_added() -> None:
    """Ruleが抽出しなかった医療LLM項目は信頼度が高ければ補足追加される。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[その他] 一般連絡"],
        guest_llm_remarks=["[other] 一般情報", "[meal] 卵アレルギー対応必要"],
        guest_llm_items=[
            _make_item(category=Category.MEAL, confidence=0.90, evidence_quote="卵アレルギー", handoff_text="卵アレルギー対応必要"),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[other] 一般情報" in remarks
    assert "[meal] 卵アレルギー対応必要" in remarks


def test_unmapped_label_relabeled_to_other_no_llm() -> None:
    """未マッピングラベルは no-LLM 時に [other] に再ラベルされる。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[カウンター来店予定] 一般連絡"],
        guest_llm_remarks=[],
        guest_llm_items=[],
        llm_extraction_success=False,
        skip_vip_label=True,
    )

    assert "[other] 一般連絡" in remarks
    assert "[カウンター来店予定]" not in " ".join(remarks)
    assert stats == RewriteStats(candidates=1, applied=0, fallback=1)


def test_unmapped_label_with_content_promoted_to_meal_no_llm() -> None:
    """未マッピングラベル + meal コンテンツ → [meal] に昇格（no-LLM）。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[電話受付] 甲殻類アレルギーがあります"],
        guest_llm_remarks=[],
        guest_llm_items=[],
        llm_extraction_success=False,
        skip_vip_label=True,
    )

    assert "[meal] 甲殻類アレルギーがあります" in remarks
    assert "[電話受付]" not in " ".join(remarks)


def test_unmapped_label_relabeled_in_else_fallback() -> None:
    """LLMフォールバック（else分岐）でも未マッピングラベルが再ラベルされる。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[カウンター来店予定] 一般連絡"],
        guest_llm_remarks=["[meal] 関係ないLLMリマーク"],
        guest_llm_items=[_make_item(category=Category.OTHER)],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[other] 一般連絡" in remarks
    assert "[カウンター来店予定]" not in " ".join(remarks)


def test_unmapped_label_relabeled_in_reliable_medical_branch() -> None:
    """reliable medical 分岐でも未マッピングラベルが漏れない。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[電話受付] アレルギーあり"],
        guest_llm_remarks=["[meal] 卵アレルギー対応必要"],
        guest_llm_items=[
            _make_item(
                category=Category.MEAL,
                confidence=0.90,
                evidence_quote="卵アレルギー",
                handoff_text="卵アレルギー対応必要",
            ),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[meal] 卵アレルギー対応必要" in remarks
    # meal: LLM only, no rule supplement
    assert "[電話受付]" not in " ".join(remarks)
    assert not any("アレルギーあり" in r for r in remarks)
    assert stats.applied == 1
    assert stats.fallback == 0


def test_rewrite_remarks_medical_reliable_llm_with_rule_supplement() -> None:
    """medical カテゴリは LLM + ルール両方出力（supplement 動作確認）。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[病人] 糖尿病でインシュリン使用"],
        guest_llm_remarks=["[medical] 糖尿病・インシュリン持参"],
        guest_llm_items=[
            _make_item(
                category=Category.MEDICAL,
                confidence=0.90,
                evidence_quote="糖尿病",
                handoff_text="糖尿病・インシュリン持参",
            ),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[medical] 糖尿病・インシュリン持参" in remarks
    assert "[medical] 糖尿病でインシュリン使用" in remarks
    assert stats.applied == 1
    assert stats.fallback == 0


def test_rewrite_remarks_meal_reliable_llm_only() -> None:
    """meal カテゴリは LLM のみ出力し、ルール原文は含まない。"""
    remarks, stats = rewrite._rewrite_remarks(
        ["[食事制限] エビ・カニアレルギー"],
        guest_llm_remarks=["[meal] 甲殻類アレルギー対応必要"],
        guest_llm_items=[
            _make_item(
                category=Category.MEAL,
                confidence=0.92,
                evidence_quote="エビ・カニアレルギー",
                handoff_text="甲殻類アレルギー対応必要",
            ),
        ],
        llm_extraction_success=True,
        skip_vip_label=True,
    )

    assert "[meal] 甲殻類アレルギー対応必要" in remarks
    assert "[食事制限] エビ・カニアレルギー" not in remarks
    assert stats.applied == 1
    assert stats.fallback == 0
