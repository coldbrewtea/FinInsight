"""解析器抽象基类。

各类数据源的解析器（邮件解析、文件解析等）继承 StatementParser，
实现 can_parse() 和 parse() 方法，将原始数据转换为 HoldingRecord 列表。
"""

from abc import ABC, abstractmethod
from typing import Any, List

from fininsight.models.records import HoldingRecord


class StatementParser(ABC):
    """投资对账单解析器抽象基类。

    职责：将来自 DataSource 的原始数据项解析为 HoldingRecord 列表。
    每种机构/数据格式可实现独立的子类。

    子类示例：
        - FundEmailParser：解析基金公司发送的 HTML 对账单邮件
        - BankCsvParser：解析银行导出的 CSV 持仓明细（可扩展）
    """

    @abstractmethod
    def can_parse(self, raw_data: Any) -> bool:
        """判断本解析器是否能处理该数据项。

        应根据数据类型、发件人、邮件主题关键词等快速判断，
        避免执行完整解析逻辑。

        Args:
            raw_data: 来自 DataSource.fetch() 的单条原始数据

        Returns:
            True 表示本解析器可以处理该数据
        """

    @abstractmethod
    def parse(self, raw_data: Any) -> List[HoldingRecord]:
        """将单条原始数据解析为持仓记录列表。

        Args:
            raw_data: 来自 DataSource.fetch() 的单条原始数据（已通过 can_parse 确认）

        Returns:
            解析得到的 HoldingRecord 列表；无法解析时返回空列表而非抛异常。
        """
