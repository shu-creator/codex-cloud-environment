from __future__ import annotations

from fnl_builder.integrate import vip as vip_module
from fnl_builder.shared.types import Category, Issue, LLMItem, Phase


def _make_item(
    *,
    category: Category = Category.VIP_SENSITIVE,
    confidence: float = 0.90,
    phase: Phase = Phase.ON_TOUR,
    handoff_text: str = "VIP待遇でお願いします",
    evidence_quote: str = "VIP待遇",
    summary: str = "",
) -> LLMItem:
    return LLMItem(
        category=category,
        who_id="0067368202-001",
        confidence=confidence,
        phase=phase,
        handoff_text=handoff_text,
        evidence_quote=evidence_quote,
        summary=summary,
    )


def test_is_vip_item() -> None:
    assert vip_module._is_vip_item(_make_item(category=Category.VIP_SENSITIVE))
    assert not vip_module._is_vip_item(_make_item(category=Category.OTHER))


def test_is_shareable_vip_item() -> None:
    assert vip_module._is_shareable_vip_item(_make_item(confidence=0.90, phase=Phase.ON_TOUR))
    assert not vip_module._is_shareable_vip_item(_make_item(confidence=0.40, phase=Phase.ON_TOUR))
    assert not vip_module._is_shareable_vip_item(_make_item(handoff_text="営業担当に電話対応を依頼"))


def test_detect_vip_action() -> None:
    assert vip_module._detect_vip_action("ホテルでアップグレード希望") == "部屋アップグレード希望"
    assert vip_module._detect_vip_action("VIP対応をお願いします") == "VIP対応希望"
    assert vip_module._detect_vip_action("要配慮の必要あり") == "要配慮対応希望"
    assert vip_module._detect_vip_action("特記事項なし") == "要配慮対応希望"


def test_generalize_vip_handoff_text() -> None:
    text = "弊社取引先の役員。社内営業担当より共有。VIP対応をお願いします。"
    assert vip_module._generalize_vip_handoff_text(text) == "重要顧客のためVIP対応希望"


def test_is_vip_candidate_remark() -> None:
    assert vip_module._is_vip_candidate_remark("[vip] 対応注意")
    assert vip_module._is_vip_candidate_remark("VIP対応が必要")
    assert vip_module._is_vip_candidate_remark("重要顧客のため要配慮")


def test_is_related_to_vip_items() -> None:
    items = [_make_item()]
    assert vip_module._is_related_to_vip_items("[お客様情報] 共有事項", items)
    assert vip_module._is_related_to_vip_items("[その他] クレーム歴あり", items)
    assert not vip_module._is_related_to_vip_items("[meal] ベジタリアン対応", items)


def test_resolve_vip_merge_filters_and_generates() -> None:
    issues: list[Issue] = []
    items = [_make_item(handoff_text="取引先役員のためVIP対応を希望")]
    candidate_remarks = ["[vip] 個別連絡", "[medical] ペースメーカー使用", "通常連絡"]

    filtered, merged, generated = vip_module._resolve_vip_merge(candidate_remarks, items, issues=issues)

    assert filtered == ["[medical] ペースメーカー使用", "通常連絡"]
    assert merged is True
    assert generated == ["[vip] 重要顧客のためVIP対応希望"]
    assert issues == []


def test_resolve_vip_merge_fallback_on_error(monkeypatch: object) -> None:
    def _raise(_: list[LLMItem]) -> list[str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(vip_module, "_build_generalized_vip_remarks", _raise)

    issues: list[Issue] = []
    items = [_make_item()]
    candidate_remarks = ["[vip] 個別連絡", "通常連絡"]

    filtered, merged, generated = vip_module._resolve_vip_merge(candidate_remarks, items, issues=issues)

    assert filtered == ["通常連絡"]
    assert merged is False
    assert generated == []
    assert len(issues) == 1
    assert issues[0].level == "warning"
    assert issues[0].code == "vip_generalize_fallback"
