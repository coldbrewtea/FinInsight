"""tests/test_efund_parser.py

易方达基金月度对账单解析器测试。

测试数据文件路径（私有，不提交远端）：
  tests/fixtures/emails/2026_efund_monthly_apr.eml
  tests/fixtures/emails/2026_efund_monthly_may.eml

可通过环境变量 FININSIGHT_EML_DIR 覆盖 fixture 目录：
  FININSIGHT_EML_DIR=/path/to/dir pytest tests/test_efund_parser.py
"""

from __future__ import annotations

import email
import os
from decimal import Decimal
from email.message import Message

import pytest

from fininsight.models.enums import AssetType, Market
from fininsight.parsers.efund_email_parser import EfundEmailParser

# ---------------------------------------------------------------------------
# Fixture path resolution
# ---------------------------------------------------------------------------

_DEFAULT_EML_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "emails")
_EML_DIR = os.environ.get("FININSIGHT_EML_DIR", _DEFAULT_EML_DIR)
_FIXTURE_APR = os.path.join(_EML_DIR, "2026_efund_monthly_apr.eml")
_FIXTURE_MAY = os.path.join(_EML_DIR, "2026_efund_monthly_may.eml")

_APR_MISSING = not os.path.exists(_FIXTURE_APR)
_MAY_MISSING = not os.path.exists(_FIXTURE_MAY)
_SKIP_REASON = (
    "真实邮件 fixture 不存在，仅限本地测试，不提交到远端。"
)


def _load_fixture(path: str) -> Message:
    with open(path, "rb") as f:
        return email.message_from_bytes(f.read())


# ---------------------------------------------------------------------------
# Unit tests（不依赖 fixture）
# ---------------------------------------------------------------------------


class TestCanParse:
    """can_parse() 的识别逻辑。"""

    PARSER = EfundEmailParser()

    def _make_msg(self, from_: str, subject: str) -> Message:
        msg = Message()
        msg["From"] = from_
        msg["Subject"] = subject
        return msg

    def test_match_efund_sender_and_subject(self):
        msg = self._make_msg("易方达基金 <service06@efunds.com.cn>", "易方达电子对账单")
        assert self.PARSER.can_parse(msg) is True

    def test_match_efund_sender_variant(self):
        msg = self._make_msg("service23@efunds.com.cn", "易方达电子对账单")
        assert self.PARSER.can_parse(msg) is True

    def test_reject_wrong_sender(self):
        msg = self._make_msg("service@fullgoal.com.cn", "易方达电子对账单")
        assert self.PARSER.can_parse(msg) is False

    def test_reject_wrong_subject_no_keyword(self):
        msg = self._make_msg("service06@efunds.com.cn", "营销资讯")
        assert self.PARSER.can_parse(msg) is False

    def test_reject_non_message(self):
        assert self.PARSER.can_parse("not a message") is False

    def test_reject_none(self):
        assert self.PARSER.can_parse(None) is False


# ---------------------------------------------------------------------------
# 单元测试：使用内联 HTML（不依赖 fixture 文件）
# ---------------------------------------------------------------------------

# 模拟易方达对账单 HTML（与真实邮件格式一致）
_MOCK_HTML = """
<html><body>
<table>
<tr><td>
尊敬的张先生，您好！对账单起止日期：2026-04-01~2026-04-30基金账号：111******593
</td></tr>
</table>

<table>
  <tr>
    <td>基金报价单位：元</td>
  </tr>
  <tr>
    <td>基金代码</td><td>基金名称</td><td>当前余额(份)</td><td>未付收益(份)</td>
    <td>分红方式</td><td>销售机构</td><td>净值日期</td><td>单位净值</td><td>参考市值</td>
  </tr>
  <tr>
    <td>007346</td><td>易方达科技创新混合A</td><td>2788.08</td><td></td>
    <td>现金红利</td><td>蚂蚁基金</td><td>20260430</td><td>5.4225</td><td>15118.36</td>
  </tr>
  <tr>
    <td>011609</td><td>易方达上证科创50ETF联接C</td><td>48662.40</td><td></td>
    <td>现金红利</td><td>蚂蚁基金</td><td>20260430</td><td>1.2012</td><td>58453.27</td>
  </tr>
  <tr>
    <td>110027</td><td>易方达安心回报债券A</td><td>38699.37</td><td></td>
    <td>现金红利</td><td>蚂蚁基金</td><td>20260430</td><td>2.2788</td><td>88184.25</td>
  </tr>
  <tr>
    <td>合计</td><td></td><td>90149.85</td><td></td>
    <td></td><td></td><td></td><td></td><td>161755.88</td>
  </tr>
</table>

<table>
  <tr>
    <td>确认日期</td><td>基金名称</td><td>销售机构</td><td>业务类型</td>
    <td>成交净值</td><td>确认金额</td><td>确认份额(份)</td><td>手续费</td><td>单位</td><td>确认结果</td>
  </tr>
  <tr>
    <td>2026-04-03</td><td>易方达科技创新混合A</td><td>蚂蚁基金</td><td>申购</td>
    <td>4.2651</td><td>1500.00</td><td>117.05</td><td>0.75</td><td>元</td><td>确认成功</td>
  </tr>
  <tr>
    <td>2026-04-10</td><td>易方达科技创新混合A</td><td>蚂蚁基金</td><td>申购</td>
    <td>4.7234</td><td>500.00</td><td>105.70</td><td>0.75</td><td>元</td><td>确认成功</td>
  </tr>
  <tr>
    <td>2026-04-10</td><td>易方达上证科创50ETF联接C</td><td>蚂蚁基金</td><td>申购</td>
    <td>1.0349</td><td>200.00</td><td>193.26</td><td>0.00</td><td>元</td><td>确认成功</td>
  </tr>
  <tr>
    <td>2026-04-13</td><td>易方达安心回报债券A</td><td>蚂蚁基金</td><td>申购</td>
    <td>2.2288</td><td>500.00</td><td>224.16</td><td>0.40</td><td>元</td><td>确认成功</td>
  </tr>
  <tr>
    <td>2026-04-20</td><td>易方达上证科创50ETF联接C</td><td>蚂蚁基金</td><td>赎回</td>
    <td>1.0500</td><td>300.00</td><td>285.71</td><td>0.00</td><td>元</td><td>确认成功</td>
  </tr>
</table>
</body></html>
"""


def _make_efund_msg(html: str, subject: str = "易方达电子对账单") -> Message:
    """构造一封模拟的易方达邮件（text/html，GBK 编码）。"""
    import base64

    msg = Message()
    msg["From"] = "易方达基金 <service06@efunds.com.cn>"
    msg["Subject"] = subject
    msg["Content-Type"] = "text/html; charset=utf-8"
    msg["Content-Transfer-Encoding"] = "base64"
    msg.set_payload(base64.encodebytes(html.encode("utf-8")).decode("ascii"))
    return msg


class TestPeriodExtraction:
    """账单期间提取测试。"""

    PARSER = EfundEmailParser()

    def test_period_extracted_correctly(self):
        msg = _make_efund_msg(_MOCK_HTML)
        holdings = self.PARSER.parse(msg)
        assert len(holdings) > 0
        period = holdings[0].period
        assert str(period.start_date) == "2026-04-01"
        assert str(period.end_date) == "2026-04-30"

    def test_no_period_returns_empty(self):
        msg = _make_efund_msg("<html><body><p>无日期信息</p></body></html>")
        holdings = self.PARSER.parse(msg)
        assert holdings == []


class TestHoldingsParsing:
    """持仓表解析测试。"""

    PARSER = EfundEmailParser()

    def _parse(self, html: str = _MOCK_HTML):
        msg = _make_efund_msg(html)
        return self.PARSER.parse(msg)

    def test_holding_count(self):
        """合计行不应被解析为持仓记录，应有 3 条。"""
        holdings = self._parse()
        assert len(holdings) == 3

    def test_holding_names(self):
        names = {h.asset.name for h in self._parse()}
        assert "易方达科技创新混合A" in names
        assert "易方达上证科创50ETF联接C" in names
        assert "易方达安心回报债券A" in names

    def test_holding_codes(self):
        holdings = self._parse()
        code_map = {h.asset.name: h.asset.code for h in holdings}
        assert code_map["易方达科技创新混合A"] == "007346"
        assert code_map["易方达上证科创50ETF联接C"] == "011609"
        assert code_map["易方达安心回报债券A"] == "110027"

    def test_closing_value(self):
        holdings = self._parse()
        val_map = {h.asset.name: h.closing_value for h in holdings}
        assert val_map["易方达科技创新混合A"] == Decimal("15118.36")
        assert val_map["易方达上证科创50ETF联接C"] == Decimal("58453.27")
        assert val_map["易方达安心回报债券A"] == Decimal("88184.25")

    def test_asset_market_is_domestic(self):
        for h in self._parse():
            assert h.asset.market == Market.DOMESTIC

    def test_etf_asset_type_is_fund(self):
        holdings = self._parse()
        etf = next(h for h in holdings if "ETF" in h.asset.name)
        assert etf.asset.asset_type == AssetType.FUND


class TestTransactionParsing:
    """交易流水回填 inflow/outflow 测试。"""

    PARSER = EfundEmailParser()

    def _parse(self, html: str = _MOCK_HTML):
        msg = _make_efund_msg(html)
        return self.PARSER.parse(msg)

    def test_inflow_summed_correctly(self):
        """科技创新混合 A 有两笔申购：1500 + 500 = 2000。"""
        holdings = self._parse()
        kj = next(h for h in holdings if h.asset.name == "易方达科技创新混合A")
        assert kj.inflow == Decimal("2000.00")

    def test_single_inflow(self):
        """安心回报只有一笔申购 500。"""
        holdings = self._parse()
        ax = next(h for h in holdings if h.asset.name == "易方达安心回报债券A")
        assert ax.inflow == Decimal("500.00")

    def test_outflow_from_transaction(self):
        """科创50 ETF 有一笔赎回 300。"""
        holdings = self._parse()
        etf = next(h for h in holdings if h.asset.name == "易方达上证科创50ETF联接C")
        assert etf.outflow == Decimal("300.00")

    def test_inflow_and_outflow_same_fund(self):
        """科创50 ETF：申购 200 + 赎回 300。"""
        holdings = self._parse()
        etf = next(h for h in holdings if h.asset.name == "易方达上证科创50ETF联接C")
        assert etf.inflow == Decimal("200.00")
        assert etf.outflow == Decimal("300.00")

    def test_no_transaction_means_zero(self):
        """无交易记录的基金 inflow/outflow 均为 0（本测试中安心回报无赎回）。"""
        holdings = self._parse()
        ax = next(h for h in holdings if h.asset.name == "易方达安心回报债券A")
        assert ax.outflow == Decimal("0")


class TestFailedTransactionFiltered:
    """失败交易不计入 inflow/outflow。"""

    PARSER = EfundEmailParser()

    _HTML_WITH_FAILED = _MOCK_HTML.replace(
        "<td>确认成功</td>\n  </tr>\n  <tr>\n    <td>2026-04-20</td>",
        "<td>确认成功</td>\n  </tr>\n  <tr>\n    <td>2026-04-19</td>"
        "<td>易方达科技创新混合A</td><td>蚂蚁基金</td><td>赎回</td>"
        "<td>5.0000</td><td>9999.00</td><td>1999.80</td><td>0.00</td><td>元</td><td>撤销</td>"
        "</tr>\n  <tr>\n    <td>2026-04-20</td>",
    )

    def test_cancelled_transaction_not_counted(self):
        msg = _make_efund_msg(self._HTML_WITH_FAILED)
        holdings = self.PARSER.parse(msg)
        kj = next(h for h in holdings if h.asset.name == "易方达科技创新混合A")
        # 撤销的赎回不应计入 outflow
        assert kj.outflow == Decimal("0")


# ---------------------------------------------------------------------------
# 集成测试：使用真实 .eml fixture（仅本地）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_APR_MISSING, reason=_SKIP_REASON)
class TestRealFixtureApril:
    """使用真实 4 月对账单 .eml 的集成测试。"""

    PARSER = EfundEmailParser()

    @pytest.fixture(scope="class")
    def holdings(self):
        msg = _load_fixture(_FIXTURE_APR)
        return self.PARSER.parse(msg)

    def test_can_parse_real_email(self):
        msg = _load_fixture(_FIXTURE_APR)
        assert self.PARSER.can_parse(msg) is True

    def test_returns_holdings(self, holdings):
        assert len(holdings) > 0

    def test_period_is_april_2026(self, holdings):
        period = holdings[0].period
        assert period.start_date.year == 2026
        assert period.start_date.month == 4

    def test_all_closing_values_positive(self, holdings):
        for h in holdings:
            assert h.closing_value >= Decimal("0"), (
                f"{h.asset.name} closing_value 不应为负"
            )

    def test_all_assets_have_names(self, holdings):
        for h in holdings:
            assert h.asset.name, "资产名称不应为空"

    def test_codes_are_six_digits(self, holdings):
        for h in holdings:
            if h.asset.code:
                assert len(h.asset.code) == 6, (
                    f"{h.asset.name} 基金代码 {h.asset.code!r} 不是 6 位"
                )


@pytest.mark.skipif(_MAY_MISSING, reason=_SKIP_REASON)
class TestRealFixtureMay:
    """使用真实 5 月对账单 .eml 的集成测试。"""

    PARSER = EfundEmailParser()

    @pytest.fixture(scope="class")
    def holdings(self):
        msg = _load_fixture(_FIXTURE_MAY)
        return self.PARSER.parse(msg)

    def test_can_parse_real_email(self):
        msg = _load_fixture(_FIXTURE_MAY)
        assert self.PARSER.can_parse(msg) is True

    def test_returns_holdings(self, holdings):
        assert len(holdings) > 0

    def test_period_is_may_2026(self, holdings):
        period = holdings[0].period
        assert period.start_date.year == 2026
        assert period.start_date.month == 5

    def test_all_closing_values_positive(self, holdings):
        for h in holdings:
            assert h.closing_value >= Decimal("0")

    def test_inflow_non_negative(self, holdings):
        for h in holdings:
            assert h.inflow >= Decimal("0"), f"{h.asset.name} inflow 不应为负"

    def test_outflow_non_negative(self, holdings):
        for h in holdings:
            assert h.outflow >= Decimal("0"), f"{h.asset.name} outflow 不应为负"
