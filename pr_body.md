## 概述

从零搭建 FinInsight 家庭投资报表工具的完整初始实现。

## 架构设计

三层完全解耦：**数据源 → 解析器 → 导出器**，各层通过标准数据结构（`HoldingRecord` / `Report`）流转，便于独立扩展。

```
EmailSource (IMAP) → FundEmailParser (HTML解析) → ReportGenerator → CSVExporter
```

## 新增内容

### 核心数据模型 (`fininsight/models/`)
- `Asset`：投资标的（名称、代码、市场、类别），frozen dataclass
- `ReportPeriod`：报告时间周期，支持 `from_year_quarter()` / `from_year()` 工厂方法
- `HoldingRecord`：持仓记录，含 `profit` / `profit_rate` 计算属性（简单 Dietz 法）
- `Report`：完整报告，含汇总属性
- `Market` / `AssetType`：市场和资产类别枚举（A股/港股/美股/境内、基金/股票/黄金/大额存单等）

### 数据源层 (`fininsight/sources/`)
- `DataSource` 抽象基类（支持 context manager）
- `EmailSource`：通过 `imaplib` 连接 IMAP 邮箱，按日期范围检索邮件

### 解析器层 (`fininsight/parsers/`)
- `StatementParser` 抽象基类（`can_parse()` + `parse()`）
- `FundEmailParser`：解析 HTML 格式基金对账单邮件
  - 自动识别季度/年度/自定义区间格式的邮件主题
  - BeautifulSoup 解析持仓表格，支持多种列名模式
  - 基于名称关键词和代码格式推断市场/资产类别
  - 可继承并覆盖 hook 方法适配特定机构格式

### 报告生成器 (`fininsight/processors/`)
- `ReportGenerator`：合并重复持仓、计算收益贡献率

### 导出器 (`fininsight/exporters/`)
- `ReportExporter` 抽象基类
- `CSVExporter`：输出 UTF-8 BOM CSV（兼容 Excel），含按市场/类别/名称排序的明细行和合计行

### 配置与安全
- `config/config.example.yaml`：含 `{{EMAIL_PASSWORD}}` 等占位符，安全提交到 git
- `config/config.yaml`：真实配置，已加入 `.gitignore`

### CLI 入口
- `main.py`：支持 `--quarter YEAR Q` / `--year YEAR` / `--range START END` 参数

### 单元测试
- `tests/` 下 4 个测试文件，共 75 个测试用例，全部通过
- 覆盖：数据模型计算、报告生成器、CSV 导出格式、解析器 HTML 解析

## 测试运行

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

---
_This PR was generated with [Oz](https://www.warp.dev/oz)._
