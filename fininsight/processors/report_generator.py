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
        # 1. 保留与目标周期有交集的记录（月度/年度账单均可纳入）
        period_holdings = [h for h in holdings if h.period.overlaps(period)]
        logger.debug(
            "周期 %s 共匹配 %d / %d 条持仓记录",
            period,
            len(period_holdings),
            len(holdings),
        )

        # 2. 合并同一标的跨不同时间周期的记录
        consolidated = self._consolidate(period_holdings, period)

        # 3. 计算收益贡献率
        report = Report(period=period, holdings=consolidated)
        self._fill_contribution_rates(report)

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _consolidate(
        self, holdings: List[HoldingRecord], report_period: ReportPeriod
    ) -> List[HoldingRecord]:
        """合并同一标的跨不同时间周期的多条记录。

        合并规则：相同 (asset.name, asset.code) 的记录，
        按原始账单的时间先后排列，取最早记录的 opening_value
        和最晚记录的 closing_value，inflow / outflow 累加。
        合并后 period 统一设为报告周期。
        """
        bucket: Dict[Tuple, List[HoldingRecord]] = {}

        for h in holdings:
            key = (h.asset.name, h.asset.code)
            bucket.setdefault(key, []).append(h)

        result: List[HoldingRecord] = []
        for records in bucket.values():
            # 按账单起始日期排序
            records.sort(key=lambda r: r.period.start_date)
            result.append(HoldingRecord(
                asset=records[0].asset,
                period=report_period,
                opening_value=records[0].opening_value,
                closing_value=records[-1].closing_value,
                inflow=sum((r.inflow for r in records), Decimal("0")),
                outflow=sum((r.outflow for r in records), Decimal("0")),
            ))

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
