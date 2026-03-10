"""报告生成器。

职责：
1. 过滤并保留与指定周期匹配的持仓记录
2. 合并来自多个数据源/邮件的同一标的重复记录
3. 计算每个持仓标的的收益贡献率（contribution_rate）
4. 封装为 Report 对象返回
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List, Tuple

from fininsight.models.records import HoldingRecord, Report, ReportPeriod

logger = logging.getLogger(__name__)


class ReportGenerator:
    """从持仓记录列表生成完整的投资报告。

    用法::

        generator = ReportGenerator()
        report = generator.generate(holdings, period)
    """

    def generate(
        self, holdings: List[HoldingRecord], period: ReportPeriod
    ) -> Report:
        """生成指定周期的投资报告。

        Args:
            holdings: 由解析器产出的持仓记录列表（可能来自多个数据源）
            period:   报告时间周期

        Returns:
            Report 对象，每条 HoldingRecord.contribution_rate 已填充。
        """
        # 1. 仅保留与目标周期匹配的记录
        period_holdings = [h for h in holdings if h.period == period]
        logger.debug(
            "周期 %s 共匹配 %d / %d 条持仓记录",
            period,
            len(period_holdings),
            len(holdings),
        )

        # 2. 合并同一标的的重复记录
        consolidated = self._consolidate(period_holdings)

        # 3. 计算收益贡献率
        report = Report(period=period, holdings=consolidated)
        self._fill_contribution_rates(report)

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _consolidate(self, holdings: List[HoldingRecord]) -> List[HoldingRecord]:
        """合并同一标的的多条记录（如来自多封邮件/多个数据源）。

        合并规则：相同 (asset.name, asset.code, period) 的记录，
        将 opening_value、closing_value、inflow、outflow 分别累加。
        """
        bucket: Dict[Tuple, HoldingRecord] = {}

        for h in holdings:
            key = (h.asset.name, h.asset.code, h.period)
            if key not in bucket:
                bucket[key] = h
            else:
                existing = bucket[key]
                bucket[key] = HoldingRecord(
                    asset=existing.asset,
                    period=existing.period,
                    opening_value=existing.opening_value + h.opening_value,
                    closing_value=existing.closing_value + h.closing_value,
                    inflow=existing.inflow + h.inflow,
                    outflow=existing.outflow + h.outflow,
                )

        result = list(bucket.values())
        if len(result) < len(holdings):
            logger.info("合并后持仓数: %d（合并前: %d）", len(result), len(holdings))
        return result

    @staticmethod
    def _fill_contribution_rates(report: Report) -> None:
        """计算并填充每条持仓记录的 contribution_rate。

        contribution_rate = 本标的收益 / 全部标的总收益

        若总收益为 0（无盈亏或盈亏相抵），则所有标的贡献率均设为 0。
        """
        total = report.total_profit
        for h in report.holdings:
            if total == Decimal("0"):
                h.contribution_rate = Decimal("0")
            else:
                h.contribution_rate = h.profit / total
