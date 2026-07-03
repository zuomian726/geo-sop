"""
Web应用配置
"""
import os
from datetime import timedelta
from local_paths import app_data_dir, instance_dir, database_path, answers_dir

class Config:
    """基础配置"""
    
    DESKTOP_MODE = os.environ.get('GEO_DESKTOP_MODE') == '1'

    # 获取当前文件所在目录（web_app目录）
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = app_data_dir() if DESKTOP_MODE else BASE_DIR
    
    # 实例目录（存放数据库等数据文件）
    INSTANCE_DIR = instance_dir() if DESKTOP_MODE else os.path.join(BASE_DIR, 'instance')
    os.makedirs(INSTANCE_DIR, exist_ok=True)  # 确保目录存在
    
    # 密钥
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # 数据库 - 使用绝对路径确保在任何位置启动都能找到正确的数据库文件
    DATABASE_PATH = database_path() if DESKTOP_MODE else os.path.join(INSTANCE_DIR, 'ai_monitor.db')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ANSWERS_DIR = os.environ.get('GEO_ANSWERS_DIR') or (answers_dir() if DESKTOP_MODE else os.path.join(BASE_DIR, 'answers'))
    CLOUD_SYNC_ENABLED = os.environ.get('GEO_CLOUD_SYNC_ENABLED') == '1'
    CLOUD_SYNC_URL = os.environ.get('GEO_CLOUD_SYNC_URL') or os.environ.get('CLOUD_SYNC_URL')
    CLOUD_SYNC_TOKEN = os.environ.get('GEO_CLOUD_SYNC_TOKEN') or os.environ.get('CLOUD_SYNC_TOKEN')
    CLOUD_SYNC_KEYS = os.environ.get('GEO_CLOUD_SYNC_KEYS') == '1'
    REQUIRE_LOGIN = os.environ.get('GEO_REQUIRE_LOGIN') == '1' or CLOUD_SYNC_ENABLED
    
    # Session配置
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # 文件上传
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Celery配置（任务队列）
    CELERY_BROKER_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    
    # AI平台配置
    SUPPORTED_PLATFORMS = [
        {'id': 'doubao', 'name': '豆包', 'url': 'https://www.doubao.com/chat'},
        {'id': 'deepseek', 'name': 'DeepSeek', 'url': 'https://chat.deepseek.com'},
        {'id': 'yuanbao', 'name': '元宝', 'url': 'https://yuanbao.tencent.com/chat'},
        {'id': 'kimi', 'name': 'Kimi', 'url': 'https://www.kimi.com'},
        {'id': 'qianwen', 'name': '千问', 'url': 'https://www.qianwen.com'},
        {'id': 'wenxin', 'name': '文心一言(wenxin)', 'url': 'https://wenxin.baidu.com'},
        {'id': 'yiyan', 'name': '文心一言(yiyan)', 'url': 'https://yiyan.baidu.com'},
        {'id': 'chatgpt', 'name': 'ChatGPT', 'url': 'https://chatgpt.com'}
    ]
