#!/usr/bin/env python3
"""FinInsight - 家庭投资报表生成工具

从邮箱中提取投资对账单，生成指定周期内的持仓分析报告（CSV 格式）。

用法示例：
    # 生成 2024 年第 1 季度报告
    python main.py --quarter 2024 1

    # 生成 2024 年全年报告
    python main.py --year 2024

    # 生成自定义日期区间报告
    python main.py --range 2024-01-01 2024-06-30

    # 指定配置文件和输出目录
    python main.py --quarter 2024 4 --config config/config.yaml --output ./reports
"""

import argparse
import logging
import sys
from datetime import date

from fininsight.config_loader import load_config
from fininsight.exporters.csv_exporter import CSVExporter
from fininsight.exporters.html_exporter import HTMLExporter
from fininsight.models.records import ReportPeriod
from fininsight.parsers.fund_email_parser import FundEmailParser
from fininsight.parsers.fullgoal_email_parser import FullgoalEmailParser
from fininsight.processors.report_generator import ReportGenerator
from fininsight.sources.email_source import EmailSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fininsight",
        description="FinInsight - 家庭投资报表生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    period_group = parser.add_mutually_exclusive_group(required=True)
    period_group.add_argument(
        "--quarter",
        nargs=2,
        metavar=("YEAR", "Q"),
        type=int,
        help="按季度生成报告，例如 --quarter 2024 1",
    )
    period_group.add_argument(
        "--year",
        type=int,
        help="按全年生成报告，例如 --year 2024",
    )
    period_group.add_argument(
        "--range",
        nargs=2,
        metavar=("START", "END"),
        help="按自定义日期区间生成报告，例如 --range 2024-01-01 2024-06-30",
    )

    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径（默认：config/config.yaml）",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="报告输出目录或文件路径（默认使用配置文件中的 output.directory）",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["csv", "html"],
        default="csv",
        help="报告输出格式（默认: csv）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细日志",
    )
    return parser


def build_period(args: argparse.Namespace) -> ReportPeriod:
    """根据命令行参数构建 ReportPeriod。"""
    if args.quarter:
        year, quarter = args.quarter
        return ReportPeriod.from_year_quarter(year, quarter)
    if args.year:
        return ReportPeriod.from_year(args.year)
    if args.range:
        try:
            start = date.fromisoformat(args.range[0])
            end = date.fromisoformat(args.range[1])
        except ValueError as exc:
            raise ValueError(
                f"日期格式错误，请使用 YYYY-MM-DD 格式: {exc}"
            ) from exc
        return ReportPeriod(start, end)
    raise ValueError("未指定时间周期")


def main() -> int:
    """主程序入口，返回退出码（0 成功，非 0 失败）。"""
    arg_parser = build_arg_parser()
    args = arg_parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 1. 加载配置
    try:
        config = load_config(args.config)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1
    except ValueError as exc:
        logger.error("配置文件错误: %s", exc)
        return 1

    # 2. 确定报告周期
    try:
        period = build_period(args)
    except ValueError as exc:
        logger.error("周期参数错误: %s", exc)
        return 1

    logger.info("报告周期: %s", period)

    # 3. 初始化组件
    parsers = []
    # 富国基金解析器（sender 匹配优先，放在通用解析器之前）
    parsers.append(FullgoalEmailParser())
    if config.parsers.fund_email.enabled:
        parsers.append(
            FundEmailParser(
                sender_patterns=config.parsers.fund_email.sender_patterns,
            )
        )

    if not parsers:
        logger.warning("没有启用任何解析器，请检查配置文件中的 parsers 节点")

    generator = ReportGenerator()
    exporter = HTMLExporter() if args.format == "html" else CSVExporter()
    output_dir = args.output or config.output.directory

    # 4. 从邮箱获取数据
    holdings = []
    try:
        with EmailSource(config.email) as source:
            logger.info("正在从邮箱获取周期 %s 内的邮件...", period)
            raw_emails = source.fetch(period)
            logger.info("共找到 %d 封邮件", len(raw_emails))

            for raw in raw_emails:
                for p in parsers:
                    if p.can_parse(raw):
                        new_records = p.parse(raw)
                        holdings.extend(new_records)
                        break

    except Exception as exc:
        logger.error("获取邮件时出错: %s", exc)
        return 1

    logger.info("解析到 %d 条持仓记录", len(holdings))

    # 5. 生成报告
    report = generator.generate(holdings, period)
    logger.info(
        "报告生成完成: %d 个标的，总收益 %.2f 元，总收益率 %.2f%%",
        len(report.holdings),
        float(report.total_profit),
        float(report.total_profit_rate) * 100,
    )

    # 6. 导出报告
    try:
        output_path = exporter.export(report, output_dir)
        logger.info("报告已保存至: %s", output_path)
        print(f"\n✓ 报告生成成功: {output_path}")
    except Exception as exc:
        logger.error("导出报告时出错: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
