"""解析器共用工具函数。

各基金公司解析器共享的底层工具：HTML 正文提取、数值解析、日期解析、资产分类。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.message import Message
from typing import Any, Optional, Tuple

import email.header as _email_header

from fininsight.models.enums import AssetType, Market


def decode_header(value: Any) -> str:
    """将邮件头部值（可能是 Header 对象或编码字符串）解码为普通字符串。"""
    if not value:
        return ""
    parts = []
    for part, charset in _email_header.decode_header(str(value)):
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(part))
    return "".join(parts)


def get_html_body(message: Message) -> Optional[str]:
    """从邮件中提取 HTML 正文，支持 multipart 及单部分邮件。"""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/html":
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(charset, errors="replace")
    elif message.get_content_type() == "text/html":
        charset = message.get_content_charset() or "utf-8"
        payload = message.get_payload(decode=True)
        if payload:
            return payload.decode(charset, errors="replace")
    return None


def parse_decimal(value: str) -> Decimal:
    """将可能含有千分位符、单位后缀的字符串解析为 Decimal。

    自动去除：逗号、空格、货币符号（¥ ￥）、单位字（元 份）。
    特殊值（空、短横、N/A 等）返回 0。
    """
    cleaned = re.sub(r"[,，\s¥￥元份]", "", value)
    if not cleaned or cleaned in ("-", "--", "N/A", "暂无", "/"):
        return Decimal("0")
    return Decimal(cleaned)


def parse_date(value: str) -> Optional[date]:
    """将常见日期字符串格式解析为 date 对象。"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def classify_asset(
    name: str,
    code: Optional[str],
    default_market: Market = Market.DOMESTIC,
    default_asset_type: AssetType = AssetType.FUND,
) -> Tuple[Market, AssetType]:
    """根据名称关键词和代码格式推断资产的市场和类别。

    推断优先级：名称关键词 > 代码格式 > 默认值。
    """
    market = default_market
    asset_type = default_asset_type

    name_upper = name.upper()
    _FUND_NAME_KEYWORDS = (
        "基金", "指数", "混合", "成长", "价值", "增强", "增长", "平衡",
        "稳健", "灵活", "量化", "对冲", "优选", "精选",
    )
    if "ETF" in name_upper or "LOF" in name_upper:
        asset_type = AssetType.FUND
    elif any(kw in name for kw in _FUND_NAME_KEYWORDS):
        asset_type = AssetType.FUND
    elif "黄金" in name and "基金" not in name:
        asset_type = AssetType.GOLD
        market = Market.DOMESTIC
    elif "货币" in name:
        asset_type = AssetType.CASH
        market = Market.DOMESTIC
    elif "存单" in name or "定期" in name:
        asset_type = AssetType.CD
        market = Market.DOMESTIC
    elif "债券" in name or ("债" in name and "基金" not in name):
        asset_type = AssetType.BOND
        market = Market.DOMESTIC

    if code:
        if re.fullmatch(r"[A-Z]{1,5}", code):
            market = Market.US_STOCK
            if asset_type == default_asset_type:
                asset_type = AssetType.STOCK
        elif re.fullmatch(r"\d{5}", code) or re.fullmatch(
            r"\d{4,5}\.HK", code, re.IGNORECASE
        ):
            market = Market.HK_STOCK
            if asset_type == default_asset_type:
                asset_type = AssetType.STOCK
        elif re.fullmatch(r"\d{6}", code):
            if code[0] == "6":
                if asset_type == default_asset_type:
                    asset_type = AssetType.STOCK
                    market = Market.A_SHARE
            elif code[0] == "3":
                if asset_type == default_asset_type:
                    asset_type = AssetType.STOCK
                    market = Market.A_SHARE

    return market, asset_type
