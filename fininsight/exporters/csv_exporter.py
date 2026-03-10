"""CSV 格式报告导出器。

输出格式：
- 第 1 行：报告期间说明
- 第 2 行：空行
- 第 3 行：列标题
- 第 4~N 行：持仓明细（按市场 → 类别 → 名称排序）
- 最后一行：汇总合计行
"""

from __future__ import annotations

import csv
import os
from decimal import Decimal
from typing import List

from fininsight.models.records import HoldingRecord, Report

from .base import ReportExporter

# 报告列标题（中文）
_HEADERS = [
    "投资标的名称",
    "代码",
    "市场",
    "类别",
    "期初市值(元)",
    "期末市值(元)",
    "入金(元)",
    "出金(元)",
    "收益(元)",
    "收益率(%)",
    "收益贡献率(%)",
]


class CSVExporter(ReportExporter):
    """将投资报告导出为 CSV 文件。

    参数:
        encoding: 文件编码，默认 ``utf-8-sig``（带 BOM，Excel 可直接打开）
    """

    def __init__(self, encoding: str = "utf-8-sig") -> None:
        self._encoding = encoding

    def export(self, report: Report, output_path: str) -> str:
        """导出报告到 CSV 文件。

        Args:
            report:      投资报告对象
            output_path: 目标目录或文件路径

        Returns:
            实际写入的文件路径
        """
        file_path = self._resolve_path(report, output_path)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        with open(file_path, "w", newline="", encoding=self._encoding) as f:
            writer = csv.writer(f)

            # 报告元信息
            writer.writerow([f"报告期间: {report.period}"])
            writer.writerow([])

            # 列标题
            writer.writerow(_HEADERS)

            # 持仓明细（按市场 → 类别 → 名称排序，便于阅读）
            sorted_holdings = sorted(
                report.holdings,
                key=lambda h: (
                    h.asset.market.value,
                    h.asset.asset_type.value,
                    h.asset.name,
                ),
            )
            for holding in sorted_holdings:
                writer.writerow(_format_holding_row(holding))

            # 汇总行
            writer.writerow([])
            writer.writerow(_format_summary_row(report))

        return file_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(report: Report, output_path: str) -> str:
        """若 output_path 是目录，自动生成文件名；否则直接使用。"""
        if os.path.isdir(output_path):
            filename = (
                f"report_{report.period.start_date}_{report.period.end_date}.csv"
            )
            return os.path.join(output_path, filename)
        return output_path


# ---------------------------------------------------------------------------
# Module-level formatting helpers
# ---------------------------------------------------------------------------

def _fmt_decimal(value: Decimal) -> str:
    """保留两位小数的数值字符串。"""
    return f"{value:.2f}"


def _fmt_pct(value: Decimal) -> str:
    """将小数形式的比率转换为百分比字符串，如 0.05 → '5.00%'。"""
    return f"{value * 100:.2f}%"


def _format_holding_row(h: HoldingRecord) -> List[str]:
    """将持仓记录格式化为 CSV 行。"""
    contribution = h.contribution_rate if h.contribution_rate is not None else Decimal("0")
    return [
        h.asset.name,
        h.asset.code or "",
        h.asset.market.value,
        h.asset.asset_type.value,
        _fmt_decimal(h.opening_value),
        _fmt_decimal(h.closing_value),
        _fmt_decimal(h.inflow),
        _fmt_decimal(h.outflow),
        _fmt_decimal(h.profit),
        _fmt_pct(h.profit_rate),
        _fmt_pct(contribution),
    ]


def _format_summary_row(report: Report) -> List[str]:
    """将报告汇总格式化为 CSV 末尾合计行。"""
    return [
        "合计",
        "",
        "",
        "",
        _fmt_decimal(report.total_opening_value),
        _fmt_decimal(report.total_closing_value),
        _fmt_decimal(report.total_inflow),
        _fmt_decimal(report.total_outflow),
        _fmt_decimal(report.total_profit),
        _fmt_pct(report.total_profit_rate),
        "100.00%",
    ]
