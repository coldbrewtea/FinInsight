"""tests/test_fullgoal_parser.py

富国基金月度对账单解析器测试。

测试数据文件路径（私有，不提交远端）：
  tests/fixtures/emails/2025_fullgoal_monthly.eml

可通过环境变量 FININSIGHT_EML_DIR 覆盖 fixture 目录：
  FININSIGHT_EML_DIR=/path/to/dir pytest tests/test_fullgoal_parser.py
"""

from __future__ import annotations

import email
import os
from decimal import Decimal
from email.message import Message

import pytest

from fininsight.models.enums import AssetType, Market
from fininsight.parsers.fullgoal_email_parser import FullgoalEmailParser

# ---------------------------------------------------------------------------
# Fixture path resolution
# ---------------------------------------------------------------------------

_DEFAULT_EML_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "emails")
_EML_DIR = os.environ.get("FININSIGHT_EML_DIR", _DEFAULT_EML_DIR)
_FIXTURE = os.path.join(_EML_DIR, "2025_fullgoal_monthly.eml")

_FIXTURE_MISSING = not os.path.exists(_FIXTURE)
_SKIP_REASON = (
    f"真实邮件 fixture 不存在（{_FIXTURE}），"
    "仅限本地测试，不提交到远端。"
)


def _load_fixture(path: str) -> Message:
    with open(path, "rb") as f:
        return email.message_from_bytes(f.read())


# ---------------------------------------------------------------------------
# Unit tests（不依赖 fixture）
# ---------------------------------------------------------------------------


class TestCanParse:
    """can_parse() 的识别逻辑。"""

    PARSER = FullgoalEmailParser()

    def _make_msg(self, from_: str, subject: str) -> Message:
        msg = Message()
        msg["From"] = from_
        msg["Subject"] = subject
        return msg

    def test_match_fullgoal_sender_and_subject(self):
        msg = self._make_msg("public@fullgoal.com.cn", "2025年11月月度对账单")
        assert self.PARSER.can_parse(msg) is True

    def test_match_sender_with_display_name(self):
        msg = self._make_msg("富国基金 <noreply@fullgoal.com.cn>", "2025年11月月度对账单")
        assert self.PARSER.can_parse(msg) is True

    def test_reject_wrong_sender(self):
        msg = self._make_msg("service@gtfund.com", "2025年11月月度对账单")
        assert self.PARSER.can_parse(msg) is False

    def test_reject_no_statement_keyword_in_subject(self):
        msg = self._make_msg("public@fullgoal.com.cn", "富国基金产品推荐")
        assert self.PARSER.can_parse(msg) is False

    def test_reject_non_message(self):
        assert self.PARSER.can_parse("not a message") is False
        assert self.PARSER.can_parse(None) is False
        assert self.PARSER.can_parse({}) is False


# ---------------------------------------------------------------------------
# Integration tests（依赖本地真实 fixture）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_FIXTURE_MISSING, reason=_SKIP_REASON)
class TestFullgoalParserWithFixture:
    """使用真实邮件 fixture 的集成测试。"""

    @pytest.fixture(scope="class")
    def holdings(self):
        parser = FullgoalEmailParser()
        msg = _load_fixture(_FIXTURE)
        return parser.parse(msg)

    # ------------------------------------------------------------------
    # Basic structure
    # ------------------------------------------------------------------

    def test_returns_two_holdings(self, holdings):
        assert len(holdings) == 2

    def test_period(self, holdings):
        for h in holdings:
            assert str(h.period.start_date) == "2025-11-01"
            assert str(h.period.end_date) == "2025-11-30"

    # ------------------------------------------------------------------
    # 000602 富国安益货币A（货币，无交易）
    # ------------------------------------------------------------------

    @pytest.fixture(scope="class")
    def cash_holding(self, holdings):
        result = [h for h in holdings if h.asset.code == "000602"]
        assert result, "未找到 000602 持仓"
        return result[0]

    def test_cash_name(self, cash_holding):
        assert "富国安益货币" in cash_holding.asset.name

    def test_cash_asset_type(self, cash_holding):
        assert cash_holding.asset.asset_type == AssetType.CASH

    def test_cash_market(self, cash_holding):
        assert cash_holding.asset.market == Market.DOMESTIC

    def test_cash_closing_value(self, cash_holding):
        assert cash_holding.closing_value == Decimal("8372.15")

    def test_cash_no_inflow(self, cash_holding):
        assert cash_holding.inflow == Decimal("0")

    def test_cash_no_outflow(self, cash_holding):
        assert cash_holding.outflow == Decimal("0")

    def test_cash_opening_value(self, cash_holding):
        # opening = closing - profit - inflow + outflow = 8372.15 - 9.06 = 8363.09
        assert cash_holding.opening_value == Decimal("8363.09")

    def test_cash_profit(self, cash_holding):
        # profit = closing - opening - inflow + outflow
        assert cash_holding.profit == Decimal("9.06")

    # ------------------------------------------------------------------
    # 100050 富国全球债券（QDII）人民币A（QDII，4 笔申购合计 375.00）
    # ------------------------------------------------------------------

    @pytest.fixture(scope="class")
    def qdii_holding(self, holdings):
        result = [h for h in holdings if h.asset.code == "100050"]
        assert result, "未找到 100050 持仓"
        return result[0]

    def test_qdii_name(self, qdii_holding):
        assert "富国全球债券" in qdii_holding.asset.name

    def test_qdii_asset_type(self, qdii_holding):
        assert qdii_holding.asset.asset_type == AssetType.FUND

    def test_qdii_market(self, qdii_holding):
        assert qdii_holding.asset.market == Market.DOMESTIC

    def test_qdii_closing_value(self, qdii_holding):
        assert qdii_holding.closing_value == Decimal("1180.85")

    def test_qdii_inflow(self, qdii_holding):
        # 4 笔申购：75.00 + 100.00 + 100.00 + 100.00 = 375.00
        assert qdii_holding.inflow == Decimal("375.00")

    def test_qdii_no_outflow(self, qdii_holding):
        assert qdii_holding.outflow == Decimal("0")

    def test_qdii_opening_value(self, qdii_holding):
        # opening = 1180.85 - 4.88 - 375.00 + 0 = 800.97
        assert qdii_holding.opening_value == Decimal("800.97")

    def test_qdii_profit(self, qdii_holding):
        assert qdii_holding.profit == Decimal("4.88")

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def test_total_profit(self, holdings):
        total = sum(h.profit for h in holdings)
        assert total == Decimal("13.94")

    def test_total_closing_value(self, holdings):
        total = sum(h.closing_value for h in holdings)
        assert total == Decimal("9553.00")
