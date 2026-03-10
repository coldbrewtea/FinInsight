"""基于本地文件系统的邮件数据源（用于测试和调试）。

从本地目录读取 .eml 文件，无需真实的 IMAP 连接，
适用于集成测试和对账单格式调试。

用法::

    source = FileSource("./tests/fixtures/emails/")
    emails = source.fetch(period)  # 返回与 period 相关的邮件（或全部）
"""

from __future__ import annotations

import email
import logging
import os
from email.message import Message
from typing import List

from fininsight.models.records import ReportPeriod

from .base import DataSource

logger = logging.getLogger(__name__)


class FileSource(DataSource):
    """从本地目录读取 .eml 文件作为数据源。

    不过滤日期（返回目录中所有 .eml 文件），适合本地调试和测试。

    参数:
        directory: 包含 .eml 文件的目录路径
    """

    def __init__(self, directory: str) -> None:
        self._directory = os.path.expanduser(directory)

    def fetch(self, period: ReportPeriod) -> List[Message]:
        """读取目录下所有 .eml 文件并返回邮件对象列表。

        注意：FileSource 不按日期过滤邮件，会返回目录中所有 .eml 文件。
        请确保目录中只放置与目标周期相关的对账单文件。
        """
        if not os.path.isdir(self._directory):
            logger.warning("目录不存在: %s", self._directory)
            return []

        messages: List[Message] = []
        for filename in sorted(os.listdir(self._directory)):
            if not filename.lower().endswith(".eml"):
                continue
            filepath = os.path.join(self._directory, filename)
            try:
                with open(filepath, "rb") as f:
                    msg = email.message_from_bytes(f.read())
                messages.append(msg)
                logger.debug("已读取邮件文件: %s", filename)
            except Exception as exc:
                logger.warning("读取文件 %s 失败: %s", filename, exc)

        logger.info("从 %s 读取了 %d 封邮件", self._directory, len(messages))
        return messages

    def close(self) -> None:
        pass  # 无资源需要释放
