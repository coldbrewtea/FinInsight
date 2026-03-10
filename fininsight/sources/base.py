"""数据源抽象基类。

所有数据源（邮箱、CSV 文件、API 等）都应继承 DataSource，
实现 fetch() 方法返回原始数据项列表，供解析器消费。
"""

from abc import ABC, abstractmethod
from typing import Any, List

from fininsight.models.records import ReportPeriod


class DataSource(ABC):
    """投资数据源抽象基类。

    子类示例：
        - EmailSource：从 IMAP 邮箱抓取对账单邮件
        - CsvFileSource：从本地 CSV 文件读取历史数据（可扩展）
    """

    @abstractmethod
    def fetch(self, period: ReportPeriod) -> List[Any]:
        """获取指定时间周期内的原始数据列表。

        Args:
            period: 报告时间周期

        Returns:
            原始数据项列表（具体类型由子类定义），供解析器（StatementParser）处理。
        """

    @abstractmethod
    def close(self) -> None:
        """释放数据源占用的资源（连接、文件句柄等）。"""

    def __enter__(self) -> "DataSource":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
