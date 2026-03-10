#!/usr/bin/env python3
"""FinInsight Demo - 使用模拟数据演示完整报告生成流水线。

无需邮箱或任何配置，直接运行即可生成示例报告：

    python demo.py

报告将输出到 ./output/demo/ 目录。
"""

from decimal import Decimal

from fininsight.exporters.csv_exporter import CSVExporter
from fininsight.models.enums import AssetType, Market
from fininsight.models.records import Asset, HoldingRecord, ReportPeriod
from fininsight.processors.report_generator import ReportGenerator

# ---------------------------------------------------------------------------
# 模拟 2024 年第 4 季度持仓数据
# ---------------------------------------------------------------------------

PERIOD = ReportPeriod.from_year_quarter(2024, 4)

MOCK_HOLDINGS = [
    # A 股 - 股票
    HoldingRecord(
        asset=Asset("贵州茅台", AssetType.STOCK, Market.A_SHARE, "600519"),
        period=PERIOD,
        opening_value=Decimal("85000.00"),
        closing_value=Decimal("92000.00"),
        inflow=Decimal("0"),
        outflow=Decimal("0"),
    ),
    # 境内 - 基金（沪深300指数基金）
    HoldingRecord(
        asset=Asset("华夏沪深300ETF", AssetType.FUND, Market.DOMESTIC, "510330"),
        period=PERIOD,
        opening_value=Decimal("50000.00"),
        closing_value=Decimal("53500.00"),
        inflow=Decimal("5000.00"),
        outflow=Decimal("0"),
    ),
    # 境内 - 基金（主动混合型）
    HoldingRecord(
        asset=Asset("易方达蓝筹精选混合", AssetType.FUND, Market.DOMESTIC, "005827"),
        period=PERIOD,
        opening_value=Decimal("30000.00"),
        closing_value=Decimal("28500.00"),
        inflow=Decimal("0"),
        outflow=Decimal("3000.00"),
    ),
    # 港股 - 股票
    HoldingRecord(
        asset=Asset("腾讯控股", AssetType.STOCK, Market.HK_STOCK, "00700"),
        period=PERIOD,
        opening_value=Decimal("40000.00"),
        closing_value=Decimal("44800.00"),
        inflow=Decimal("0"),
        outflow=Decimal("0"),
    ),
    # 美股 - 股票
    HoldingRecord(
        asset=Asset("苹果公司", AssetType.STOCK, Market.US_STOCK, "AAPL"),
        period=PERIOD,
        opening_value=Decimal("35000.00"),
        closing_value=Decimal("38000.00"),
        inflow=Decimal("8000.00"),
        outflow=Decimal("0"),
    ),
    # 境内 - 黄金
    HoldingRecord(
        asset=Asset("黄金积累计划", AssetType.GOLD, Market.DOMESTIC),
        period=PERIOD,
        opening_value=Decimal("20000.00"),
        closing_value=Decimal("22000.00"),
        inflow=Decimal("1000.00"),
        outflow=Decimal("0"),
    ),
    # 境内 - 大额存单
    HoldingRecord(
        asset=Asset("招商银行大额存单36M", AssetType.CD, Market.DOMESTIC),
        period=PERIOD,
        opening_value=Decimal("100000.00"),
        closing_value=Decimal("101500.00"),
        inflow=Decimal("0"),
        outflow=Decimal("0"),
    ),
]


def main() -> None:
    print("=" * 60)
    print("FinInsight Demo - 2024 年第 4 季度投资报告")
    print("=" * 60)

    # 生成报告
    generator = ReportGenerator()
    report = generator.generate(MOCK_HOLDINGS, PERIOD)

    # 打印摘要
    print(f"\n报告期间  : {report.period}")
    print(f"持仓标的数: {len(report.holdings)}")
    print(f"期初总市值: ¥{report.total_opening_value:,.2f}")
    print(f"期末总市值: ¥{report.total_closing_value:,.2f}")
    print(f"总入金    : ¥{report.total_inflow:,.2f}")
    print(f"总出金    : ¥{report.total_outflow:,.2f}")
    print(f"总收益    : ¥{report.total_profit:,.2f}")
    print(f"总收益率  : {float(report.total_profit_rate) * 100:.2f}%")

    print("\n各标的明细：")
    print(f"{'标的名称':<20} {'市场':<6} {'收益(元)':>12} {'收益率':>8} {'贡献率':>8}")
    print("-" * 60)
    for h in sorted(report.holdings, key=lambda x: x.asset.market.value):
        name = str(h.asset)[:20]
        profit_rate_pct = float(h.profit_rate) * 100
        contrib_pct = float(h.contribution_rate or 0) * 100
        print(
            f"{name:<20} {h.asset.market.value:<6} "
            f"{float(h.profit):>12,.2f} "
            f"{profit_rate_pct:>7.2f}% "
            f"{contrib_pct:>7.2f}%"
        )

    # 导出 CSV
    import os
    output_dir = "./output/demo"
    os.makedirs(output_dir, exist_ok=True)
    exporter = CSVExporter()
    output_path = exporter.export(report, output_dir)
    print(f"\n✓ CSV 报告已生成: {output_path}")
    print("  用 Excel 或任意电子表格软件打开查看完整报告。")


if __name__ == "__main__":
    main()
