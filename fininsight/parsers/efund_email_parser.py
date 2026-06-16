"""易方达基金月度对账单邮件解析器。

邮件特征：
- 发件人：service*@efunds.com.cn
- 主题：含「易方达电子对账单」或「易方达」+「对账单」
- HTML 正文编码 GBK，使用嵌套 <table> 布局
- 账单起止日期：文本中「对账单起止日期：YYYY-MM-DD~YYYY-MM-DD」
- 基金账号：文本中「基金账号：XXXXXX」
- 持仓表（当前账户余额合计表）：
    列：基金代码 | 基金名称 | 当前余额(份) | 未付收益(份) | 分红方式 | 销售机构 | 净值日期 | 单位净值 | 参考市值
- 交易流水表（对账期内交易流水表）：
    列：确认日期 | 基金名称 | 销售机构 | 业务类型 | 成交净值 | 确认金额 | 确认份额(份) | 手续费 | 单位 | 确认结果
- 表格特点：持仓表是结构良好的 <table>，表头行有「基金代码」；
           交易流水表表头行有「确认日期」和「业务类型」。
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
    classify_asset,
    decode_header,
    get_html_body,
    parse_decimal,
    parse_date,
)

logger = logging.getLogger(__name__)

# 申购/买入类操作 → inflow
_INFLOW_KEYWORDS: frozenset = frozenset({"申购", "买入", "定投", "转入", "红利再投"})

# 赎回/卖出类操作 → outflow
_OUTFLOW_KEYWORDS: frozenset = frozenset({"赎回", "卖出", "转出"})

# 跳过的合计行
_SKIP_NAMES: frozenset = frozenset({"合计", "总计", "小计", "汇总", "暂无数据"})


class EfundEmailParser(StatementParser):
    """解析易方达基金发送的 HTML 月度电子对账单邮件。

    工作流程：
    1. ``can_parse()``：发件人匹配 ``@efunds.com.cn`` 且主题含「易方达」+「对账单」
    2. ``parse()``：
       - 从文本提取账单期间
       - 定位持仓表（表头含「基金代码」和「参考市值」）
       - 定位交易流水表（表头含「确认日期」和「业务类型」）
       - 交易流水按基金名称汇总 inflow/outflow
       - 根据参考市值（closing_value）+ inflow/outflow 反推 opening_value
    """

    _SENDER_PATTERN = r"@efunds\.com\.cn"

    # ------------------------------------------------------------------
    # StatementParser interface
    # ------------------------------------------------------------------

    def can_parse(self, raw_data: Any) -> bool:
        if not isinstance(raw_data, Message):
            return False
        sender = decode_header(raw_data.get("From", ""))
        subject = decode_header(raw_data.get("Subject", ""))
        return bool(re.search(self._SENDER_PATTERN, sender, re.IGNORECASE)) and (
            "对账单" in subject or "易方达" in subject
        )

    def parse(self, raw_data: Message) -> List[HoldingRecord]:
        subject = decode_header(raw_data.get("Subject", ""))
        html = get_html_body(raw_data)
        if not html:
            logger.warning("易方达：邮件无 HTML 正文，跳过: %s", subject)
            return []

        soup = BeautifulSoup(html, "html.parser")

        # 1. 提取账单期间
        period = self._extract_period(soup)
        if period is None:
            logger.warning("易方达：无法提取账单期间，跳过: %s", subject)
            return []

        # 2. 解析交易流水（汇总各基金 inflow/outflow）
        tx_map = self._parse_transaction_table(soup)
        logger.debug("易方达：交易流水 %d 条基金记录", len(tx_map))

        # 3. 解析持仓表，生成 HoldingRecord
        holdings = self._parse_holdings_table(soup, period, tx_map)
        logger.info("易方达：从邮件「%s」解析到 %d 条持仓记录", subject, len(holdings))
        return holdings

    # ------------------------------------------------------------------
    # Period extraction
    # ------------------------------------------------------------------

    def _extract_period(self, soup: BeautifulSoup) -> Optional[ReportPeriod]:
        """从 HTML 文本中提取「对账单起止日期：YYYY-MM-DD~YYYY-MM-DD」。

        易方达的账单期间藏在纯文本节点里，格式示例：
            对账单起止日期：2026-04-01~2026-04-30
        """
        full_text = soup.get_text(" ", strip=True)
        # 支持「~」和「至」两种分隔符
        m = re.search(
            r"对账单起止日期[：:]\s*(\d{4}-\d{2}-\d{2})[~至]\s*(\d{4}-\d{2}-\d{2})",
            full_text,
        )
        if not m:
            # 兜底：尝试从主题中提取年月（如「2026年5月」）
            logger.debug("易方达：未在正文找到起止日期，尝试主题")
            return None

        start = parse_date(m.group(1))
        end = parse_date(m.group(2))
        if not start or not end:
            return None

        try:
            return ReportPeriod(start, end)
        except ValueError as exc:
            logger.debug("易方达：期间日期无效: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Table finders
    # ------------------------------------------------------------------

    @staticmethod
    def _get_header_cells(table_tag: Any) -> List[str]:
        """扫描 <table> 所有 <tr>，返回第一个同时含多列且有意义的行（表头行）。

        处理易方达邮件中持仓表首行是「基金报价单位：元」的情况：
        只返回单元格数 >= 3 的第一个有内容行，这样可以跳过只有 1 个单元格的说明行。
        """
        for tr in table_tag.find_all("tr", recursive=False):
            cells = [
                td.get_text(strip=True)
                for td in tr.find_all(["th", "td"], recursive=False)
            ]
            if len([c for c in cells if c]) >= 3:
                return cells
        return []

    @staticmethod
    def _table_has_header_keywords(
        table_tag: Any, *keyword_groups: tuple
    ) -> bool:
        """检查 <table> 的任意行是否同时满足所有关键词组（每组至少命中一个关键词）。

        使用 recursive=False 只扫描直接子 <tr>，避免匹配嵌套 table 的行。
        同时要求行中单元格数 >= 3，以排除将所有内容合并在单个 <td> 的汇总行。
        """
        for tr in table_tag.find_all("tr", recursive=False):
            cells = [
                td.get_text(strip=True)
                for td in tr.find_all(["th", "td"], recursive=False)
            ]
            # 要求至少 3 个单元格，排除大段文字合并在单个 <td> 的行
            if len([c for c in cells if c]) < 3:
                continue
            all_matched = all(
                any(kw in c for c in cells for kw in group)
                for group in keyword_groups
            )
            if all_matched:
                return True
        return False

    def _find_holdings_table(self, soup: BeautifulSoup) -> Optional[Any]:
        """找到持仓表：某行同时含「基金代码」和「参考市值」的 <table>（直接子 tr）。"""
        for table in soup.find_all("table"):
            if self._table_has_header_keywords(
                table, ("基金代码",), ("参考市值",)
            ):
                return table
        return None

    def _find_transaction_table(self, soup: BeautifulSoup) -> Optional[Any]:
        """找到交易流水表：某行同时含「确认日期」和「业务类型」的 <table>（直接子 tr）。"""
        for table in soup.find_all("table"):
            if self._table_has_header_keywords(
                table, ("确认日期",), ("业务类型",)
            ):
                return table
        return None

    # ------------------------------------------------------------------
    # Holdings parser
    # ------------------------------------------------------------------

    def _parse_holdings_table(
        self,
        soup: BeautifulSoup,
        period: ReportPeriod,
        tx_map: Dict[str, Tuple[Decimal, Decimal]],
    ) -> List[HoldingRecord]:
        """解析持仓表，返回 HoldingRecord 列表。"""
        table = self._find_holdings_table(soup)
        if table is None:
            logger.warning("易方达：未找到持仓表")
            return []

        headers = self._get_header_cells(table)
        col = self._build_col_index(
            headers,
            {
                "code": ("基金代码",),
                "name": ("基金名称",),
                "nav": ("单位净值",),
                "closing": ("参考市值",),
            },
        )

        if col.get("name") is None or col.get("closing") is None:
            logger.warning("易方达持仓表：缺少「基金名称」或「参考市值」列，headers=%s", headers)
            return []

        results: List[HoldingRecord] = []
        # 只遍历直接子 <tr>，避免嵌套 table 的行混入
        rows = table.find_all("tr", recursive=False)
        header_skipped = False

        for tr in rows:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"], recursive=False)]
            if not any(c for c in cells):
                continue

            # 跳过表头行：包含「基金代码」关键词的行
            if not header_skipped:
                if any("基金代码" in c or "基金报价" in c for c in cells):
                    if any("基金代码" in c for c in cells):
                        header_skipped = True
                    continue

            if not header_skipped:
                continue

            max_needed = max(v for v in col.values() if v is not None)
            if len(cells) <= max_needed:
                continue

            name = cells[col["name"]].strip()
            if not name or name in _SKIP_NAMES:
                continue

            # 基金代码
            code: Optional[str] = None
            if col.get("code") is not None:
                raw_code = cells[col["code"]].strip()
                # 基金代码应为 6 位数字
                code = raw_code if (raw_code and len(raw_code) == 6 and raw_code.isdigit()) else None

            # 参考市值（期末市值）
            try:
                closing_value = parse_decimal(cells[col["closing"]])
            except Exception:
                closing_value = Decimal("0")

            # 推断资产类型
            market, asset_type = classify_asset(name, code)

            asset = Asset(
                name=name,
                asset_type=asset_type,
                market=market,
                code=code,
            )

            # 从交易流水回填 inflow/outflow（按基金名称匹配）
            inflow, outflow = tx_map.get(name, (Decimal("0"), Decimal("0")))

            record = HoldingRecord(
                asset=asset,
                period=period,
                opening_value=Decimal("0"),
                closing_value=closing_value,
                inflow=inflow,
                outflow=outflow,
            )
            results.append(record)

        return results

    # ------------------------------------------------------------------
    # Transaction parser
    # ------------------------------------------------------------------

    def _parse_transaction_table(
        self, soup: BeautifulSoup
    ) -> Dict[str, Tuple[Decimal, Decimal]]:
        """解析交易流水表，按基金名称汇总 inflow/outflow。

        Returns:
            {基金名称: (inflow合计, outflow合计)}
        """
        table = self._find_transaction_table(soup)
        if table is None:
            logger.debug("易方达：未找到交易流水表")
            return {}

        headers = self._get_header_cells(table)
        col = self._build_col_index(
            headers,
            {
                "name": ("基金名称",),
                "type": ("业务类型",),
                "amount": ("确认金额",),
                "result": ("确认结果",),
            },
        )

        if col.get("name") is None or col.get("type") is None or col.get("amount") is None:
            logger.warning("易方达交易表：缺少必要列，headers=%s", headers)
            return {}

        result: Dict[str, List[Decimal]] = {}
        # 只遍历直接子 <tr>
        rows = table.find_all("tr", recursive=False)
        header_skipped = False

        for tr in rows:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"], recursive=False)]
            if not any(c for c in cells):
                continue

            # 跳过表头行
            if not header_skipped:
                if any("业务类型" in c for c in cells):
                    header_skipped = True
                    continue
                continue

            max_needed = max(v for v in col.values() if v is not None)
            if len(cells) <= max_needed:
                continue

            name = cells[col["name"]].strip()
            tx_type = cells[col["type"]].strip()
            if not name or not tx_type:
                continue

            # 过滤失败/撤销的交易
            if col.get("result") is not None and col["result"] < len(cells):
                result_text = cells[col["result"]].strip()
                if result_text and "成功" not in result_text:
                    continue

            try:
                amount = parse_decimal(cells[col["amount"]])
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

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _build_col_index(
        headers: List[str], mapping: Dict[str, Tuple[str, ...]]
    ) -> Dict[str, Optional[int]]:
        """根据表头和关键词映射，构建列名 → 索引的字典。

        Args:
            headers: 表头单元格文本列表
            mapping: {字段名: (关键词1, 关键词2, ...)} — 任意关键词命中即匹配

        Returns:
            {字段名: 列索引（未找到时为 None）}
        """
        col: Dict[str, Optional[int]] = {}
        for field_name, keywords in mapping.items():
            col[field_name] = next(
                (
                    i
                    for i, h in enumerate(headers)
                    if any(kw in h for kw in keywords)
                ),
                None,
            )
        return col
