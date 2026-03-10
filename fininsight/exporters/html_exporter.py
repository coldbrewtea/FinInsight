"""HTML 格式报告导出器。

输出一个自包含的单文件 HTML，无外部依赖（纯内联 CSS），可直接在浏览器中打开。

页面结构：
- 顶部标题栏：报告期间
- 摘要卡片：期末总市值 / 期初总市值 / 期内总收益 / 整体收益率
- 持仓明细表：按市场 → 类别 → 名称排序，收益正负用颜色区分，
              收益贡献率以内嵌进度条形式展示
- 页脚：生成时间
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from decimal import Decimal
from typing import List

from fininsight.models.records import HoldingRecord, Report

from .base import ReportExporter

# ---------------------------------------------------------------------------
# CSS 样式（内联，无外部依赖）
# ---------------------------------------------------------------------------
_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f4f8;color:#2d3748;font-size:14px}
a{color:inherit;text-decoration:none}

/* ---- 顶部标题 ---- */
.page-header{background:#1a365d;color:#fff;padding:24px 32px}
.page-header h1{font-size:20px;font-weight:600;letter-spacing:.5px}
.page-header .subtitle{margin-top:6px;font-size:13px;opacity:.75}

/* ---- 摘要卡片 ---- */
.summary{display:flex;flex-wrap:wrap;gap:16px;padding:24px 32px}
.card{flex:1;min-width:180px;background:#fff;border-radius:8px;
      padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card .label{font-size:12px;color:#718096;margin-bottom:6px}
.card .value{font-size:22px;font-weight:700;letter-spacing:-.5px}
.card.profit-pos .value{color:#276749}
.card.profit-neg .value{color:#c53030}
.card.profit-neu .value{color:#4a5568}

/* ---- 持仓表格 ---- */
.section{padding:0 32px 32px}
.section h2{font-size:15px;font-weight:600;color:#2d3748;margin-bottom:12px}
.table-wrap{overflow-x:auto;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
table{width:100%;border-collapse:collapse;background:#fff}
thead tr{background:#2c5282;color:#fff}
thead th{padding:10px 12px;text-align:right;font-weight:500;font-size:12px;white-space:nowrap}
thead th:first-child,thead th:nth-child(2),
thead th:nth-child(3),thead th:nth-child(4){text-align:left}
tbody tr:nth-child(even){background:#f7fafc}
tbody tr:hover{background:#ebf8ff}
tbody td{padding:9px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;
         text-align:right;white-space:nowrap}
tbody td:first-child,tbody td:nth-child(2),
tbody td:nth-child(3),tbody td:nth-child(4){text-align:left}
tfoot tr{background:#edf2f7;font-weight:600}
tfoot td{padding:10px 12px;text-align:right;font-size:13px;border-top:2px solid #cbd5e0}
tfoot td:first-child{text-align:left}

/* ---- 数值颜色 ---- */
.pos{color:#276749}
.neg{color:#c53030}
.neu{color:#718096}

/* ---- 贡献率进度条 ---- */
.bar-cell{min-width:110px}
.bar-wrap{display:flex;align-items:center;gap:6px}
.bar-bg{flex:1;height:8px;background:#e2e8f0;border-radius:4px;overflow:hidden}
.bar-fill{height:100%;background:#4299e1;border-radius:4px}
.bar-label{font-size:12px;color:#4a5568;min-width:42px;text-align:right}

/* ---- 类型标签 ---- */
.tag{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:500}
.tag-基金{background:#ebf8ff;color:#2b6cb0}
.tag-股票{background:#fff5f5;color:#c53030}
.tag-债券{background:#f0fff4;color:#276749}
.tag-黄金{background:#fffff0;color:#975a16}
.tag-大额存单{background:#faf5ff;color:#6b46c1}
.tag-现金{background:#f0fff4;color:#276749}
.tag-其他{background:#f7fafc;color:#718096}

/* ---- 页脚 ---- */
.page-footer{padding:16px 32px;text-align:right;font-size:11px;color:#a0aec0}
"""


class HTMLExporter(ReportExporter):
    """将投资报告导出为自包含 HTML 文件。

    参数:
        encoding: 文件编码，默认 ``utf-8``
        title:    页面 <title> 前缀，默认 ``"FinInsight 投资报告"``
    """

    def __init__(
        self,
        encoding: str = "utf-8",
        title: str = "FinInsight 投资报告",
    ) -> None:
        self._encoding = encoding
        self._title = title

    def export(self, report: Report, output_path: str) -> str:
        """导出报告到 HTML 文件。

        Args:
            report:      投资报告对象
            output_path: 目标目录或文件路径

        Returns:
            实际写入的文件路径
        """
        file_path = self._resolve_path(report, output_path)
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

        content = self._render(report)
        with open(file_path, "w", encoding=self._encoding) as f:
            f.write(content)

        return file_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(report: Report, output_path: str) -> str:
        """若 output_path 是目录，自动生成文件名；否则直接使用。"""
        if os.path.isdir(output_path):
            filename = (
                f"report_{report.period.start_date}_{report.period.end_date}.html"
            )
            return os.path.join(output_path, filename)
        return output_path

    def _render(self, report: Report) -> str:
        """渲染完整的 HTML 字符串。"""
        period_str = str(report.period)
        page_title = f"{self._title} — {period_str}"

        summary_html = self._render_summary(report)
        table_html = self._render_table(report)

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        return (
            f'<!DOCTYPE html>\n'
            f'<html lang="zh-CN">\n'
            f'<head>\n'
            f'<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{_esc(page_title)}</title>\n'
            f'<style>{_CSS}</style>\n'
            f'</head>\n'
            f'<body>\n'
            f'<header class="page-header">\n'
            f'  <h1>投资持仓报告</h1>\n'
            f'  <p class="subtitle">统计期间：{_esc(period_str)}</p>\n'
            f'</header>\n'
            f'{summary_html}\n'
            f'<section class="section">\n'
            f'  <h2>持仓明细</h2>\n'
            f'  {table_html}\n'
            f'</section>\n'
            f'<footer class="page-footer">由 FinInsight 生成 · {_esc(generated_at)}</footer>\n'
            f'</body>\n'
            f'</html>\n'
        )

    @staticmethod
    def _render_summary(report: Report) -> str:
        """渲染顶部四格摘要卡片。"""
        closing = report.total_closing_value
        opening = report.total_opening_value
        profit = report.total_profit
        rate = report.total_profit_rate

        profit_class = _profit_class(profit)

        cards = [
            ("期末总市值（元）", f"¥{closing:,.2f}", "profit-neu"),
            ("期初总市值（元）", f"¥{opening:,.2f}", "profit-neu"),
            ("期内总收益（元）", f"{'+' if profit > 0 else ''}{profit:,.2f}", profit_class),
            ("整体收益率", _fmt_pct(rate), profit_class),
        ]

        items = "\n".join(
            f'  <div class="card {cls}">'
            f'<div class="label">{_esc(label)}</div>'
            f'<div class="value">{_esc(value)}</div>'
            f'</div>'
            for label, value, cls in cards
        )
        return f'<div class="summary">\n{items}\n</div>'

    @staticmethod
    def _render_table(report: Report) -> str:
        """渲染持仓明细表格（含表头、数据行、合计行）。"""
        headers = [
            "投资标的名称", "代码", "市场", "类别",
            "期初市值(元)", "期末市值(元)", "入金(元)", "出金(元)",
            "收益(元)", "收益率", "收益贡献率",
        ]
        th_cells = "\n".join(f"      <th>{_esc(h)}</th>" for h in headers)

        sorted_holdings = sorted(
            report.holdings,
            key=lambda h: (
                h.asset.market.value,
                h.asset.asset_type.value,
                h.asset.name,
            ),
        )

        rows_html = "\n".join(
            _render_holding_row(h) for h in sorted_holdings
        )
        summary_html = _render_summary_row(report)

        return (
            f'<div class="table-wrap">\n'
            f'<table>\n'
            f'  <thead><tr>\n{th_cells}\n  </tr></thead>\n'
            f'  <tbody>\n{rows_html}\n  </tbody>\n'
            f'  <tfoot>\n{summary_html}\n  </tfoot>\n'
            f'</table>\n'
            f'</div>'
        )


# ---------------------------------------------------------------------------
# Module-level rendering helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """HTML 转义。"""
    return html.escape(str(text))


def _fmt_decimal(value: Decimal) -> str:
    return f"{value:,.2f}"


def _fmt_pct(value: Decimal) -> str:
    return f"{value * 100:.2f}%"


def _profit_class(value: Decimal) -> str:
    if value > 0:
        return "profit-pos"
    if value < 0:
        return "profit-neg"
    return "profit-neu"


def _value_class(value: Decimal) -> str:
    """返回正/负/零对应的 CSS class（用于表格单元格内联着色）。"""
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return "neu"


def _render_holding_row(h: HoldingRecord) -> str:
    """将单条持仓记录渲染为一个 <tr> 行。"""
    contribution = h.contribution_rate if h.contribution_rate is not None else Decimal("0")
    # 贡献率进度条：最大 100%，clip 在 100 以内
    bar_pct = min(float(contribution * 100), 100)

    asset_type = h.asset.asset_type.value
    tag_class = f"tag tag-{asset_type}"

    profit_cls = _value_class(h.profit)

    cells: List[str] = [
        f'<td>{_esc(h.asset.name)}</td>',
        f'<td>{_esc(h.asset.code or "—")}</td>',
        f'<td>{_esc(h.asset.market.value)}</td>',
        f'<td><span class="{tag_class}">{_esc(asset_type)}</span></td>',
        f'<td>{_esc(_fmt_decimal(h.opening_value))}</td>',
        f'<td>{_esc(_fmt_decimal(h.closing_value))}</td>',
        f'<td>{_esc(_fmt_decimal(h.inflow))}</td>',
        f'<td>{_esc(_fmt_decimal(h.outflow))}</td>',
        f'<td class="{profit_cls}">{_esc(_fmt_decimal(h.profit))}</td>',
        f'<td class="{profit_cls}">{_esc(_fmt_pct(h.profit_rate))}</td>',
        (
            f'<td class="bar-cell">'
            f'<div class="bar-wrap">'
            f'<div class="bar-bg"><div class="bar-fill" style="width:{bar_pct:.1f}%"></div></div>'
            f'<span class="bar-label">{_esc(_fmt_pct(contribution))}</span>'
            f'</div></td>'
        ),
    ]
    return "    <tr>\n      " + "\n      ".join(cells) + "\n    </tr>"


def _render_summary_row(report: Report) -> str:
    """渲染 <tfoot> 合计行。"""
    profit = report.total_profit
    profit_cls = _value_class(profit)

    cells: List[str] = [
        "<td>合计</td>",
        "<td></td>",
        "<td></td>",
        "<td></td>",
        f"<td>{_esc(_fmt_decimal(report.total_opening_value))}</td>",
        f"<td>{_esc(_fmt_decimal(report.total_closing_value))}</td>",
        f"<td>{_esc(_fmt_decimal(report.total_inflow))}</td>",
        f"<td>{_esc(_fmt_decimal(report.total_outflow))}</td>",
        f'<td class="{profit_cls}">{_esc(_fmt_decimal(profit))}</td>',
        f'<td class="{profit_cls}">{_esc(_fmt_pct(report.total_profit_rate))}</td>',
        "<td>100.00%</td>",
    ]
    return "    <tr>\n      " + "\n      ".join(cells) + "\n    </tr>"
