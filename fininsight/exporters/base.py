"""报告导出器抽象基类。

所有输出格式（CSV、Excel、JSON 等）都应继承 ReportExporter，
实现 export() 方法，将 Report 对象写入指定路径。
"""

from abc import ABC, abstractmethod

from fininsight.models.records import Report


class ReportExporter(ABC):
    """投资报告导出器抽象基类。

    子类示例：
        - CSVExporter：导出为 CSV 文件（已实现）
        - ExcelExporter：导出为 Excel 工作簿（可扩展）
        - JsonExporter：导出为 JSON 文件（可扩展）
    """

    @abstractmethod
    def export(self, report: Report, output_path: str) -> str:
        """将报告导出到指定路径。

        Args:
            report:      要导出的投资报告
            output_path: 输出文件路径或目录路径。
                         - 若传入目录，子类应在该目录下自动生成文件名；
                         - 若传入文件路径，直接写入该文件。

        Returns:
            实际写入的文件路径。
        """
