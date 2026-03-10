"""基于 IMAP 协议的邮箱数据源。

使用 Python 标准库 imaplib 连接邮箱服务器，按日期范围检索邮件，
返回 email.message.Message 对象列表供解析器处理。
"""

from __future__ import annotations

import email
import imaplib
import logging
from datetime import timedelta
from email.message import Message
from typing import List, Optional

from fininsight.config_loader import EmailConfig
from fininsight.models.records import ReportPeriod

from .base import DataSource

logger = logging.getLogger(__name__)

# IMAP 日期格式，例如 "01-Jan-2024"
_IMAP_DATE_FMT = "%d-%b-%Y"


class EmailSource(DataSource):
    """通过 IMAP 协议从邮箱获取投资对账单邮件。

    用法::

        config = load_config()
        with EmailSource(config.email) as source:
            emails = source.fetch(period)

    返回的每个 email.message.Message 对象可以传给
    ``StatementParser.can_parse()`` / ``StatementParser.parse()``。
    """

    def __init__(self, config: EmailConfig) -> None:
        self._config = config
        self._conn: Optional[imaplib.IMAP4] = None

    # ------------------------------------------------------------------
    # DataSource interface
    # ------------------------------------------------------------------

    def fetch(self, period: ReportPeriod) -> List[Message]:
        """检索指定时间周期内收到的所有邮件。

        Args:
            period: 报告时间周期

        Returns:
            期间内收到的邮件列表（email.message.Message）
        """
        self._ensure_connected()

        self._conn.select(self._config.mailbox)  # type: ignore[union-attr]

        # IMAP SEARCH 的 BEFORE 不含当天，因此结束日期 +1 天
        since = period.start_date.strftime(_IMAP_DATE_FMT)
        before = (period.end_date + timedelta(days=1)).strftime(_IMAP_DATE_FMT)
        search_criterion = f'(SINCE "{since}" BEFORE "{before}")'

        logger.debug("IMAP search: %s in %s", search_criterion, self._config.mailbox)
        status, data = self._conn.search(None, search_criterion)  # type: ignore[union-attr]

        if status != "OK" or not data or not data[0]:
            logger.info("该时间段内未找到邮件: %s", period)
            return []

        messages: List[Message] = []
        for msg_id in data[0].split():
            try:
                status, msg_data = self._conn.fetch(msg_id, "(RFC822)")  # type: ignore[union-attr]
                if status != "OK" or not msg_data or msg_data[0] is None:
                    continue
                raw_bytes = msg_data[0][1]  # type: ignore[index]
                msg = email.message_from_bytes(raw_bytes)
                messages.append(msg)
            except Exception as exc:
                logger.warning("读取邮件 %s 时出错: %s", msg_id, exc)

        logger.info("共检索到 %d 封邮件", len(messages))
        return messages

    def close(self) -> None:
        """退出 IMAP 会话，释放连接。"""
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception:
                pass
            finally:
                self._conn = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """按需建立 IMAP 连接并登录。"""
        if self._conn is not None:
            return

        cfg = self._config
        logger.info("连接 IMAP 服务器 %s:%s ...", cfg.host, cfg.port)

        if cfg.use_ssl:
            self._conn = imaplib.IMAP4_SSL(cfg.host, cfg.port)
        else:
            self._conn = imaplib.IMAP4(cfg.host, cfg.port)

        self._conn.login(cfg.username, cfg.password)
        logger.info("IMAP 登录成功: %s", cfg.username)
