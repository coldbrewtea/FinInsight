"""配置文件加载器。

从 config/config.yaml 读取配置，映射到类型安全的 dataclass 对象。
真实配置文件在 .gitignore 中，请参考 config/config.example.yaml 创建。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml


@dataclass
class EmailConfig:
    """IMAP 邮箱配置。"""

    host: str
    username: str
    password: str
    port: int = 993
    use_ssl: bool = True
    mailbox: str = "INBOX"


@dataclass
class OutputConfig:
    """报告输出配置。"""

    directory: str = "./output"


@dataclass
class FundEmailParserConfig:
    """基金邮件解析器配置。"""

    enabled: bool = True
    sender_patterns: List[str] = field(default_factory=list)


@dataclass
class ParsersConfig:
    """解析器汇总配置。"""

    fund_email: FundEmailParserConfig = field(default_factory=FundEmailParserConfig)


@dataclass
class AppConfig:
    """应用全局配置。"""

    email: EmailConfig
    output: OutputConfig = field(default_factory=OutputConfig)
    parsers: ParsersConfig = field(default_factory=ParsersConfig)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """从 YAML 文件加载应用配置。

    Args:
        config_path: 配置文件路径。若为 None，则自动查找项目根目录下的
                     ``config/config.yaml``。

    Returns:
        AppConfig 实例。

    Raises:
        FileNotFoundError: 配置文件不存在。
        ValueError: 配置文件缺少必要字段。
    """
    if config_path is None:
        # 相对于本模块所在目录向上两级找项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(project_root, "config", "config.yaml")

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"配置文件未找到: {config_path}\n"
            "请先复制模板并填入真实信息：\n"
            "  cp config/config.example.yaml config/config.yaml"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "email" not in data:
        raise ValueError("配置文件缺少必要的 'email' 节点")

    email_raw = data["email"]
    _require_fields(email_raw, ("host", "username", "password"), section="email")

    email_config = EmailConfig(
        host=email_raw["host"],
        username=email_raw["username"],
        password=email_raw["password"],
        port=email_raw.get("port", 993),
        use_ssl=email_raw.get("use_ssl", True),
        mailbox=email_raw.get("mailbox", "INBOX"),
    )

    output_raw = data.get("output", {}) or {}
    output_config = OutputConfig(
        directory=output_raw.get("directory", "./output"),
    )

    parsers_raw = data.get("parsers", {}) or {}
    fund_raw = parsers_raw.get("fund_email", {}) or {}
    fund_config = FundEmailParserConfig(
        enabled=fund_raw.get("enabled", True),
        sender_patterns=fund_raw.get("sender_patterns") or [],
    )

    return AppConfig(
        email=email_config,
        output=output_config,
        parsers=ParsersConfig(fund_email=fund_config),
    )


def _require_fields(data: dict, fields: tuple, section: str) -> None:
    """检查必要字段是否存在且不为空。"""
    for f in fields:
        if f not in data or not data[f]:
            raise ValueError(f"配置文件 [{section}] 节点缺少必要字段: {f}")
