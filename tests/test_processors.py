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
        """同一标的同一周期两条记录：合并后取最早记录的 opening_value（非累加）。"""
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
        # 按 period.start_date 排序后两条记录相同，取第一条的 opening_value
        assert c.opening_value == Decimal("5000")
        assert c.closing_value == Decimal("3500")  # 取最晚的 closing
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


class TestReportGeneratorOpeningValueResolution:
    """跨月推算期初市值的测试。"""

    def test_prior_month_closing_becomes_opening(self, generator, asset_a):
        """4月 opening=0，存在3月数据时，3月 closing 应作为4月 opening。"""
        period_mar = ReportPeriod.from_year_quarter(2024, 1)  # 使用Q1代替
        # 模拟：3月对账单（period 早于目标期）
        record_mar = HoldingRecord(
            asset=asset_a,
            period=ReportPeriod(
                start_date=__import__('datetime').date(2026, 3, 1),
                end_date=__import__('datetime').date(2026, 3, 31),
            ),
            opening_value=Decimal("8000"),
            closing_value=Decimal("9000"),  # 3月期末
        )
        # 模拟：4月对账单（opening=0，因为解析器无期初字段）
        period_apr = ReportPeriod(
            start_date=__import__('datetime').date(2026, 4, 1),
            end_date=__import__('datetime').date(2026, 4, 30),
        )
        record_apr = HoldingRecord(
            asset=asset_a,
            period=period_apr,
            opening_value=Decimal("0"),
            closing_value=Decimal("10500"),
            inflow=Decimal("1000"),
        )
        # generate() 传入全量（含3月），目标期为4月
        report = generator.generate([record_mar, record_apr], period_apr)
        assert len(report.holdings) == 1
        h = report.holdings[0]
        # 期初应由3月期末推算得到
        assert h.opening_value == Decimal("9000")
        assert h.closing_value == Decimal("10500")
        assert h.inflow == Decimal("1000")

    def test_no_prior_data_opening_stays_zero(self, generator, asset_a):
        """没有前置期数据时，opening_value 保持为 0。"""
        from datetime import date
        period_apr = ReportPeriod(date(2026, 4, 1), date(2026, 4, 30))
        record_apr = HoldingRecord(
            asset=asset_a,
            period=period_apr,
            opening_value=Decimal("0"),
            closing_value=Decimal("10500"),
        )
        report = generator.generate([record_apr], period_apr)
        assert report.holdings[0].opening_value == Decimal("0")

    def test_existing_opening_not_overridden(self, generator, asset_a):
        """若原始 opening_value != 0，不应被覆盖（富国等已有期初值的解析器）。"""
        from datetime import date
        period_mar = ReportPeriod(date(2026, 3, 1), date(2026, 3, 31))
        period_apr = ReportPeriod(date(2026, 4, 1), date(2026, 4, 30))
        record_mar = HoldingRecord(
            asset=asset_a,
            period=period_mar,
            opening_value=Decimal("7000"),
            closing_value=Decimal("9999"),  # 应被忽略（apr 有自己的 opening）
        )
        record_apr = HoldingRecord(
            asset=asset_a,
            period=period_apr,
            opening_value=Decimal("8500"),  # 已有期初，不应被替换
            closing_value=Decimal("10000"),
        )
        report = generator.generate([record_mar, record_apr], period_apr)
        assert report.holdings[0].opening_value == Decimal("8500")

    def test_cross_month_inflow_cumulated(self, generator, asset_a):
        """3月+4月两条记录（均在目标期4月内 overlaps），inflow 应累加，
        但 opening 应来自3月期末推算（当3月不在目标期内时）。"""
        from datetime import date
        # 3月记录不 overlaps 4月目标期，但作为前置期存在于 all_holdings
        period_mar = ReportPeriod(date(2026, 3, 1), date(2026, 3, 31))
        period_apr = ReportPeriod(date(2026, 4, 1), date(2026, 4, 30))
        record_mar = HoldingRecord(
            asset=asset_a,
            period=period_mar,
            opening_value=Decimal("5000"),
            closing_value=Decimal("6000"),
            inflow=Decimal("500"),
        )
        record_apr = HoldingRecord(
            asset=asset_a,
            period=period_apr,
            opening_value=Decimal("0"),
            closing_value=Decimal("7500"),
            inflow=Decimal("1000"),
        )
        report = generator.generate([record_mar, record_apr], period_apr)
        h = report.holdings[0]
        assert h.opening_value == Decimal("6000")  # 来自3月 closing
        assert h.closing_value == Decimal("7500")  # 4月 closing
        assert h.inflow == Decimal("1000")          # 只有4月 inflow（3月不在目标期）

    def test_chain_fill_within_target_period(self, generator, asset_a):
        """4月+5月两条记录均在目标期内，5月 opening=0 时应由4月 closing 链式填充。"""
        from datetime import date
        period_apr = ReportPeriod(date(2026, 4, 1), date(2026, 4, 30))
        period_may = ReportPeriod(date(2026, 5, 1), date(2026, 5, 31))
        target = ReportPeriod(date(2026, 4, 1), date(2026, 5, 31))
        record_apr = HoldingRecord(
            asset=asset_a,
            period=period_apr,
            opening_value=Decimal("0"),
            closing_value=Decimal("10000"),
            inflow=Decimal("500"),
        )
        record_may = HoldingRecord(
            asset=asset_a,
            period=period_may,
            opening_value=Decimal("0"),
            closing_value=Decimal("11000"),
            inflow=Decimal("200"),
        )
        report = generator.generate([record_apr, record_may], target)
        h = report.holdings[0]
        # 4月 opening 无前置数据，保持0；5月 opening 由4月 closing 链式填充
        # 合并后取最早 opening（4月=0）和最晚 closing（5月=11000）
        assert h.opening_value == Decimal("0")       # 4月无前置数据
        assert h.closing_value == Decimal("11000")   # 5月 closing
        assert h.inflow == Decimal("700")             # 累加


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
