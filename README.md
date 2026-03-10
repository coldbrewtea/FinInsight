# FinInsight

家庭投资报表工具，支持从邮箱自动获取对账单、解析持仓数据，生成周期性投资报告（CSV）。

## 功能特性

- **数据源**：通过 IMAP 协议从邮箱获取基金/银行发送的对账单邮件
- **市场分类**：A 股、港股、美股、境内（基金、黄金、存单等）
- **资产类别**：基金、股票、黄金、大额存单、债券等
- **周期报告**：支持按季度、全年或自定义日期区间生成报告
- **收益计算**：期初/期末市值、入金/出金、收益值、收益率（简单 Dietz 法）、收益贡献率
- **输出格式**：CSV（带 BOM，Excel 可直接打开）
- **可扩展**：数据源、解析器、导出器三层完全解耦，可方便地新增支持

## 项目结构

```
FinInsight/
├── fininsight/
│   ├── models/          # 核心数据结构（Asset, HoldingRecord, Report 等）
│   ├── sources/         # 数据源（DataSource 抽象类 + EmailSource）
│   ├── parsers/         # 解析器（StatementParser 抽象类 + FundEmailParser）
│   ├── processors/      # 报告生成器（ReportGenerator）
│   ├── exporters/       # 导出器（ReportExporter 抽象类 + CSVExporter）
│   └── config_loader.py # 配置加载
├── tests/               # 单元测试（pytest）
├── config/
│   └── config.example.yaml  # 配置模板（含占位符）
├── main.py              # CLI 入口
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置邮箱

```bash
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，填入邮箱地址、密码等信息
```

> **注意**：`config/config.yaml` 已在 `.gitignore` 中，不会被提交到版本库。
> 使用 Gmail 时，需要开启「两步验证」并生成「应用专用密码」。

### 3. 运行

```bash
# 生成 2024 年 Q1 季报
python main.py --quarter 2024 1

# 生成 2024 年年报
python main.py --year 2024

# 自定义日期区间
python main.py --range 2024-01-01 2024-06-30

# 指定输出目录
python main.py --quarter 2024 3 --output ./reports
```

报告将输出到 `./output/` 目录（或通过 `--output` 指定），文件名格式：`report_2024-01-01_2024-03-31.csv`。

## CSV 报告格式

| 列名 | 说明 |
|------|------|
| 投资标的名称 | 基金/股票名称 |
| 代码 | 基金代码或股票代码 |
| 市场 | A股 / 港股 / 美股 / 境内 |
| 类别 | 基金 / 股票 / 黄金 / 大额存单 / 债券 |
| 期初市值(元) | 周期开始时的持仓市值 |
| 期末市值(元) | 周期结束时的持仓市值 |
| 入金(元) | 周期内申购/买入金额 |
| 出金(元) | 周期内赎回/卖出金额 |
| 收益(元) | 期末 − 期初 − 净投入 |
| 收益率(%) | 收益 / (期初 + 净投入) |
| 收益贡献率(%) | 本标的收益 / 全部标的总收益 |

## 运行测试

```bash
python -m pytest tests/ -v
```

## 扩展指南

### 新增数据源

继承 `fininsight/sources/base.py` 中的 `DataSource`，实现 `fetch()` 方法即可。

### 新增解析器

继承 `fininsight/parsers/base.py` 中的 `StatementParser`，实现 `can_parse()` 和 `parse()` 方法。

可通过继承 `FundEmailParser` 并覆盖 `_extract_period()` 或 `_extract_holdings()` 来适配特定机构邮件格式。

### 新增输出格式

继承 `fininsight/exporters/base.py` 中的 `ReportExporter`，实现 `export()` 方法即可（如 Excel、JSON 等）。

## 依赖

- `beautifulsoup4` — HTML 邮件解析
- `pyyaml` — 配置文件加载
- `lxml` — HTML 解析后端
- `pytest` — 单元测试
