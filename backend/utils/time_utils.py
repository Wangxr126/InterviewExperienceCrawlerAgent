"""
时间工具模块 - 统一使用北京时间 (UTC+8)
"""
from datetime import datetime, timezone, timedelta

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def now_beijing() -> datetime:
    """获取当前北京时间"""
    return datetime.now(BEIJING_TZ)


def now_beijing_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取当前北京时间的字符串格式"""
    return now_beijing().strftime(fmt)


def timestamp_to_beijing(timestamp: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将时间戳转换为北京时间字符串
    
    Args:
        timestamp: Unix时间戳（秒）或 SQLite datetime 字符串
        fmt: 时间格式字符串
    
    Returns:
        北京时间字符串
    """
    # 如果是字符串，先解析为 datetime
    if isinstance(timestamp, str):
        return sqlite_datetime_to_beijing(timestamp, fmt)
    
    dt = datetime.fromtimestamp(timestamp, tz=BEIJING_TZ)
    return dt.strftime(fmt)


def sqlite_datetime_to_beijing(datetime_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将 SQLite datetime 字符串转换为北京时间字符串
    SQLite CURRENT_TIMESTAMP 返回 UTC 时间，格式如: '2025-01-05 12:30:45'
    
    Args:
        datetime_str: SQLite datetime 字符串
        fmt: 输出时间格式字符串
    
    Returns:
        北京时间字符串
    """
    # 解析 SQLite datetime 字符串（UTC时间）
    dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    dt = dt.replace(tzinfo=timezone.utc)
    
    # 转换到北京时区
    beijing_dt = dt.astimezone(BEIJING_TZ)
    return beijing_dt.strftime(fmt)


def timestamp_ms_to_beijing(timestamp_ms: int, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将毫秒时间戳转换为北京时间字符串
    
    Args:
        timestamp_ms: Unix时间戳（毫秒）
        fmt: 时间格式字符串
    
    Returns:
        北京时间字符串
    """
    return timestamp_to_beijing(timestamp_ms / 1000, fmt)


def datetime_to_beijing_str(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将datetime对象转换为北京时间字符串
    
    Args:
        dt: datetime对象
        fmt: 时间格式字符串
    
    Returns:
        北京时间字符串
    """
    if dt.tzinfo is None:
        # 如果没有时区信息，假设是UTC时间
        dt = dt.replace(tzinfo=timezone.utc)
    
    # 转换到北京时区
    beijing_dt = dt.astimezone(BEIJING_TZ)
    return beijing_dt.strftime(fmt)
