"""报告生成器。

职责：
1. 过滤并保留与指定周期匹配的持仓记录
2. 合并来自多个数据源/邮件的同一标的重复记录
3. 推算缺失的期初市值：若最早一条记录 opening_value == 0，
   则用「目标期之前最近一期」相同标的的 closing_value 作为期初市值
4. 计算每个持仓标的的收益贡献率（contribution_rate）
5. 封装为 Report 对象返回
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

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
            holdings: 由解析器产出的持仓记录列表（可能来自多个数据源）。
                      建议包含比报告期稍宽的时间范围内的邮件，以便推算期初市值。
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

        # 2. 合并同一标的跨不同时间周期的记录，并推算缺失期初市值
        consolidated = self._consolidate(period_holdings, period, all_holdings=holdings)

        # 3. 计算收益贡献率
        report = Report(period=period, holdings=consolidated)
        self._fill_contribution_rates(report)

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _consolidate(
        self,
        holdings: List[HoldingRecord],
        report_period: ReportPeriod,
        all_holdings: Optional[List[HoldingRecord]] = None,
    ) -> List[HoldingRecord]:
        """合并同一标的跨不同时间周期的多条记录，并推算缺失的期初市值。

        合并规则：相同 (asset.name, asset.code) 的记录，
        按原始账单的时间先后排列，取最早记录的 opening_value
        和最晚记录的 closing_value，inflow / outflow 累加。
        合并后 period 统一设为报告周期。

        期初市值推算：若合并后最早记录的 opening_value == 0，
        则在 all_holdings 中查找同标的、period 早于目标期的最近一条记录，
        用其 closing_value 作为期初市值。
        """
        bucket: Dict[Tuple, List[HoldingRecord]] = {}

        for h in holdings:
            key = (h.asset.name, h.asset.code)
            bucket.setdefault(key, []).append(h)

        result: List[HoldingRecord] = []
        for key, records in bucket.items():
            # 按账单起始日期排序
            records.sort(key=lambda r: r.period.start_date)

            # 链式填充：对相邻两条记录，若后一条 opening=0 且前一条有 closing，
            # 则用前一条 closing 填充后一条 opening（适用于易方达等无期初字段的月度账单）
            for i in range(1, len(records)):
                if records[i].opening_value == Decimal("0") and records[i - 1].closing_value != Decimal("0"):
                    records[i] = HoldingRecord(
                        asset=records[i].asset,
                        period=records[i].period,
                        opening_value=records[i - 1].closing_value,
                        closing_value=records[i].closing_value,
                        inflow=records[i].inflow,
                        outflow=records[i].outflow,
                    )
                    logger.debug(
                        "链式推算期初: %s [%s] opening=%s（来自前月 closing）",
                        key,
                        records[i].period,
                        records[i].opening_value,
                    )

            opening = self._resolve_opening_value(
                key=key,
                earliest_record=records[0],
                all_holdings=all_holdings or [],
                target_period=report_period,
            )
            result.append(HoldingRecord(
                asset=records[0].asset,
                period=report_period,
                opening_value=opening,
                closing_value=records[-1].closing_value,
                inflow=sum((r.inflow for r in records), Decimal("0")),
                outflow=sum((r.outflow for r in records), Decimal("0")),
            ))

        if len(result) < len(holdings):
            logger.info("合并后持仓数: %d（合并前: %d）", len(result), len(holdings))
        return result

    @staticmethod
    def _resolve_opening_value(
        key: Tuple,
        earliest_record: HoldingRecord,
        all_holdings: List[HoldingRecord],
        target_period: ReportPeriod,
    ) -> Decimal:
        """推算期初市值。

        若 earliest_record.opening_value != 0，直接使用原值。
        否则，在 all_holdings 中查找同标的且 period 结束于目标期开始之前的
        最近一条记录，用其 closing_value 作为期初市值。

        适用场景：易方达等月度对账单只有期末市值，没有期初列；
        当同时存在上月和本月对账单时，上月期末 = 本月期初。
        """
        if earliest_record.opening_value != Decimal("0"):
            return earliest_record.opening_value

        # 找同标的、period 结束在目标期开始之前的所有记录
        prior = [
            h for h in all_holdings
            if (h.asset.name, h.asset.code) == key
            and h.period.end_date < target_period.start_date
        ]
        if not prior:
            return Decimal("0")

        # 取 period.end_date 最近的一条
        prior.sort(key=lambda r: r.period.end_date)
        resolved = prior[-1].closing_value
        logger.debug(
            "推算期初市值: %s = %s（来自前置期 %s）",
            key,
            resolved,
            prior[-1].period,
        )
        return resolved

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
