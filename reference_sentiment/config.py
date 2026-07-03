"""
配置文件 - 引用链接舆情分析
"""
import os
import json
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent

# 数据库配置（保存到 reference_sentiment 目录下）
DATABASE_PATH = BASE_DIR / "reference_sentiment" / "reference_sentiment.db"
DATABASE_URI = f"sqlite:///{DATABASE_PATH}"

# 现有数据库配置（只读，用于读取采集结果）
EXISTING_DATABASE_PATH = BASE_DIR / "web_app" / "instance" / "ai_monitor.db"
EXISTING_DATABASE_URI = f"sqlite:///{EXISTING_DATABASE_PATH}"

# 引用链接内容存储目录
REFERENCE_CONTENT_DIR = BASE_DIR / "reference_sentiment" / "content"
REFERENCE_CONTENT_DIR.mkdir(parents=True, exist_ok=True)

# 舆情分析结果存储目录
SENTIMENT_RESULT_DIR = BASE_DIR / "reference_sentiment" / "results"
SENTIMENT_RESULT_DIR.mkdir(parents=True, exist_ok=True)

# 日志配置
LOG_DIR = BASE_DIR / "reference_sentiment" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "reference_sentiment.log"

# 采集配置
CRAWL_TIMEOUT = 30  # 网页请求超时时间（秒）
CRAWL_RETRY_TIMES = 3  # 失败重试次数
CRAWL_RETRY_DELAY = 2  # 重试延迟（秒）

# 舆情分析配置
SENTIMENT_BATCH_SIZE = 10  # 批量分析数量
SENTIMENT_INTERVAL = 60  # 分析间隔（秒）

# 用户代理
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# 舆情分析关键词配置
DEFAULT_SENTIMENT_CONFIG = {
    'positive_words': [
        '好', '优秀', '出色', '好评', '推荐', '满意', '赞', '棒', '完美', '精彩',
        '专业', '可靠', '放心', '安全', '便捷', '高效', '稳定', '流畅', '清晰',
        '贴心', '周到', '细致', '认真', '负责', '诚信', '良心', '物超所值', '好评如潮',
        '值得', '信赖', '安心', '舒适', '实用', '方便', '快速', '准确', '清晰',
        '创新', '领先', '卓越', '杰出', '优异', '精湛', '高品质', '高性能', '高性价比'
    ],
    'negative_words': [
        '坏', '差', '糟糕', '差评', '投诉', '不满', '垃圾', '坑', '骗', '假',
        '劣质', '失败', '问题', '错误', '崩溃', '卡顿', '慢', '难用', '复杂',
        '麻烦', '浪费', '后悔', '失望', '愤怒', '伤心', '无语', '欺骗', '虚假',
        '坑人', '上当', '被骗', '欺诈', '劣质', '次品', '缺陷', '故障', '漏洞',
        '卡顿', '闪退', '崩溃', '不稳定', '不兼容', '不推荐', '不建议', '千万别'
    ],
    'enable_ai_sentiment': False,
    'ai_config': {}
}