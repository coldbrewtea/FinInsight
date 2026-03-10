"""数据模型单元测试。

覆盖：Asset、ReportPeriod、HoldingRecord、Report
"""

from datetime import date
from decimal import Decimal

import pytest

from fininsight.models.enums import AssetType, Market
from fininsight.models.records import Asset, HoldingRecord, Report, ReportPeriod


# ---------------------------------------------------------------------------
# ReportPeriod
# ---------------------------------------------------------------------------

class TestReportPeriod:
    def test_from_year_quarter_q1(self):
        p = ReportPeriod.from_year_quarter(2024, 1)
        assert p.start_date == date(2024, 1, 1)
        assert p.end_date == date(2024, 3, 31)

    def test_from_year_quarter_q2(self):
        p = ReportPeriod.from_year_quarter(2024, 2)
        assert p.start_date == date(2024, 4, 1)
        assert p.end_date == date(2024, 6, 30)

    def test_from_year_quarter_q3(self):
        p = ReportPeriod.from_year_quarter(2024, 3)
        assert p.start_date == date(2024, 7, 1)
        assert p.end_date == date(2024, 9, 30)

    def test_from_year_quarter_q4(self):
        p = ReportPeriod.from_year_quarter(2024, 4)
        assert p.start_date == date(2024, 10, 1)
        assert p.end_date == date(2024, 12, 31)

    def test_from_year(self):
        p = ReportPeriod.from_year(2023)
        assert p.start_date == date(2023, 1, 1)
        assert p.end_date == date(2023, 12, 31)

    def test_invalid_quarter(self):
        with pytest.raises(ValueError):
            ReportPeriod.from_year_quarter(2024, 0)
        with pytest.raises(ValueError):
            ReportPeriod.from_year_quarter(2024, 5)

    def test_invalid_date_range(self):
        with pytest.raises(ValueError):
            ReportPeriod(date(2024, 6, 1), date(2024, 1, 1))

    def test_str_representation(self):
        p = ReportPeriod.from_year_quarter(2024, 1)
        assert str(p) == "2024-01-01 ~ 2024-03-31"

    def test_frozen(self):
        p = ReportPeriod.from_year_quarter(2024, 1)
        with pytest.raises((AttributeError, TypeError)):
            p.start_date = date(2024, 2, 1)  # type: ignore[misc]

    def test_equality(self):
        p1 = ReportPeriod.from_year_quarter(2024, 1)
        p2 = ReportPeriod.from_year_quarter(2024, 1)
        assert p1 == p2


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------

class TestAsset:
    def test_str_with_code(self):
        a = Asset("华夏成长混合", AssetType.FUND, Market.DOMESTIC, "000001")
        assert str(a) == "华夏成长混合(000001)"

    def test_str_without_code(self):
        a = Asset("实物黄金", AssetType.GOLD, Market.DOMESTIC)
        assert str(a) == "实物黄金"

    def test_frozen(self):
        a = Asset("测试", AssetType.FUND, Market.DOMESTIC)
        with pytest.raises((AttributeError, TypeError)):
            a.name = "修改"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HoldingRecord
# ---------------------------------------------------------------------------

class TestHoldingRecord:
    def setup_method(self):
        self.asset = Asset("华夏成长混合", AssetType.FUND, Market.DOMESTIC, "000001")
        self.period = ReportPeriod.from_year_quarter(2024, 1)

    def test_profit_gain(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("11000"),
        )
        assert h.profit == Decimal("1000")

    def test_profit_with_inflow(self):
        # profit = 11200 - 10000 - 500 + 0 = 700
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("11200"),
            inflow=Decimal("500"),
        )
        assert h.profit == Decimal("700")

    def test_profit_with_outflow(self):
        # profit = 9500 - 10000 - 0 + 1000 = 500
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("9500"),
            outflow=Decimal("1000"),
        )
        assert h.profit == Decimal("500")

    def test_profit_loss(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("9000"),
        )
        assert h.profit == Decimal("-1000")

    def test_profit_rate_basic(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("11000"),
        )
        assert h.profit_rate == Decimal("0.1")

    def test_profit_rate_with_inflow(self):
        # profit = 11200 - 10000 - 500 = 700; rate = 700 / (10000 + 500) = 700/10500
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("11200"),
            inflow=Decimal("500"),
        )
        expected = Decimal("700") / Decimal("10500")
        assert h.profit_rate == expected

    def test_profit_rate_zero_denominator(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("0"),
            closing_value=Decimal("0"),
        )
        assert h.profit_rate == Decimal("0")

    def test_default_inflow_outflow(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("1000"),
            closing_value=Decimal("1100"),
        )
        assert h.inflow == Decimal("0")
        assert h.outflow == Decimal("0")

    def test_contribution_rate_default_none(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("1000"),
            closing_value=Decimal("1100"),
        )
        assert h.contribution_rate is None

    def test_contribution_rate_mutable(self):
        h = HoldingRecord(
            asset=self.asset,
            period=self.period,
            opening_value=Decimal("1000"),
            closing_value=Decimal("1100"),
        )
        h.contribution_rate = Decimal("0.5")
        assert h.contribution_rate == Decimal("0.5")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class TestReport:
    def setup_method(self):
        self.period = ReportPeriod.from_year_quarter(2024, 1)
        asset_a = Asset("基金A", AssetType.FUND, Market.DOMESTIC, "110011")
        asset_b = Asset("基金B", AssetType.FUND, Market.DOMESTIC, "270002")
        self.holdings = [
            HoldingRecord(
                asset=asset_a,
                period=self.period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("12000"),
                inflow=Decimal("1000"),
            ),
            HoldingRecord(
                asset=asset_b,
                period=self.period,
                opening_value=Decimal("5000"),
                closing_value=Decimal("4500"),
            ),
        ]

    def test_total_profit(self):
        report = Report(period=self.period, holdings=self.holdings)
        # h1: 12000 - 10000 - 1000 = 1000
        # h2: 4500 - 5000 = -500
        assert report.total_profit == Decimal("500")

    def test_total_opening_value(self):
        report = Report(period=self.period, holdings=self.holdings)
        assert report.total_opening_value == Decimal("15000")

    def test_total_closing_value(self):
        report = Report(period=self.period, holdings=self.holdings)
        assert report.total_closing_value == Decimal("16500")

    def test_total_inflow(self):
        report = Report(period=self.period, holdings=self.holdings)
        assert report.total_inflow == Decimal("1000")

    def test_total_outflow(self):
        report = Report(period=self.period, holdings=self.holdings)
        assert report.total_outflow == Decimal("0")

    def test_total_profit_rate(self):
        report = Report(period=self.period, holdings=self.holdings)
        # net_inflow = 1000; denominator = 15000 + 1000 = 16000
        # rate = 500 / 16000 = 0.03125
        assert report.total_profit_rate == Decimal("500") / Decimal("16000")

    def test_empty_holdings(self):
        report = Report(period=self.period, holdings=[])
        assert report.total_profit == Decimal("0")
        assert report.total_opening_value == Decimal("0")
        assert report.total_profit_rate == Decimal("0")
