"""Investment classification enumerations."""

from enum import Enum


class Market(str, Enum):
    """投资市场分类。"""

    A_SHARE = "A股"    # A 股市场（沪深交易所）
    HK_STOCK = "港股"  # 香港股票市场
    US_STOCK = "美股"  # 美国股票市场
    DOMESTIC = "境内"  # 境内非股票市场（基金、黄金、存单等）


class AssetType(str, Enum):
    """投资标的类别。"""

    FUND = "基金"       # 公募基金、ETF 等
    STOCK = "股票"      # 个股
    GOLD = "黄金"       # 实物黄金、黄金 ETF 等
    CD = "大额存单"     # 大额存单
    BOND = "债券"       # 债券
    CASH = "现金"       # 货币基金、活期等
    OTHER = "其他"      # 其他资产
