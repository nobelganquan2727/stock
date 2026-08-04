"""
核心自选池：只关注这 50 只股票。
代码格式与 yfinance 一致：沪市 .SS，深市 .SZ。
"""

from typing import Dict, List, Optional, Tuple


def _code(symbol: str) -> str:
    """纯数字代码 → yfinance 后缀"""
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SS"
    return f"{symbol}.SZ"


# (代码, 名称) — 顺序即用户提供的顺序
_WATCHLIST_RAW: List[Tuple[str, str]] = [
    ("600900", "长江电力"),
    ("601088", "中国神华"),
    ("600941", "中国移动"),
    ("601398", "工商银行"),
    ("601939", "建设银行"),
    ("601288", "农业银行"),
    ("601628", "中国人寿"),
    ("600028", "中国石化"),
    ("601225", "陕西煤业"),
    ("601816", "京沪高铁"),
    ("600036", "招商银行"),
    ("601318", "中国平安"),
    ("600030", "中信证券"),
    ("601166", "兴业银行"),
    ("601899", "紫金矿业"),
    ("600938", "中国海油"),
    ("601857", "中国石油"),
    ("600406", "国电南瑞"),
    ("601985", "中国核电"),
    ("600023", "浙能电力"),
    ("600519", "贵州茅台"),
    ("000858", "五粮液"),
    ("000651", "格力电器"),
    ("000333", "美的集团"),
    ("600887", "伊利股份"),
    ("000895", "双汇发展"),
    ("603288", "海天味业"),
    ("600276", "恒瑞医药"),
    ("300760", "迈瑞医疗"),
    ("600436", "片仔癀"),
    ("600150", "中国船舶"),
    ("601766", "中国中车"),
    ("600031", "三一重工"),
    ("000338", "潍柴动力"),
    ("600660", "福耀玻璃"),
    ("300124", "汇川技术"),
    ("601100", "恒立液压"),
    ("600309", "万华化学"),
    ("600176", "中国巨石"),
    ("601668", "中国建筑"),
    ("688981", "中芯国际"),
    ("300750", "宁德时代"),
    ("002594", "比亚迪"),
    ("601012", "隆基绿能"),
    ("300274", "阳光电源"),
    ("002475", "立讯精密"),
    ("002241", "歌尔股份"),
    ("688041", "海光信息"),
    ("002415", "海康威视"),
    ("600745", "闻泰科技"),
]

WATCHLIST: List[Dict[str, str]] = [
    {"code": _code(symbol), "symbol": symbol, "name": name}
    for symbol, name in _WATCHLIST_RAW
]

WATCHLIST_CODES: List[str] = [item["code"] for item in WATCHLIST]

WATCHLIST_NAMES: Dict[str, str] = {
    item["code"]: item["name"] for item in WATCHLIST
}


def get_watchlist_codes() -> List[str]:
    """返回核心自选池代码列表"""
    return list(WATCHLIST_CODES)


def get_stock_name(code: str) -> str:
    """按代码取中文名；未知则返回代码本身"""
    if code in WATCHLIST_NAMES:
        return WATCHLIST_NAMES[code]
    bare = code.split(".")[0]
    for item in WATCHLIST:
        if item["symbol"] == bare:
            return item["name"]
    return code


def normalize_code(code: str) -> Optional[str]:
    """把 600519 / 600519.SS / 600519.SH 统一成自选池格式"""
    bare = code.split(".")[0].zfill(6)
    candidate = _code(bare)
    if candidate in WATCHLIST_NAMES:
        return candidate
    return None
