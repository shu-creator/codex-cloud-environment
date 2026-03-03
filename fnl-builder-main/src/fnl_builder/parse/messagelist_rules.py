from __future__ import annotations

import re
from typing import Callable

from fnl_builder.shared.text import collapse_ws, normalize_inquiry_main

_INQUIRY_PDF_RE = re.compile(r"(\d{10})-(\d{3})")
_INQUIRY_CSV_RE = re.compile(r"\[問合せNO:\s*(\d{7,10})\]")
_GUEST_ID_RE = re.compile(r"顧客\s+(\d{10})-(\d{3})")
_DATE_PREFIX_RE = re.compile(r"^\d{2}-\d{2}\s")
_PDF_ITEM_HEADER_RE = re.compile(r"^\d{2}-\d{2}\s+(?P<category>.+)$")
_PDF_PAGE_FOOTER_RE = re.compile(r"^\d+\s*/\s*\d+$")
_PDF_PAGE_MARKER_RE = re.compile(r"^\[page\s+\d+\]$", re.IGNORECASE)
_PDF_PARTICIPANT_ROW_RE = re.compile(r"^\d+(?:\s+\d+)?\s+(?:MR|MS|MRS|MISS|DR)\.?\b", re.IGNORECASE)
_PDF_HEADER_CONTINUATION_RE = re.compile(r"^[A-Za-z0-9ぁ-ゟァ-ヶー一-龯＜＞【】（）()・／/]+$")
_DUMMY_PREFIX_RE = re.compile(r"^☆+[^☆]+☆+\s*")
_DATE_OPERATOR_PREFIX_RE = re.compile(r"^\d{2}-\d{2}\s+[^\s]+\s*")
_MEMO_LABEL_PATTERN = r"(?:[【\[〈《(]?\s*後方メモ\s*[】\]〉》)]?\s*[:：]?)"
_MEMO_INLINE_RE = re.compile(_MEMO_LABEL_PATTERN, re.IGNORECASE)
_JP_CHAR_CLASS = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uF900-\uFAFF\uFF10-\uFF5A\uFF65-\uFF9F"
_JP_CHAR_TOKEN = rf"[{_JP_CHAR_CLASS}][\u3099\u309A\u309B\u309C]?"
_CJK_CJK_SPACE_RE = re.compile(rf"({_JP_CHAR_TOKEN})\s+({_JP_CHAR_TOKEN})")
_CJK_DIGIT_SPACE_RE = re.compile(rf"({_JP_CHAR_TOKEN})\s+([0-9])")
_DIGIT_CJK_SPACE_RE = re.compile(rf"([0-9])\s+({_JP_CHAR_TOKEN})")

_LAND_ONLY_PATTERN = re.compile(r"(ランドオンリー|ﾗﾝﾄﾞｵﾝﾘｰ|LAND\s*ONLY|L\s*[／/]\s*O|Ｌ／Ｏ)", re.IGNORECASE)
_REMARKS_KEYWORDS = [
    re.compile(r"(アレルギー|ｱﾚﾙｷﾞｰ)", re.IGNORECASE),
    re.compile(r"(ベジタリアン|ヴィーガン|ハラール|ハラル)", re.IGNORECASE),
    re.compile(r"(苦手|食べ(?:られ|れ)ない|不可|禁忌).{0,8}(?:食|料理|食材|食品)", re.IGNORECASE),
    re.compile(r"(?:食|料理|食材|食品).{0,8}(苦手|食べ(?:られ|れ)ない|不可|禁忌)", re.IGNORECASE),
    re.compile(r"食事.{0,4}(?:リクエスト|希望|制限|変更)", re.IGNORECASE),
    re.compile(r"(糖尿病|インシュリン|ｲﾝｼｭﾘﾝ)", re.IGNORECASE),
    re.compile(r"(ペースメーカー|ﾍﾟｰｽﾒｰｶｰ|人工関節|透析)", re.IGNORECASE),
    re.compile(r"(身障者|障害者|障害(?:者)?(?:\s*\d級)?|要介護)", re.IGNORECASE),
    re.compile(r"(閉所恐怖|高所恐怖)", re.IGNORECASE),
    re.compile(r"(車椅子|車いす|ｸﾙﾏｲｽ)", re.IGNORECASE),
    re.compile(r"(杖|松葉杖|歩行器|歩行[^\s]*(?:困難|制限|不自由))", re.IGNORECASE),
    re.compile(r"(変形性|関節症|昇降[^\s]*(?:困難|できない|遅))", re.IGNORECASE),
    re.compile(r"(エレベーター|ｴﾚﾍﾞｰﾀｰ)", re.IGNORECASE),
    re.compile(r"(ベッド[^\s]*(?:大き|キング|サイズ)|大柄|体重|身長)", re.IGNORECASE),
    re.compile(r"(ツイン|ダブル|シングル|トリプル).{0,6}(?:ベッド|希望|不可)", re.IGNORECASE),
    re.compile(r"(隣室|隣の部屋|同フロア|同じ階|近い部屋).{0,6}希望", re.IGNORECASE),
    re.compile(r"(禁煙|喫煙|ノンスモ|ｽﾓｰｷﾝｸﾞ).{0,6}(?:室|部屋|希望|ルーム)", re.IGNORECASE),
    re.compile(r"(低層階|高層階|上層階|1階|２階|地上階).{0,6}希望", re.IGNORECASE),
    re.compile(r"(バスタブ|ﾊﾞｽﾀﾌﾞ|浴槽|シャワー).{0,6}(?:希望|付き|あり)", re.IGNORECASE),
    re.compile(r"(エクステンション(?:ベルト)?|ｴｸｽﾃﾝｼｮﾝ)", re.IGNORECASE),
    re.compile(r"(VIP|重要顧客|顧客ランク)", re.IGNORECASE),
    re.compile(r"(クレーム|苦情|トラブル|揉め|怒っ|対応注意|参加.{0,4}拒否)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z])(UR|VS|VP)(?![A-Za-z])", re.IGNORECASE),
    re.compile(r"(役員|取締役|社長|部長).{0,6}(?:関連|親戚|ご家族|紹介)", re.IGNORECASE),
    re.compile(r"(離団|途中参加|途中離脱|途中合流)", re.IGNORECASE),
    re.compile(r"(タクシー|ﾀｸｼｰ|チャーター|ｼｬｰﾀｰ|専用車)", re.IGNORECASE),
    _LAND_ONLY_PATTERN,
    re.compile(r"(フルーツ|チョコレート|ケーキ|花束|ギフト|プレゼント).*(?:手配|希望)", re.IGNORECASE),
    re.compile(r"\bOP\s*RQ\b", re.IGNORECASE),
]


def _repair_pdf_jp_spacing(text: str) -> str:
    if not text:
        return ""
    repaired = text
    repaired = _CJK_CJK_SPACE_RE.sub(r"\1\2", repaired)
    repaired = _CJK_DIGIT_SPACE_RE.sub(r"\1\2", repaired)
    repaired = _DIGIT_CJK_SPACE_RE.sub(r"\1\2", repaired)
    return repaired


def _normalize_message_list_inquiry(raw: str) -> str:
    return normalize_inquiry_main(raw)


def _extract_message_list_remark(
    line: str,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> str | None:
    if not _has_remark_keyword(line):
        return None
    if remarks_has_banned(line):
        return None
    remark = collapse_ws(_repair_pdf_jp_spacing(line))
    remark = _MEMO_INLINE_RE.sub("", remark)
    remark = collapse_ws(remark)
    remark = _DUMMY_PREFIX_RE.sub("", remark)
    remark = _DATE_OPERATOR_PREFIX_RE.sub("", remark)
    remark = collapse_ws(_repair_pdf_jp_spacing(remark))
    if remark and len(remark) > 3:
        return remark
    return None


def _has_remark_keyword(text: str) -> bool:
    return any(keyword_pattern.search(text) for keyword_pattern in _REMARKS_KEYWORDS)


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _is_pdf_banner_line(line: str) -> bool:
    return "メッセージリスト" in _compact_text(line)


def _is_pdf_report_header_line(line: str) -> bool:
    compact = _compact_text(line)
    compact_upper = compact.upper()
    if compact_upper.startswith("コースNO"):
        return True
    if compact.startswith("出発日：") or compact.startswith("帰着日："):
        return True
    if "出発日：" in compact and "帰着日：" in compact:
        return True
    if "日間" in compact and ("出発日：" in compact or "帰着日：" in compact):
        return True
    if "FLTパターン" in compact or "HTLパターン" in compact or "バス号車" in compact:
        return True
    if compact_upper.startswith("GRPNO"):
        return True
    if compact_upper == "GRP":
        return True
    if "メッセージ" in compact and "NAME" in compact_upper:
        return True
    return False


def _is_pdf_report_header_continuation_line(line: str) -> bool:
    compact = _compact_text(line)
    if not compact or len(compact) > 40:
        return False
    if not compact.endswith("日間"):
        return False
    if _has_remark_keyword(compact):
        return False
    return bool(_PDF_HEADER_CONTINUATION_RE.fullmatch(compact))


def _is_pdf_noise_line(line: str) -> bool:
    return bool(
        _PDF_PAGE_FOOTER_RE.match(line)
        or _PDF_PAGE_MARKER_RE.match(line)
        or _is_pdf_banner_line(line)
        or _is_pdf_report_header_line(line)
        or _is_pdf_report_header_continuation_line(line)
    )


def _is_pdf_next_record_line(line: str) -> bool:
    return bool(_PDF_PARTICIPANT_ROW_RE.match(line))


def _is_pdf_item_header(line: str) -> re.Match[str] | None:
    match = _PDF_ITEM_HEADER_RE.match(line)
    if not match:
        return None
    category = collapse_ws(match.group("category"))
    if not category:
        return None
    return match
