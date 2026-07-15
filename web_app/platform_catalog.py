"""Canonical AI platform catalog shared by desktop features."""

PLATFORM_CATALOG = (
    {"id": "doubao", "name": "豆包", "url": "https://www.doubao.com/chat"},
    {"id": "deepseek", "name": "DeepSeek", "url": "https://chat.deepseek.com"},
    {"id": "yuanbao", "name": "腾讯元宝", "url": "https://yuanbao.tencent.com/chat"},
    {"id": "kimi", "name": "Kimi", "url": "https://www.kimi.com"},
    {"id": "qianwen", "name": "通义千问", "url": "https://www.qianwen.com"},
    {"id": "wenxin", "name": "文心一言（wenxin）", "url": "https://wenxin.baidu.com"},
    {"id": "yiyan", "name": "文心一言（yiyan）", "url": "https://yiyan.baidu.com"},
    {"id": "chatgpt", "name": "ChatGPT", "url": "https://chatgpt.com"},
)

SUPPORTED_PLATFORM_IDS = frozenset(item["id"] for item in PLATFORM_CATALOG)


def supported_platforms() -> list[dict[str, str]]:
    """Return independent dictionaries so callers cannot mutate the catalog."""
    return [dict(item) for item in PLATFORM_CATALOG]
