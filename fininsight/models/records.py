"""Core data structures shared across all pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from .enums import AssetType, Market


@dataclass(frozen=True)
class Asset:
    """表示一个投资标的（基金、股票、黄金等）。

    使用 frozen=True 保证对象不可变，可作为 dict key 使用。
    """

    name: str
    asset_type: AssetType
    market: Market
    code: Optional[str] = None

    def __str__(self) -> str:
        if self.code:
            return f"{self.name}({self.code})"
        return self.name


@dataclass(frozen=True)
class ReportPeriod:
    """报告时间周期（不可变），包含开始和结束日期。

    使用 frozen=True 保证对象不可变，可作为 dict key 使用。
    """

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.start_date >= self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) 必须早于 end_date ({self.end_date})"
            )

    @classmethod
    def from_year_quarter(cls, year: int, quarter: int) -> ReportPeriod:
        """按年份和季度创建周期。

        Args:
            year: 年份，如 2024
            quarter: 季度，1~4

        Returns:
            对应季度的 ReportPeriod
        """
        if quarter not in (1, 2, 3, 4):
            raise ValueError(f"quarter 必须为 1~4，得到: {quarter}")
        quarter_months = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
        start_month, end_month = quarter_months[quarter]
        start = date(year, start_month, 1)
        # 计算季度末最后一天
        if end_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        return cls(start, end)

    @classmethod
    def from_year(cls, year: int) -> ReportPeriod:
        """按年份创建全年周期。"""
        return cls(date(year, 1, 1), date(year, 12, 31))

    def __str__(self) -> str:
        return (
            f"{self.start_date.strftime('%Y-%m-%d')} ~ "
            f"{self.end_date.strftime('%Y-%m-%d')}"
        )


@dataclass
class HoldingRecord:
    """单一投资标的在某个周期内的持仓记录。

    这是整个数据流水线中的核心数据结构，由解析器产生，
    经处理器丰富（填充 contribution_rate），最终由导出器输出。

    收益计算采用简单 Dietz 法：
        profit = closing_value - opening_value - inflow + outflow
        profit_rate = profit / (opening_value + net_inflow)
    """

    asset: Asset
    period: ReportPeriod
    opening_value: Decimal           # 期初市值（元）
    closing_value: Decimal           # 期末市值（元）
    inflow: Decimal = field(default_factory=lambda: Decimal("0"))   # 期内入金（元）
    outflow: Decimal = field(default_factory=lambda: Decimal("0"))  # 期内出金（元）
    contribution_rate: Optional[Decimal] = field(default=None)      # 收益贡献率，由 ReportGenerator 填充

    @property
    def profit(self) -> Decimal:
        """期内收益（元）= 期末市值 - 期初市值 - 净投入。"""
        return self.closing_value - self.opening_value - self.inflow + self.outflow

    @property
    def profit_rate(self) -> Decimal:
        """期内收益率（小数形式，如 0.05 表示 5%）。

        分母 = 期初市值 + 净投入（入金 - 出金），若为零则返回 0。
        """
        net_inflow = self.inflow - self.outflow
        denominator = self.opening_value + net_inflow
        if denominator == Decimal("0"):
            return Decimal("0")
        return self.profit / denominator


@dataclass
class Report:
    """完整的投资报告，包含所有持仓记录及汇总统计。"""

    period: ReportPeriod
    holdings: List[HoldingRecord]

    @property
    def total_profit(self) -> Decimal:
        """所有标的的总收益（元）。"""
        return sum((h.profit for h in self.holdings), Decimal("0"))

    @property
    def total_opening_value(self) -> Decimal:
        """所有标的的期初市值合计（元）。"""
        return sum((h.opening_value for h in self.holdings), Decimal("0"))

    @property
    def total_closing_value(self) -> Decimal:
        """所有标的的期末市值合计（元）。"""
        return sum((h.closing_value for h in self.holdings), Decimal("0"))

    @property
    def total_inflow(self) -> Decimal:
        """所有标的的入金合计（元）。"""
        return sum((h.inflow for h in self.holdings), Decimal("0"))

    @property
    def total_outflow(self) -> Decimal:
        """所有标的的出金合计（元）。"""
        return sum((h.outflow for h in self.holdings), Decimal("0"))

    @property
    def total_profit_rate(self) -> Decimal:
        """整体收益率（小数形式）。"""
        net_inflow = self.total_inflow - self.total_outflow
        denominator = self.total_opening_value + net_inflow
        if denominator == Decimal("0"):
            return Decimal("0")
        return self.total_profit / denominator
