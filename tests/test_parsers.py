"""FundEmailParser 单元测试。"""

import email as email_mod
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from fininsight.models.enums import AssetType, Market
from fininsight.models.records import ReportPeriod
from fininsight.parsers.fund_email_parser import FundEmailParser


# ---------------------------------------------------------------------------
# 测试 HTML 邮件构造工具函数
# ---------------------------------------------------------------------------

def make_email(
    subject: str,
    html_body: str,
    sender: str = "no-reply@fund.example.com",
) -> email_mod.message.Message:
    """构造用于测试的模拟邮件消息。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "investor@example.com"
    part = MIMEText(html_body, "html", "utf-8")
    msg.attach(part)
    return msg


# ---------------------------------------------------------------------------
# 模拟基金对账单 HTML
# ---------------------------------------------------------------------------

SAMPLE_FUND_STATEMENT_HTML = """
<html><body>
<p>尊敬的投资者，以下是您的持仓情况：</p>
<table>
  <tr>
    <th>基金名称</th>
    <th>基金代码</th>
    <th>期初市值</th>
    <th>申购金额</th>
    <th>赎回金额</th>
    <th>期末市值</th>
  </tr>
  <tr>
    <td>华夏成长混合</td>
    <td>000001</td>
    <td>10,000.00</td>
    <td>500.00</td>
    <td>0.00</td>
    <td>11,200.00</td>
  </tr>
  <tr>
    <td>嘉实沪深300ETF</td>
    <td>160706</td>
    <td>5000.00</td>
    <td>0.00</td>
    <td>1000.00</td>
    <td>4200.00</td>
  </tr>
  <tr>
    <td>合计</td>
    <td></td>
    <td>15000.00</td>
    <td>500.00</td>
    <td>1000.00</td>
    <td>15400.00</td>
  </tr>
</table>
</body></html>
"""

MARKET_VALUE_ONLY_HTML = """
<html><body>
<table>
  <tr>
    <th>基金名称</th>
    <th>基金代码</th>
    <th>最新市值</th>
  </tr>
  <tr>
    <td>招商中证白酒指数</td>
    <td>161725</td>
    <td>8888.88</td>
  </tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# can_parse 测试
# ---------------------------------------------------------------------------

class TestFundEmailParserCanParse:
    def setup_method(self):
        self.parser = FundEmailParser()

    def test_can_parse_quarterly_statement(self):
        msg = make_email("2024年第1季度对账单", "<html></html>")
        assert self.parser.can_parse(msg)

    def test_can_parse_holding_statement(self):
        msg = make_email("您的持仓报告", "<html></html>")
        assert self.parser.can_parse(msg)

    def test_can_parse_annual_statement(self):
        msg = make_email("2024年对账单", "<html></html>")
        assert self.parser.can_parse(msg)

    def test_cannot_parse_generic_email(self):
        msg = make_email("这是一封普通邮件", "<html></html>")
        assert not self.parser.can_parse(msg)

    def test_cannot_parse_non_message(self):
        assert not self.parser.can_parse("not an email")
        assert not self.parser.can_parse(None)
        assert not self.parser.can_parse({"subject": "test"})

    def test_sender_pattern_allows_trusted(self):
        parser = FundEmailParser(sender_patterns=[r".*@trusted-fund\.com"])
        msg = make_email(
            "2024年第1季度对账单",
            "<html></html>",
            sender="noreply@trusted-fund.com",
        )
        assert parser.can_parse(msg)

    def test_sender_pattern_blocks_unknown(self):
        parser = FundEmailParser(sender_patterns=[r".*@trusted-fund\.com"])
        msg = make_email(
            "2024年第1季度对账单",
            "<html></html>",
            sender="spam@unknown.com",
        )
        assert not parser.can_parse(msg)

    def test_no_sender_pattern_allows_all(self):
        """未配置发件人白名单时，任意发件人均可通过检查。"""
        parser = FundEmailParser(sender_patterns=[])
        msg = make_email("2024年第1季度对账单", "<html></html>", sender="any@sender.com")
        assert parser.can_parse(msg)


# ---------------------------------------------------------------------------
# parse - 时间周期提取测试
# ---------------------------------------------------------------------------

class TestFundEmailParserPeriod:
    def setup_method(self):
        self.parser = FundEmailParser()

    def test_extract_quarter_period(self):
        msg = make_email("2024年第1季度对账单", SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        assert len(holdings) > 0
        assert holdings[0].period == ReportPeriod.from_year_quarter(2024, 1)

    def test_extract_annual_period(self):
        msg = make_email("2024年对账单", SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        assert len(holdings) > 0
        assert holdings[0].period == ReportPeriod.from_year(2024)

    def test_unknown_period_returns_empty(self):
        msg = make_email("持仓报告（无日期）", SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        assert holdings == []


# ---------------------------------------------------------------------------
# parse - 持仓数据提取测试
# ---------------------------------------------------------------------------

class TestFundEmailParserHoldings:
    def setup_method(self):
        self.parser = FundEmailParser()
        self.subject = "2024年第1季度对账单"

    def test_parse_holding_count(self):
        """合计行应被跳过，只解析有效的持仓行。"""
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        assert len(holdings) == 2

    def test_parse_asset_name(self):
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        names = {h.asset.name for h in holdings}
        assert "华夏成长混合" in names
        assert "嘉实沪深300ETF" in names

    def test_parse_asset_code(self):
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.asset.code == "000001"

    def test_parse_opening_value(self):
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.opening_value == Decimal("10000.00")

    def test_parse_closing_value(self):
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.closing_value == Decimal("11200.00")

    def test_parse_inflow(self):
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.inflow == Decimal("500.00")

    def test_parse_outflow(self):
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        jishi = next(h for h in holdings if h.asset.name == "嘉实沪深300ETF")
        assert jishi.outflow == Decimal("1000.00")

    def test_profit_calculated_correctly(self):
        """profit = closing - opening - inflow + outflow = 11200 - 10000 - 500 + 0 = 700"""
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.profit == Decimal("700.00")

    def test_parse_market_value_only_column(self):
        """当表格只有「最新市值」而无「期末市值」列时，应使用最新市值作为期末市值。"""
        msg = make_email(self.subject, MARKET_VALUE_ONLY_HTML)
        holdings = self.parser.parse(msg)
        assert len(holdings) == 1
        assert holdings[0].closing_value == Decimal("8888.88")

    def test_parse_thousand_separator(self):
        """金额中含千分位逗号（10,000.00）应正确解析。"""
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.opening_value == Decimal("10000.00")


# ---------------------------------------------------------------------------
# parse - 资产分类测试
# ---------------------------------------------------------------------------

class TestFundEmailParserClassification:
    def setup_method(self):
        self.parser = FundEmailParser()

    def _parse_holding(self, name: str, code: str, subject: str = "2024年第1季度对账单"):
        html = f"""
        <html><body>
        <table>
          <tr><th>基金名称</th><th>基金代码</th><th>期末市值</th></tr>
          <tr><td>{name}</td><td>{code}</td><td>10000.00</td></tr>
        </table>
        </body></html>
        """
        msg = make_email(subject, html)
        holdings = self.parser.parse(msg)
        return holdings[0] if holdings else None

    def test_fund_classified_as_fund(self):
        h = self._parse_holding("华夏成长混合", "000001")
        assert h is not None
        assert h.asset.asset_type == AssetType.FUND

    def test_stock_6_classified_as_a_share(self):
        """60xxxx 代码应识别为 A 股股票。"""
        h = self._parse_holding("贵州茅台", "600519")
        assert h is not None
        assert h.asset.asset_type == AssetType.STOCK
        assert h.asset.market == Market.A_SHARE

    def test_etf_name_classified_as_fund(self):
        h = self._parse_holding("沪深300ETF", "510300")
        assert h is not None
        assert h.asset.asset_type == AssetType.FUND

    def test_gold_classified_correctly(self):
        h = self._parse_holding("实物黄金积累计划", "")
        assert h is not None
        assert h.asset.asset_type == AssetType.GOLD
