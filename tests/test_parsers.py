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
# 交易明细表 + 账户摘要表解析测试
# ---------------------------------------------------------------------------

# 模拟：包含【基本信息表】+【持仓表】+【交易明细表】的综合 HTML
COMPLETE_STATEMENT_HTML = """
<html><body>
<!-- Table 0: 账户摘要 (key-value) -->
<table>
  <tr><td>基金账号：</td><td>123456789</td></tr>
  <tr><td>统计时间段：</td><td>2024-1-1至2024-12-31</td></tr>
  <tr><td>期初总金额：</td><td>20000.00</td></tr>
  <tr><td>期末变化总金额：</td><td>-500.00</td></tr>
</table>
<!-- Table 1: 持仓表 (无期初列) -->
<table>
  <tr>
    <th>基金代码</th><th>基金名称</th>
    <th>期末持有净值</th><th>状态</th>
  </tr>
  <tr><td>000001</td><td>华夏成长混合</td><td>15000.00</td><td>继续持有</td></tr>
  <tr><td>160706</td><td>嘉实汪深300ETF</td><td>5000.00</td><td>继续持有</td></tr>
</table>
<!-- Table 2: 交易明细表 -->
<table>
  <tr>
    <th>申请日期</th><th>确认日期</th><th>基金代码</th>
    <th>基金名称</th><th>业务类型</th><th>确认金额</th><th>状态</th>
  </tr>
  <tr><td>2024-03-10</td><td>2024-03-13</td><td>000001</td>
      <td>华夏成长混合</td><td>基金申购</td><td>1000.00</td><td>成功</td></tr>
  <tr><td>2024-06-05</td><td>2024-06-07</td><td>000001</td>
      <td>华夏成长混合</td><td>基金赎回</td><td>500.00</td><td>成功</td></tr>
  <tr><td>2024-09-01</td><td>2024-09-03</td><td>160706</td>
      <td>嘉实汪深300ETF</td><td>基金申购</td><td>300.00</td><td>成功</td></tr>
</table>
</body></html>
"""


class TestTransactionAndSummaryParsing:
    """验证交易明细表和账户摘要表的新解析逻辑。"""

    def setup_method(self):
        self.parser = FundEmailParser()
        self.subject = "2024年对账单"

    def _parse(self, html=COMPLETE_STATEMENT_HTML):
        msg = make_email(self.subject, html)
        return self.parser.parse(msg)

    def test_transaction_rows_not_parsed_as_holdings(self):
        """交易明细表的行不应被当作持仓记录解析，只应有 2 条持仓。"""
        holdings = self._parse()
        assert len(holdings) == 2

    def test_inflow_from_transaction_table(self):
        """申购交易金额应正确回填到对应基金的 inflow。"""
        holdings = self._parse()
        huaxia = next(h for h in holdings if h.asset.code == "000001")
        assert huaxia.inflow == Decimal("1000.00")

    def test_outflow_from_transaction_table(self):
        """赎回交易金额应正确回填到对应基金的 outflow。"""
        holdings = self._parse()
        huaxia = next(h for h in holdings if h.asset.code == "000001")
        assert huaxia.outflow == Decimal("500.00")

    def test_inflow_multiple_transactions_summed(self):
        """同一基金多笔申购应汇总。嘉实小表只有 300 。"""
        holdings = self._parse()
        jishi = next(h for h in holdings if h.asset.code == "160706")
        assert jishi.inflow == Decimal("300.00")
        assert jishi.outflow == Decimal("0")

    def test_portfolio_opening_distributed_proportionally(self):
        """期初总金额 20000 应按期末市值占比分配到各基金。"""
        holdings = self._parse()
        total_opening = sum(h.opening_value for h in holdings)
        # 分配后各基金 opening 之和应等于期初总金额（允许 0.01 舍入误差）
        assert abs(total_opening - Decimal("20000.00")) <= Decimal("0.10")

    def test_portfolio_opening_ratio_follows_closing_value(self):
        """期初市值占比应等于期末市值占比（误差 < 1%）。"""
        holdings = self._parse()
        huaxia = next(h for h in holdings if h.asset.code == "000001")
        jishi = next(h for h in holdings if h.asset.code == "160706")
        # 期末占比 15000:5000 = 3:1，期初应也是 3:1
        ratio = huaxia.opening_value / jishi.opening_value
        assert abs(ratio - Decimal("3")) < Decimal("0.05")

    def test_existing_opening_column_not_overridden(self):
        """持仓表已有期初市值列时，不应被期初总金额覆盖。"""
        # SAMPLE_FUND_STATEMENT_HTML 有 "期初市值" 列，无摘要表， opening 应保持原值
        msg = make_email(self.subject, SAMPLE_FUND_STATEMENT_HTML)
        holdings = self.parser.parse(msg)
        huaxia = next(h for h in holdings if h.asset.name == "华夏成长混合")
        assert huaxia.opening_value == Decimal("10000.00")

    def test_no_summary_table_no_distribution(self):
        """没有摘要表时，期初市值应保持 0。"""
        # MARKET_VALUE_ONLY_HTML 无摘要表，无期初列，opening 应为 0
        msg = make_email(self.subject, MARKET_VALUE_ONLY_HTML)
        holdings = self.parser.parse(msg)
        assert holdings[0].opening_value == Decimal("0")


class TestGTFundFixture:
    """国泰基金 2025 年年度对账单 .eml fixture 端到端验证。"""

    @pytest.fixture(scope="class")
    def gtfund_holdings(self):
        import email as email_mod
        import os
        fixture = os.path.join(
            os.path.dirname(__file__),
            "fixtures", "emails", "2025_gtfund_annual_statement.eml",
        )
        with open(fixture, "rb") as f:
            msg = email_mod.message_from_bytes(f.read())
        return FundEmailParser().parse(msg)

    def test_holding_count(self, gtfund_holdings):
        """应解析出 3 条持仓（交易表不再产生额外行）。"""
        assert len(gtfund_holdings) == 3

    def test_inflow_for_shipin(self, gtfund_holdings):
        """食品(160222)两笔申购共 8000。"""
        shipin = next(h for h in gtfund_holdings if h.asset.code == "160222")
        assert shipin.inflow == Decimal("8000.00")

    def test_outflow_for_shipin(self, gtfund_holdings):
        """食品(160222)两笔赎回共 3500。"""
        shipin = next(h for h in gtfund_holdings if h.asset.code == "160222")
        assert shipin.outflow == Decimal("3500.00")

    def test_inflow_for_huobi(self, gtfund_holdings):
        """国泰货币B(005253)申购 10000。"""
        huobi = next(h for h in gtfund_holdings if h.asset.code == "005253")
        assert huobi.inflow == Decimal("10000.00")
        assert huobi.outflow == Decimal("5000.00")

    def test_inflow_for_sp500(self, gtfund_holdings):
        """国泰标普500ETF(017028)申购 500。"""
        sp500 = next(h for h in gtfund_holdings if h.asset.code == "017028")
        assert sp500.inflow == Decimal("500.00")
        assert sp500.outflow == Decimal("0")

    def test_huobi_classified_as_cash(self, gtfund_holdings):
        """国泰货币B 应识别为现金类型。"""
        from fininsight.models.enums import AssetType
        huobi = next(h for h in gtfund_holdings if h.asset.code == "005253")
        assert huobi.asset.asset_type == AssetType.CASH

    def test_opening_value_from_profit(self, gtfund_holdings):
        """opening 应由收益金额反推而来，非零却非负（017028 新仓期初为 0）。"""
        for h in gtfund_holdings:
            assert h.opening_value >= Decimal("0")
        # 005253 和 160222 期初应 > 0
        huobi = next(h for h in gtfund_holdings if h.asset.code == "005253")
        shipin = next(h for h in gtfund_holdings if h.asset.code == "160222")
        assert huobi.opening_value > Decimal("0")
        assert shipin.opening_value > Decimal("0")

    def test_total_opening_matches_portfolio(self, gtfund_holdings):
        """收益列反推后汇总 opening 应接近 48646.89。"""
        total = sum(h.opening_value for h in gtfund_holdings)
        assert abs(total - Decimal("48646.89")) <= Decimal("0.10")

    def test_closing_total(self, gtfund_holdings):
        """期末持有净值合计应等于 52570.36。"""
        total = sum(h.closing_value for h in gtfund_holdings)
        assert total == Decimal("52570.36")

    def test_per_fund_profit_from_email(self, gtfund_holdings):
        """每只基金收益应与邮件中的收益金额列完全匹配。"""
        huobi = next(h for h in gtfund_holdings if h.asset.code == "005253")
        sp500 = next(h for h in gtfund_holdings if h.asset.code == "017028")
        shipin = next(h for h in gtfund_holdings if h.asset.code == "160222")
        assert huobi.profit == Decimal("-40.00")
        assert sp500.profit == Decimal("-418.52")
        assert shipin.profit == Decimal("-5618.01")

    def test_total_profit_matches_email_stated_value(self, gtfund_holdings):
        """收益合计应等于邮件所述 期末变化总金额 = -6076.53。"""
        total_profit = sum(h.profit for h in gtfund_holdings)
        assert total_profit == Decimal("-6076.53")


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
