"""ReportGenerator 单元测试。"""

from decimal import Decimal

import pytest

from fininsight.models.enums import AssetType, Market
from fininsight.models.records import Asset, HoldingRecord, ReportPeriod
from fininsight.processors.report_generator import ReportGenerator


@pytest.fixture
def generator():
    return ReportGenerator()


@pytest.fixture
def period():
    return ReportPeriod.from_year_quarter(2024, 1)


@pytest.fixture
def asset_a():
    return Asset("基金A", AssetType.FUND, Market.DOMESTIC, "110011")


@pytest.fixture
def asset_b():
    return Asset("基金B", AssetType.FUND, Market.DOMESTIC, "270002")


class TestReportGeneratorBasic:
    def test_generate_single_holding(self, generator, period, asset_a):
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("12000"),
            )
        ]
        report = generator.generate(holdings, period)
        assert len(report.holdings) == 1
        assert report.period == period

    def test_contribution_rate_single_holding(self, generator, period, asset_a):
        """单一标的的贡献率应为 1（100%）。"""
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("12000"),
            )
        ]
        report = generator.generate(holdings, period)
        assert report.holdings[0].contribution_rate == Decimal("1")

    def test_contribution_rates_sum_to_one(self, generator, period, asset_a, asset_b):
        """多个标的的贡献率之和应为 1。"""
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("12000"),
            ),
            HoldingRecord(
                asset=asset_b,
                period=period,
                opening_value=Decimal("5000"),
                closing_value=Decimal("6000"),
            ),
        ]
        report = generator.generate(holdings, period)
        total = sum(h.contribution_rate for h in report.holdings)
        assert total == Decimal("1")

    def test_contribution_rates_correct_split(self, generator, period, asset_a, asset_b):
        """验证贡献率的具体数值。"""
        # a: profit=2000, b: profit=1000, total=3000
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("12000"),
            ),
            HoldingRecord(
                asset=asset_b,
                period=period,
                opening_value=Decimal("5000"),
                closing_value=Decimal("6000"),
            ),
        ]
        report = generator.generate(holdings, period)
        a_record = next(h for h in report.holdings if h.asset.name == "基金A")
        b_record = next(h for h in report.holdings if h.asset.name == "基金B")
        assert a_record.contribution_rate == Decimal("2000") / Decimal("3000")
        assert b_record.contribution_rate == Decimal("1000") / Decimal("3000")

    def test_zero_total_profit_contribution_rates(self, generator, period, asset_a):
        """当总收益为 0 时，所有贡献率应为 0。"""
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("10000"),
            )
        ]
        report = generator.generate(holdings, period)
        assert report.holdings[0].contribution_rate == Decimal("0")

    def test_negative_contribution_rate(self, generator, period, asset_a, asset_b):
        """亏损标的的贡献率应为负数。"""
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("10000"),
                closing_value=Decimal("13000"),  # profit=3000
            ),
            HoldingRecord(
                asset=asset_b,
                period=period,
                opening_value=Decimal("5000"),
                closing_value=Decimal("4000"),   # profit=-1000
            ),
        ]
        report = generator.generate(holdings, period)
        b_record = next(h for h in report.holdings if h.asset.name == "基金B")
        assert b_record.contribution_rate == Decimal("-1000") / Decimal("2000")


class TestReportGeneratorConsolidation:
    def test_consolidate_duplicate_holdings(self, generator, period, asset_a):
        """同一标的的多条记录应合并为一条。"""
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("5000"),
                closing_value=Decimal("6000"),
                inflow=Decimal("500"),
            ),
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("3000"),
                closing_value=Decimal("3500"),
                inflow=Decimal("200"),
            ),
        ]
        report = generator.generate(holdings, period)
        assert len(report.holdings) == 1
        c = report.holdings[0]
        assert c.opening_value == Decimal("8000")
        assert c.closing_value == Decimal("9500")
        assert c.inflow == Decimal("700")

    def test_different_assets_not_merged(self, generator, period, asset_a, asset_b):
        """不同标的不应合并。"""
        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period,
                opening_value=Decimal("5000"),
                closing_value=Decimal("6000"),
            ),
            HoldingRecord(
                asset=asset_b,
                period=period,
                opening_value=Decimal("3000"),
                closing_value=Decimal("3500"),
            ),
        ]
        report = generator.generate(holdings, period)
        assert len(report.holdings) == 2


class TestReportGeneratorPeriodFilter:
    def test_filters_different_period(self, generator, asset_a, asset_b):
        """不属于目标周期的持仓记录应被过滤。"""
        period_q1 = ReportPeriod.from_year_quarter(2024, 1)
        period_q2 = ReportPeriod.from_year_quarter(2024, 2)

        holdings = [
            HoldingRecord(
                asset=asset_a,
                period=period_q1,
                opening_value=Decimal("10000"),
                closing_value=Decimal("12000"),
            ),
            HoldingRecord(
                asset=asset_b,
                period=period_q2,
                opening_value=Decimal("5000"),
                closing_value=Decimal("6000"),
            ),
        ]
        report = generator.generate(holdings, period_q1)
        assert len(report.holdings) == 1
        assert report.holdings[0].asset.name == "基金A"

    def test_empty_holdings(self, generator):
        period = ReportPeriod.from_year_quarter(2024, 1)
        report = generator.generate([], period)
        assert len(report.holdings) == 0
        assert report.total_profit == Decimal("0")
