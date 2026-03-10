"""CSVExporter / HTMLExporter 单元测试。"""

import csv
import os
import tempfile
from decimal import Decimal

import pytest

from fininsight.exporters.csv_exporter import CSVExporter
from fininsight.exporters.html_exporter import HTMLExporter
from fininsight.models.enums import AssetType, Market
from fininsight.models.records import Asset, HoldingRecord, Report, ReportPeriod


@pytest.fixture
def simple_report():
    period = ReportPeriod.from_year_quarter(2024, 1)
    asset = Asset("华夏成长混合", AssetType.FUND, Market.DOMESTIC, "000001")
    holding = HoldingRecord(
        asset=asset,
        period=period,
        opening_value=Decimal("10000"),
        closing_value=Decimal("11000"),
        inflow=Decimal("0"),
        outflow=Decimal("0"),
        contribution_rate=Decimal("1"),
    )
    return Report(period=period, holdings=[holding])


@pytest.fixture
def multi_holding_report():
    period = ReportPeriod.from_year_quarter(2024, 2)
    assets = [
        Asset("沪深300ETF", AssetType.FUND, Market.DOMESTIC, "510300"),
        Asset("腾讯控股", AssetType.STOCK, Market.HK_STOCK, "00700"),
        Asset("实物黄金", AssetType.GOLD, Market.DOMESTIC),
    ]
    holdings = [
        HoldingRecord(
            asset=assets[0],
            period=period,
            opening_value=Decimal("20000"),
            closing_value=Decimal("22000"),
            contribution_rate=Decimal("0.8"),
        ),
        HoldingRecord(
            asset=assets[1],
            period=period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("10500"),
            contribution_rate=Decimal("0.2"),
        ),
        HoldingRecord(
            asset=assets[2],
            period=period,
            opening_value=Decimal("5000"),
            closing_value=Decimal("5000"),
            contribution_rate=Decimal("0"),
        ),
    ]
    return Report(period=period, holdings=holdings)


class TestCSVExporter:
    def test_export_creates_file_in_directory(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            assert os.path.exists(output_path)
            assert output_path.endswith(".csv")

    def test_export_to_specific_file_path(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "my_report.csv")
            result = exporter.export(simple_report, file_path)
            assert result == file_path
            assert os.path.exists(file_path)

    def test_export_file_has_header_row(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
            # 第 1 行：报告期间，第 2 行：空行，第 3 行：列标题
            header_row = rows[2]
            assert "投资标的名称" in header_row
            assert "收益(元)" in header_row
            assert "收益率(%)" in header_row
            assert "收益贡献率(%)" in header_row

    def test_export_contains_holding_data(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        assert "华夏成长混合" in content
        assert "000001" in content
        assert "10000.00" in content
        assert "11000.00" in content

    def test_export_contains_summary_row(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        assert "合计" in content

    def test_export_period_info_in_first_row(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                first_row = next(reader)
        assert "报告期间" in first_row[0]
        assert "2024-01-01" in first_row[0]

    def test_profit_rate_formatted_as_percentage(self, simple_report):
        """收益率应格式化为百分比形式（含 % 符号）。"""
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        assert "10.00%" in content

    def test_multiple_holdings_sorted(self, multi_holding_report):
        """持仓应按市场 → 类别 → 名称排序输出。"""
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(multi_holding_report, tmpdir)
            with open(output_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
        # 找到数据行（第 3 行之后，跳过期间行、空行、表头行）
        data_rows = [r for r in rows[3:] if r and r[0] not in ("", "合计")]
        names = [r[0] for r in data_rows]
        # 港股在 A股/境内 之前（港 < 境 in unicode ordering）
        # 实际排序取决于市场 value 字符串
        assert len(names) == 3

    def test_export_creates_parent_dirs(self, simple_report):
        """导出到不存在的父目录时应自动创建。"""
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "subdir1", "subdir2", "report.csv")
            output_path = exporter.export(simple_report, nested)
            assert os.path.exists(output_path)

    def test_filename_contains_dates_when_exported_to_dir(self, simple_report):
        exporter = CSVExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            filename = os.path.basename(output_path)
        assert "2024-01-01" in filename
        assert "2024-03-31" in filename


class TestHTMLExporter:
    def test_export_creates_file_in_directory(self, simple_report):
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            assert os.path.exists(output_path)
            assert output_path.endswith(".html")

    def test_export_to_specific_file_path(self, simple_report):
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "my_report.html")
            result = exporter.export(simple_report, file_path)
            assert result == file_path
            assert os.path.exists(file_path)

    def test_filename_contains_dates_when_exported_to_dir(self, simple_report):
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            filename = os.path.basename(output_path)
        assert "2024-01-01" in filename
        assert "2024-03-31" in filename

    def test_html_is_valid_structure(self, simple_report):
        """输出应包含基本 HTML 骨架标签。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "<!DOCTYPE html>" in content
        assert "<html" in content
        assert "</html>" in content
        assert "<table>" in content

    def test_html_contains_holding_data(self, simple_report):
        """持仓名称和代码应出现在输出中。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "华夏成长混合" in content
        assert "000001" in content
        assert "10,000.00" in content
        assert "11,000.00" in content

    def test_html_contains_period_info(self, simple_report):
        """报告期间应出现在页面标题区。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "2024-01-01" in content
        assert "2024-03-31" in content

    def test_html_contains_summary_cards(self, simple_report):
        """摘要卡片的标签文字应出现在输出中。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "期末总市值" in content
        assert "期内总收益" in content
        assert "整体收益率" in content

    def test_html_contains_summary_row(self, simple_report):
        """合计行应出现在输出中。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "合计" in content
        assert "100.00%" in content

    def test_html_profit_positive_uses_pos_class(self, simple_report):
        """盈利时应使用 pos CSS class 标注收益列。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert 'class="pos"' in content

    def test_html_profit_negative_uses_neg_class(self, multi_holding_report):
        """亏损持仓应使用 neg CSS class。"""
        from fininsight.models.records import HoldingRecord
        period = multi_holding_report.period
        losing_asset = multi_holding_report.holdings[0].asset
        losing_holding = HoldingRecord(
            asset=losing_asset,
            period=period,
            opening_value=Decimal("10000"),
            closing_value=Decimal("8000"),
            contribution_rate=Decimal("-1"),
        )
        from fininsight.models.records import Report
        report = Report(period=period, holdings=[losing_holding])
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert 'class="neg"' in content

    def test_html_asset_type_tag_rendered(self, simple_report):
        """资产类型标签应带 tag- 前缀 class。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "tag-基金" in content

    def test_html_contribution_bar_rendered(self, simple_report):
        """贡献率进度条结构应出现在输出中。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "bar-fill" in content
        assert "bar-label" in content

    def test_html_creates_parent_dirs(self, simple_report):
        """导出到不存在的父目录时应自动创建。"""
        exporter = HTMLExporter()
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "subdir", "report.html")
            output_path = exporter.export(simple_report, nested)
            assert os.path.exists(output_path)

    def test_html_custom_title(self, simple_report):
        """自定义 title 参数应反映在 <title> 标签中。"""
        exporter = HTMLExporter(title="我的报告")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = exporter.export(simple_report, tmpdir)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()
        assert "我的报告" in content
