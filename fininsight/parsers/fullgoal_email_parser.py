"""富国基金月度对账单邮件解析器。

邮件特征：
- 发件人：public@fullgoal.com.cn
- 主题：含「对账单」
- HTML 正文使用 div 布局（无 <table>），编码 GBK
- 账户概览：ul.info > li（span.label + span.value）
- 持仓区块：div.table-content > div.inner（标题"我的资产"）
  - 资产分组：div.table-title（货币 / QDII / 股票 / 债券 / 混合 / 指数）
  - 每组持仓：div.table > div.thead.table-item（表头）+ div.tbody > div.table-item（行）
- 交易区块：div.table-content > div.inner（标题"基金交易明细"）
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from email.message import Message
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from fininsight.models.enums import AssetType, Market
from fininsight.models.records import Asset, HoldingRecord, ReportPeriod

from .base import StatementParser
from ._utils import (
    decode_header,
    get_html_body,
    parse_decimal,
    parse_date,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 资产分组 → AssetType 映射（以邮件中出现的分组名称为准）
# ---------------------------------------------------------------------------
_GROUP_TYPE_MAP: Dict[str, AssetType] = {
    "货币":  AssetType.CASH,
    "QDII":  AssetType.FUND,
    "股票":  AssetType.STOCK,
    "债券":  AssetType.BOND,
    "混合":  AssetType.FUND,
    "指数":  AssetType.FUND,
    "海外":  AssetType.FUND,
    "FOF":   AssetType.FUND,
}

# 申购/买入类操作 → 计入 inflow
_INFLOW_KEYWORDS: frozenset = frozenset({"申购", "买入", "定投", "转入", "红利再投"})

# 赎回/卖出类操作 → 计入 outflow
_OUTFLOW_KEYWORDS: frozenset = frozenset({"赎回", "卖出", "转出"})


class FullgoalEmailParser(StatementParser):
    """解析富国基金发送的 HTML 月度对账单邮件。

    工作流程：
    1. ``can_parse()``：发件人匹配 ``@fullgoal.com.cn`` 且主题含「对账单」
    2. ``parse()``：从 HTML 中提取账单期间 → 解析交易明细 → 解析持仓 → 反推期初市值
    """

    _SENDER_PATTERN = r"@fullgoal\.com\.cn"

    # ------------------------------------------------------------------
    # StatementParser interface
    # ------------------------------------------------------------------

    def can_parse(self, raw_data: Any) -> bool:
        if not isinstance(raw_data, Message):
            return False
        sender = decode_header(raw_data.get("From", ""))
        subject = decode_header(raw_data.get("Subject", ""))
        return (
            bool(re.search(self._SENDER_PATTERN, sender, re.IGNORECASE))
            and "对账单" in subject
        )

    def parse(self, raw_data: Message) -> List[HoldingRecord]:
        subject = decode_header(raw_data.get("Subject", ""))
        period = self._extract_period(raw_data)
        if period is None:
            logger.warning("富国基金：无法提取账单期间，跳过: %s", subject)
            return []
        holdings = self._extract_holdings(raw_data, period)
        logger.info("从邮件「%s」解析到 %d 条持仓记录", subject, len(holdings))
        return holdings

    # ------------------------------------------------------------------
    # Period extraction
    # ------------------------------------------------------------------

    def _extract_period(self, message: Message) -> Optional[ReportPeriod]:
        """从 ul.info 中的「账单期间」字段提取时间周期。

        格式：2025-11-01至2025-11-30
        """
        html = get_html_body(message)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        ul = soup.find("ul", class_="info")
        if not ul:
            logger.debug("富国基金：未找到 ul.info")
            return None

        for li in ul.find_all("li"):
            spans = li.find_all("span")
            if len(spans) < 2:
                continue
            label = spans[0].get_text(strip=True)
            if "账单期间" not in label:
                continue
            value = spans[1].get_text(strip=True)
            m = re.match(r"(\d{4}-\d{2}-\d{2})至(\d{4}-\d{2}-\d{2})", value)
            if m:
                start = parse_date(m.group(1))
                end = parse_date(m.group(2))
                if start and end:
                    try:
                        return ReportPeriod(start, end)
                    except ValueError as exc:
                        logger.debug("富国基金：期间日期无效 %s: %s", value, exc)
        return None

    # ------------------------------------------------------------------
    # Holdings extraction
    # ------------------------------------------------------------------

    def _extract_holdings(
        self, message: Message, period: ReportPeriod
    ) -> List[HoldingRecord]:
        html = get_html_body(message)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # 步骤 1：解析交易明细（按基金名称汇总入金/出金）
        tx_map = self._parse_transaction_section(soup)
        logger.debug("富国基金：交易明细 %d 条", len(tx_map))

        # 步骤 2：解析持仓区块，返回 (record, profit) 对
        holding_pairs = self._parse_holdings_section(soup, period)

        # 步骤 3：回填交易数据，反推期初市值
        holdings: List[HoldingRecord] = []
        for record, profit in holding_pairs:
            name = record.asset.name
            if name in tx_map:
                record.inflow, record.outflow = tx_map[name]
            # 反推期初市值：opening = closing - profit - inflow + outflow
            record.opening_value = (
                record.closing_value - profit - record.inflow + record.outflow
            ).quantize(Decimal("0.01"))
            holdings.append(record)

        return holdings

    # ------------------------------------------------------------------
    # Section parsers
    # ------------------------------------------------------------------

    def _find_inner_section(self, soup: Any, title_prefix: str) -> Optional[Any]:
        """找到 div.table-content > div.inner，其文本以 title_prefix 开头。"""
        for tc in soup.find_all("div", class_="table-content"):
            inner = tc.find("div", class_="inner")
            if inner and inner.get_text(strip=True).startswith(title_prefix):
                return inner
        return None

    @staticmethod
    def _row_cells(row_div: Any) -> List[str]:
        """提取 div.table-item 中各 span 的文本。"""
        return [s.get_text(strip=True) for s in row_div.find_all("span", recursive=False)]

    def _parse_transaction_section(
        self, soup: Any
    ) -> Dict[str, Tuple[Decimal, Decimal]]:
        """从「基金交易明细」区块提取各基金的入金/出金合计。

        Returns:
            {基金名称: (inflow合计, outflow合计)}
        """
        inner = self._find_inner_section(soup, "基金交易明细")
        if not inner:
            return {}

        result: Dict[str, List[Decimal]] = {}

        for table_div in inner.find_all("div", class_="table"):
            thead = table_div.find("div", class_="thead")
            if not thead:
                continue
            headers = self._row_cells(thead)

            name_idx = next(
                (i for i, h in enumerate(headers) if "基金名称" in h or "产品名称" in h),
                None,
            )
            type_idx = next(
                (i for i, h in enumerate(headers) if "业务类型" in h or "交易类型" in h),
                None,
            )
            # 交易申请列（金额）：优先「交易申请」，其次「申请金额」，再次含「金额」
            amt_idx = next(
                (i for i, h in enumerate(headers)
                 if any(k in h for k in ("交易申请", "申请金额", "成交金额", "确认金额"))),
                None,
            )
            if amt_idx is None:
                amt_idx = next(
                    (i for i, h in enumerate(headers) if "金额" in h), None
                )

            if name_idx is None or type_idx is None or amt_idx is None:
                logger.debug("富国基金交易表：缺少必要列，表头=%s", headers)
                continue

            tbody = table_div.find("div", class_="tbody")
            if not tbody:
                continue

            for row in tbody.find_all("div", class_="table-item"):
                cells = self._row_cells(row)
                needed = max(name_idx, type_idx, amt_idx)
                if needed >= len(cells):
                    continue

                name = cells[name_idx].strip()
                tx_type = cells[type_idx].strip()
                if not name or not tx_type:
                    continue

                try:
                    amount = parse_decimal(cells[amt_idx])
                except Exception:
                    continue

                if amount <= Decimal("0"):
                    continue

                if name not in result:
                    result[name] = [Decimal("0"), Decimal("0")]

                if any(kw in tx_type for kw in _INFLOW_KEYWORDS):
                    result[name][0] += amount
                elif any(kw in tx_type for kw in _OUTFLOW_KEYWORDS):
                    result[name][1] += amount

        return {k: (v[0], v[1]) for k, v in result.items()}

    def _parse_holdings_section(
        self, soup: Any, period: ReportPeriod
    ) -> List[Tuple[HoldingRecord, Decimal]]:
        """从「我的资产」区块提取持仓，返回 (HoldingRecord, 本期收益) 列表。

        本期收益暂存于返回值而非 HoldingRecord（后者无该字段），
        在 _extract_holdings 中合并交易数据后用于反推期初市值。
        """
        inner = self._find_inner_section(soup, "我的资产")
        if not inner:
            logger.debug("富国基金：未找到「我的资产」区块")
            return []

        results: List[Tuple[HoldingRecord, Decimal]] = []
        current_asset_type: AssetType = AssetType.FUND  # 默认类型

        for child in inner.children:
            if not hasattr(child, "name") or not child.name:
                continue

            classes = child.get("class") or []

            if "table-title" in classes:
                # 更新当前资产类型
                group_name = child.get_text(strip=True)
                mapped = _GROUP_TYPE_MAP.get(group_name) or _GROUP_TYPE_MAP.get(
                    group_name.upper()
                )
                if mapped is not None:
                    current_asset_type = mapped
                else:
                    logger.debug("富国基金：未知资产分组「%s」，保留默认类型", group_name)

            elif "table" in classes:
                parsed = self._parse_holding_table(
                    child, current_asset_type, period
                )
                results.extend(parsed)

        return results

    def _parse_holding_table(
        self,
        table_div: Any,
        asset_type: AssetType,
        period: ReportPeriod,
    ) -> List[Tuple[HoldingRecord, Decimal]]:
        """解析单个持仓 div.table，返回 (HoldingRecord, profit) 列表。"""
        thead = table_div.find("div", class_="thead")
        if not thead:
            return []
        headers = self._row_cells(thead)

        name_idx = next(
            (i for i, h in enumerate(headers) if "产品名称" in h or "基金名称" in h),
            None,
        )
        code_idx = next(
            (i for i, h in enumerate(headers) if "基金代码" in h or "产品代码" in h or h == "代码"),
            None,
        )
        closing_idx = next(
            (i for i, h in enumerate(headers) if "期末市值" in h),
            None,
        )
        profit_idx = next(
            (i for i, h in enumerate(headers) if "本期收益" in h or "收益" in h),
            None,
        )

        if name_idx is None or closing_idx is None:
            return []

        tbody = table_div.find("div", class_="tbody")
        if not tbody:
            return []

        results: List[Tuple[HoldingRecord, Decimal]] = []
        _skip = frozenset({"合计", "总计", "小计", "汇总", "暂无数据"})

        for row in tbody.find_all("div", class_="table-item"):
            cells = self._row_cells(row)
            if not cells:
                continue

            max_needed = max(
                c for c in [name_idx, code_idx, closing_idx, profit_idx]
                if c is not None
            )
            if max_needed >= len(cells):
                continue

            name = cells[name_idx].strip()
            if not name or name in _skip:
                continue

            code: Optional[str] = None
            if code_idx is not None:
                raw_code = cells[code_idx].strip()
                code = raw_code if raw_code else None

            try:
                closing_value = parse_decimal(cells[closing_idx])
            except Exception:
                closing_value = Decimal("0")

            profit = Decimal("0")
            if profit_idx is not None:
                try:
                    profit = parse_decimal(cells[profit_idx])
                except Exception:
                    pass

            asset = Asset(
                name=name,
                asset_type=asset_type,
                market=Market.DOMESTIC,
                code=code,
            )
            record = HoldingRecord(
                asset=asset,
                period=period,
                opening_value=Decimal("0"),  # 待反推
                closing_value=closing_value,
            )
            results.append((record, profit))

        return results
