"""基金对账单邮件解析器。

通用实现：
- 使用邮件主题关键词识别对账单
- 使用 BeautifulSoup 解析 HTML 邮件正文中的持仓表格
- 基于列名模式匹配自动识别各字段
- 资产类型/市场分类根据代码格式和名称关键词自动推断

扩展方式：
  继承 FundEmailParser，覆盖 _extract_period() 或 _extract_holdings()，
  即可支持特定机构（如招行、工行、天天基金等）的专属邮件格式。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.message import Message
from typing import Any, Dict, List, Optional, Tuple

import email.header as _email_header
from bs4 import BeautifulSoup

from fininsight.models.enums import AssetType, Market
from fininsight.models.records import Asset, HoldingRecord, ReportPeriod

from .base import StatementParser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 列名匹配规则（key = 规范字段名，value = 可能出现在表头的关键词列表）
# ---------------------------------------------------------------------------
_COLUMN_PATTERNS: Dict[str, List[str]] = {
    "name":          ["基金名称", "产品名称", "投资标的", "名称"],
    "code":          ["基金代码", "产品代码", "代码"],
    "opening_value": ["期初市值", "上期末市值", "期初金额", "上期市值"],
    "closing_value": ["期末持有净值", "期末市值", "本期末市值", "期末金额", "本期市值", "当前市值"],
    "inflow":        ["申购金额", "买入金额", "入金金额", "申购", "买入"],
    "outflow":       ["赎回金额", "卖出金额", "出金金额", "赎回", "卖出"],
    "market_value":  ["最新市值", "持有市值", "市值", "资产市值"],
    "units":         ["持有份额", "持仓份额", "份额", "持有数量"],
}

# 邮件主题中表示「对账单/持仓报告」的关键词
_STATEMENT_SUBJECT_KEYWORDS = ["对账单", "持仓", "资产报告", "理财报告", "持有明细", "账户报告"]

# ---------------------------------------------------------------------------
# 交易明细表识别与分类
# ---------------------------------------------------------------------------

# 命中任意一个则该 <table> 视为交易流水表，不作为持仓表解析
_TRANSACTION_TABLE_SIGNALS: frozenset = frozenset({"申请日期", "确认日期", "业务类型"})

# 申购/买入类操作关键词 → 计入 inflow
_INFLOW_TX_KEYWORDS: frozenset = frozenset(["申购", "买入", "定投", "转入", "红利再投"])

# 赎回/卖出类操作关键词 → 计入 outflow
_OUTFLOW_TX_KEYWORDS: frozenset = frozenset(["赎回", "卖出", "转出"])


class FundEmailParser(StatementParser):
    """解析基金公司发送的 HTML 对账单邮件。

    工作流程：
    1. ``can_parse()``：检查主题关键词（及可选的发件人正则）
    2. ``parse()``：提取 HTML 正文 → 解析持仓表格 → 返回 HoldingRecord 列表

    参数:
        default_market: 无法自动识别市场时的默认值，默认 ``Market.DOMESTIC``
        default_asset_type: 无法自动识别类别时的默认值，默认 ``AssetType.FUND``
        sender_patterns: 发件人地址白名单（Python 正则列表），为空则不限制
    """

    def __init__(
        self,
        default_market: Market = Market.DOMESTIC,
        default_asset_type: AssetType = AssetType.FUND,
        sender_patterns: Optional[List[str]] = None,
    ) -> None:
        self._default_market = default_market
        self._default_asset_type = default_asset_type
        self._sender_patterns = sender_patterns or []

    # ------------------------------------------------------------------
    # StatementParser interface
    # ------------------------------------------------------------------

    def can_parse(self, raw_data: Any) -> bool:
        """判断该邮件是否是基金对账单。"""
        if not isinstance(raw_data, Message):
            return False

        # 发件人白名单过滤（配置了才检查）
        if self._sender_patterns:
            sender = _decode_header(raw_data.get("From", ""))
            if not any(
                re.search(p, sender, re.IGNORECASE) for p in self._sender_patterns
            ):
                return False

        # 主题关键词检查
        subject = _decode_header(raw_data.get("Subject", ""))
        return any(kw in subject for kw in _STATEMENT_SUBJECT_KEYWORDS)

    def parse(self, raw_data: Message) -> List[HoldingRecord]:
        """解析对账单邮件，返回持仓记录列表。"""
        subject = _decode_header(raw_data.get("Subject", ""))
        period = self._extract_period(raw_data)
        if period is None:
            logger.warning("无法从邮件主题中提取时间周期，跳过: %s", subject)
            return []

        holdings = self._extract_holdings(raw_data, period)
        logger.info("从邮件「%s」解析到 %d 条持仓记录", subject, len(holdings))
        return holdings

    # ------------------------------------------------------------------
    # Overridable hooks（子类可覆盖以适配特定机构格式）
    # ------------------------------------------------------------------

    def _extract_period(self, message: Message) -> Optional[ReportPeriod]:
        """从邮件中提取报告时间周期。

        依次尝试以下匹配规则（子类可覆盖实现机构专属逻辑）：
        1. 「YYYY年第Q季度」
        2. 「YYYY年度对账单」或「YYYY年对账单」
        3. 「YYYY-MM-DD ~ YYYY-MM-DD」日期区间
        """
        subject = _decode_header(message.get("Subject", ""))

        # 规则 1：季度
        m = re.search(r"(\d{4})\s*年\s*[第]?\s*([1-4])\s*季度", subject)
        if m:
            return ReportPeriod.from_year_quarter(int(m.group(1)), int(m.group(2)))

        # 规则 2：全年（兼容「YYYY年度对账单」/「YYYY年年度电子对账单」等写法）
        m = re.search(r"(\d{4})\s*年.*?对账单", subject)
        if m:
            return ReportPeriod.from_year(int(m.group(1)))

        # 规则 3：明确日期区间
        m = re.search(
            r"(\d{4}[-/]\d{2}[-/]\d{2})\s*[~至到－\-]\s*(\d{4}[-/]\d{2}[-/]\d{2})",
            subject,
        )
        if m:
            start = _parse_date(m.group(1))
            end = _parse_date(m.group(2))
            if start and end:
                try:
                    return ReportPeriod(start, end)
                except ValueError:
                    pass

        return None

    def _extract_holdings(
        self, message: Message, period: ReportPeriod
    ) -> List[HoldingRecord]:
        """从 HTML 邮件正文中提取所有持仓记录。

        处理流程：
        1. 从账户摘要表（key-value 形式）提取期初总金额
        2. 从交易明细表（含「业务类型」等列）提取各基金的申购/赎回金额
        3. 仅对剩余持仓表调用 _parse_table
        4. 将交易流水中的入金/出金回填到对应基金的 HoldingRecord
        5. 若持仓表无期初列且存在期初总金额，则按期末市值占比分配（近似值）
        """
        html = _get_html_body(message)
        if not html:
            logger.debug("邮件无 HTML 正文，跳过")
            return []

        soup = BeautifulSoup(html, "html.parser")
        tables = soup.find_all("table")

        # 步骤 1：提取账户期初总金额（如国泰基金年度对账单的基本信息表）
        portfolio_opening = _extract_portfolio_opening(tables)

        # 步骤 2：从交易明细表提取入金/出金，按基金代码汇总
        tx_map = _extract_transaction_map(tables)

        # 步骤 3：解析持仓表格，跳过交易明细表（其行不是持仓记录）
        holdings: List[HoldingRecord] = []
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue
            header_set = {c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])}
            if header_set & _TRANSACTION_TABLE_SIGNALS:
                continue  # 跳过交易明细表
            holdings.extend(self._parse_table(table, period))

        # 步骤 4：将交易流水的入金/出金回填到持仓记录（按基金代码匹配）
        if tx_map:
            for h in holdings:
                code = h.asset.code
                if code and code in tx_map:
                    inflow, outflow = tx_map[code]
                    h.inflow = inflow
                    h.outflow = outflow
            logger.debug("从交易明细表回填了 %d 只基金的入金/出金数据", len(tx_map))

        # 步骤 5：若持仓表无期初列（所有 opening_value 均为 0），且有期初总金额，
        #         则按期末市值占比近似分配（注：这是估算值，非精确的每只基金期初）
        if portfolio_opening is not None and portfolio_opening > Decimal("0"):
            total_holding_opening = sum(h.opening_value for h in holdings)
            if total_holding_opening == Decimal("0") and holdings:
                total_closing = sum(h.closing_value for h in holdings)
                if total_closing > Decimal("0"):
                    for h in holdings:
                        ratio = h.closing_value / total_closing
                        h.opening_value = (portfolio_opening * ratio).quantize(
                            Decimal("0.01")
                        )
                    logger.debug(
                        "期初总金额 ¥%s 已按期末市值占比分配至 %d 只基金（近似）",
                        portfolio_opening,
                        len(holdings),
                    )

        return holdings

    def _parse_table(self, table: Any, period: ReportPeriod) -> List[HoldingRecord]:
        """解析单个 HTML <table> 元素，返回持仓记录列表。"""
        rows = table.find_all("tr")
        if len(rows) < 2:
            return []

        # 提取表头并建立列索引映射
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True) for c in header_cells]
        col_map = _map_columns(headers)

        if "name" not in col_map:
            return []  # 不是持仓表格

        holdings: List[HoldingRecord] = []
        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            record = self._parse_row(cells, col_map, period)
            if record:
                holdings.append(record)
        return holdings

    def _parse_row(
        self,
        cells: List[str],
        col_map: Dict[str, int],
        period: ReportPeriod,
    ) -> Optional[HoldingRecord]:
        """将一行表格数据解析为 HoldingRecord。"""
        try:
            name = cells[col_map["name"]].strip()
            if not name or name in ("合计", "总计", "小计", "汇总"):
                return None  # 跳过合计行

            code: Optional[str] = None
            if "code" in col_map and col_map["code"] < len(cells):
                raw_code = cells[col_map["code"]].strip()
                code = raw_code if raw_code else None

            opening_value = Decimal("0")
            closing_value = Decimal("0")

            if "opening_value" in col_map and col_map["opening_value"] < len(cells):
                opening_value = _parse_decimal(cells[col_map["opening_value"]])

            if "closing_value" in col_map and col_map["closing_value"] < len(cells):
                closing_value = _parse_decimal(cells[col_map["closing_value"]])
            elif "market_value" in col_map and col_map["market_value"] < len(cells):
                # 若无明确的「期末市值」列，退而使用「当前市值」
                closing_value = _parse_decimal(cells[col_map["market_value"]])

            inflow = (
                _parse_decimal(cells[col_map["inflow"]])
                if "inflow" in col_map and col_map["inflow"] < len(cells)
                else Decimal("0")
            )
            outflow = (
                _parse_decimal(cells[col_map["outflow"]])
                if "outflow" in col_map and col_map["outflow"] < len(cells)
                else Decimal("0")
            )

            market, asset_type = self._classify_asset(name, code)
            asset = Asset(name=name, asset_type=asset_type, market=market, code=code)

            return HoldingRecord(
                asset=asset,
                period=period,
                opening_value=opening_value,
                closing_value=closing_value,
                inflow=inflow,
                outflow=outflow,
            )
        except (IndexError, KeyError, InvalidOperation) as exc:
            logger.debug("解析表格行失败 %s: %s", cells, exc)
            return None

    def _classify_asset(
        self, name: str, code: Optional[str]
    ) -> Tuple[Market, AssetType]:
        """根据名称关键词和代码格式推断资产的市场和类别。

        推断优先级：名称关键词 > 代码格式 > 默认值。
        子类可覆盖此方法实现更精确的分类逻辑。
        """
        market = self._default_market
        asset_type = self._default_asset_type

        # --- 优先基于名称关键词推断（直观可靠）---
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

        # --- 基于代码格式推断市场，或在名称无法确定类型时辅助推断类型 ---
        if code:
            if re.fullmatch(r"[A-Z]{1,5}", code):
                # 纯大写字母 → 美股
                market = Market.US_STOCK
                if asset_type == self._default_asset_type:
                    asset_type = AssetType.STOCK
            elif re.fullmatch(r"\d{5}", code) or re.fullmatch(
                r"\d{4,5}\.HK", code, re.IGNORECASE
            ):
                # 5 位数字或 xxxxx.HK → 港股
                market = Market.HK_STOCK
                if asset_type == self._default_asset_type:
                    asset_type = AssetType.STOCK
            elif re.fullmatch(r"\d{6}", code):
                if code[0] == "6":
                    # 6xxxxx → 上海主板股票（如 600519 贵州茅台）
                    if asset_type == self._default_asset_type:
                        asset_type = AssetType.STOCK
                        market = Market.A_SHARE
                elif code[0] == "3":
                    # 3xxxxx → 深圳创业板股票（如 300750）
                    if asset_type == self._default_asset_type:
                        asset_type = AssetType.STOCK
                        market = Market.A_SHARE
                # 其余 6 位代码（0, 1, 2, 4, 5, 7, 8, 9 开头）可能是基金或深证股票
                # 保持名称推断结果，不做进一步覆盖

        return market, asset_type


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _decode_header(value: Any) -> str:
    """将邮件头部值（可能是 Header 对象或编码字符串）解码为普通字符串。"""
    if not value:
        return ""
    # decode_header 处理 =?charset?encoding?text?= 格式
    parts = []
    for part, charset in _email_header.decode_header(str(value)):
        if isinstance(part, bytes):
            parts.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(part))
    return "".join(parts)


def _get_html_body(message: Message) -> Optional[str]:
    """从邮件中提取 HTML 正文。"""
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


def _map_columns(headers: List[str]) -> Dict[str, int]:
    """将表头字符串列表映射为规范列名 → 列索引的字典。"""
    col_map: Dict[str, int] = {}
    for normalized, patterns in _COLUMN_PATTERNS.items():
        for idx, header in enumerate(headers):
            if any(p in header for p in patterns):
                col_map[normalized] = idx
                break
    return col_map


def _parse_decimal(value: str) -> Decimal:
    """将可能含有千分位符、货币符号的字符串解析为 Decimal。"""
    cleaned = re.sub(r"[,，\s¥￥元]", "", value)
    if not cleaned or cleaned in ("-", "--", "N/A", "暂无", "/"):
        return Decimal("0")
    return Decimal(cleaned)


def _parse_date(value: str) -> Optional[date]:
    """将常见日期字符串格式解析为 date 对象。"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _extract_portfolio_opening(tables: Any) -> Optional[Decimal]:
    """从账户摘要表中提取期初总金额。

    适配 key-value 形式的基本信息表（如国泰基金年度对账单的 Table 0）：
        | 期初总金额：  | 52570.36 |
        | 期末变化总金额：| -6076.53 |

    若未找到则返回 None。
    """
    for table in tables:
        all_cell_text = [
            c.get_text(strip=True)
            for row in table.find_all("tr")
            for c in row.find_all(["td", "th"])
        ]
        # 快速过滤：表格中必须含有「期初总金额」字样
        if not any("期初总金额" in t for t in all_cell_text):
            continue
        for row in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) >= 2 and "期初总金额" in cells[0]:
                try:
                    return Decimal(cells[1].replace(",", ""))
                except InvalidOperation:
                    pass
    return None


def _extract_transaction_map(
    tables: Any,
) -> Dict[str, Tuple[Decimal, Decimal]]:
    """从交易明细表提取各基金的累计入金和出金。

    识别含「业务类型」「申请日期」「确认日期」等特征列的表格，
    按基金代码汇总申购（inflow）和赎回（outflow）金额。

    Returns:
        {基金代码: (inflow合计, outflow合计)}
    """
    result: Dict[str, list] = {}  # code → [inflow, outflow]

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not (set(headers) & _TRANSACTION_TABLE_SIGNALS):
            continue

        # 定位关键列索引
        code_idx = next(
            (i for i, h in enumerate(headers) if "代码" in h), None
        )
        type_idx = next(
            (i for i, h in enumerate(headers) if "业务类型" in h), None
        )
        # 金额列：优先匹配「确认金额」「交易金额」「成交金额」，次之匹配任意含「金额」的列
        amt_idx = next(
            (i for i, h in enumerate(headers)
             if any(k in h for k in ("确认金额", "交易金额", "成交金额"))),
            None,
        )
        if amt_idx is None:
            amt_idx = next(
                (i for i, h in enumerate(headers) if "金额" in h), None
            )

        if type_idx is None or amt_idx is None:
            logger.debug("交易明细表缺少必要列（业务类型/金额），跳过")
            continue

        for row in rows[1:]:
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            needed = max(c for c in [type_idx, amt_idx, code_idx] if c is not None)
            if needed >= len(cells):
                continue

            tx_type = cells[type_idx]
            code = cells[code_idx].strip() if code_idx is not None else None
            if not code:
                continue

            try:
                amount = Decimal(cells[amt_idx].replace(",", ""))
            except InvalidOperation:
                continue

            if amount <= Decimal("0"):
                continue

            if code not in result:
                result[code] = [Decimal("0"), Decimal("0")]

            if any(kw in tx_type for kw in _INFLOW_TX_KEYWORDS):
                result[code][0] += amount
            elif any(kw in tx_type for kw in _OUTFLOW_TX_KEYWORDS):
                result[code][1] += amount

    return {k: (v[0], v[1]) for k, v in result.items()}
