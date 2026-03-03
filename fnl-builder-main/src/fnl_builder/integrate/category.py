from __future__ import annotations

import re

from fnl_builder.shared.text import collapse_ws

_REMARK_CATEGORY_RE = re.compile(
    r"^(?:\[\s*問合せ\s*NO:\s*\d{7,10}\]\s*)?\[\s*(?P<label>[^\]]+)\s*\]\s*(?P<body>.*)$",
    re.IGNORECASE,
)

# Map rule-based Japanese labels (from PDF section headers) to the same
# category keys used by LLM remarks so that the rewrite matching works.
_RULE_LABEL_TO_CATEGORY: dict[str, str] = {
    # medical_health
    "病人、身体障害者": "medical",
    "病人・身体障害者": "medical",
    "病人，身体障害者": "medical",
    # dietary
    "食事制限": "meal",
    "アレルギー": "meal",
    # mobility_accessibility
    "車椅子": "mobility",
    "歩行補助": "mobility",
    # accommodation_room
    "ルーミング変更・人数変更": "hotel",
    "ルーミング変更": "hotel",
    # grouping_companion
    "同室": "group",
    "同行grp別室": "group",
    "別問合せ番号同行ｇｒｐ有": "group",
    "別問合せ番号同行grp有": "group",
    # vip_sensitive
    "お客様情報": "vip",
    "フルーツバスケット手配": "vip",
    # schedule_change_separation
    "離団ｒｑ": "itinerary",
    "離団rq": "itinerary",
    "ランドオンリー": "itinerary",
    # documents_immigration
    "ppt": "docs",
    # other (content-based refinement applied below)
    "関連事項": "other",
    "その他": "other",
    # Canonical category labels (pass-through so already-labelled remarks
    # like [vip], [hotel], [meal] are not downgraded to "other").
    "medical": "medical",
    "meal": "meal",
    "mobility": "mobility",
    "hotel": "hotel",
    "group": "group",
    "vip": "vip",
    "itinerary": "itinerary",
    "docs": "docs",
    "comm": "comm",
    "baggage": "baggage",
    "other": "other",
}

# Content keywords to refine "other" category into a specific LLM category.
# Checked in order; first match wins.
_OTHER_CONTENT_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "meal",
        re.compile(
            r"(アレルギー|ｱﾚﾙｷﾞｰ|ベジタリアン|ハラール|食事制限|食材|苦手.{0,8}(?:食|料理)|(?:食|料理).{0,8}苦手)",
            re.IGNORECASE,
        ),
    ),
    ("medical", re.compile(r"(糖尿病|ペースメーカー|インシュリン|透析|身障者|障害者|閉所恐怖|高所恐怖)", re.IGNORECASE)),
    ("mobility", re.compile(r"(車椅子|車いす|杖|歩行|変形性|関節症|昇降)", re.IGNORECASE)),
    (
        "hotel",
        re.compile(
            r"(エレベーター|ｴﾚﾍﾞｰﾀｰ|ベッド.*希望|部屋.*希望|ツイン.*希望|ダブル.*希望|隣室|隣の部屋|同フロア|禁煙.*(?:室|部屋)|低層階|高層階|バスタブ.*希望)",
            re.IGNORECASE,
        ),
    ),
    ("itinerary", re.compile(r"(離団|途中参加|ランドオンリー|タクシー|チャーター)", re.IGNORECASE)),
    (
        "vip",
        re.compile(
            r"(VIP|[クｸ][レﾚ][ーｰ][ムﾑ]|苦情|顧[客ｷｬｸ][ラﾗ][ンﾝ][クｸ]|要配慮|対応注意|参加.{0,4}拒否|役員|取締役)",
            re.IGNORECASE,
        ),
    ),
    (
        "baggage",
        re.compile(
            r"(エクステンション(?:ベルト)?|ｴｸｽﾃﾝｼｮﾝ(?:ﾍﾞﾙﾄ)?|延長ベルト|ベルト延長"
            r"|体重\s*\d{2,3}\s*(?:kg|㎏|[kK][gG])"
            r"|身長\s*\d{3}\s*(?:cm|㎝|センチ))",
            re.IGNORECASE,
        ),
    ),
    ("group", re.compile(r"(同室|同行|グループ|ｸﾞﾙｰﾌﾟ|合流)", re.IGNORECASE)),
    ("docs", re.compile(r"(パスポート|ﾊﾟｽﾎﾟｰﾄ|PPT|旅券|査証|ビザ|(?<![A-Za-z])VISA(?![A-Za-z])|(?<![A-Za-z])ESTA(?![A-Za-z]))", re.IGNORECASE)),
]


# Detect food/allergy content inside a "medical"-labelled remark.
_MEDICAL_TO_MEAL_RE = re.compile(
    r"(アレルギー|ｱﾚﾙｷﾞｰ|食材|食事制限|ベジタリアン|ハラール|エビ|海老|カニ|蟹|ナッツ|乳製品|小麦|グルテン)",
    re.IGNORECASE,
)
# Genuine medical conditions — if matched, do NOT refine medical→meal.
_GENUINE_MEDICAL_RE = re.compile(
    r"(糖尿病|ペースメーカー|インシュリン|インスリン|透析|身障者|障害者|閉所恐怖|高所恐怖|心臓|血圧)",
    re.IGNORECASE,
)

# LLM taxonomy id → short display label for remarks.
_LLM_CATEGORY_LABELS: dict[str, str] = {
    "medical_health": "medical",
    "dietary": "meal",
    "mobility_accessibility": "mobility",
    "accommodation_room": "hotel",
    "grouping_companion": "group",
    "vip_sensitive": "vip",
    "schedule_change_separation": "itinerary",
    "documents_immigration": "docs",
    "communication_language": "comm",
    "baggage_equipment": "baggage",
    "other": "other",
}


def _refine_category_by_content(category: str, remark_body: str) -> str:
    """Refine a category based on remark content keywords.

    - ``other``: applies ``_OTHER_CONTENT_CATEGORY_RULES``.
    - ``medical``: refines to ``meal`` when body matches food/allergy
      patterns and does NOT match genuine medical patterns.
    """
    if category == "other":
        for target_category, pattern in _OTHER_CONTENT_CATEGORY_RULES:
            if pattern.search(remark_body):
                return target_category
        return category
    if category == "medical":
        if _MEDICAL_TO_MEAL_RE.search(remark_body) and not _GENUINE_MEDICAL_RE.search(remark_body):
            return "meal"
    return category


def _relabel_remark(remark: str, new_label: str) -> str:
    """Replace the [label] prefix of a remark with a new label."""
    normalized = collapse_ws(remark)
    match = _REMARK_CATEGORY_RE.match(normalized)
    if not match:
        return f"[{new_label}] {normalized}"
    body = match.group("body")
    # Preserve inquiry prefix if present
    prefix = normalized[: match.start("label")]
    return f"{prefix}{new_label}] {body}"


def _parse_remark_category(remark: str) -> tuple[str | None, str]:
    normalized = collapse_ws(remark)
    if not normalized:
        return None, ""
    match = _REMARK_CATEGORY_RE.match(normalized)
    if not match:
        return None, normalized
    label = collapse_ws(match.group("label")).lower()
    body = collapse_ws(match.group("body"))
    return label, body
