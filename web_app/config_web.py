"""
Web应用配置
"""
import os
from datetime import timedelta


def _startup_trace(message):
    if os.environ.get('GEO_DEBUG_BOOT') != '1':
        return
    try:
        path = os.environ.get('GEO_BOOT_LOG_PATH') or os.path.join(os.environ.get('TEMP') or '/tmp', 'geo_sop_boot.log')
        with open(path, 'a', encoding='utf-8') as handle:
            handle.write(f"config: {message}\n")
    except Exception:
        pass


_startup_trace('module loading')
from local_paths import app_data_dir, instance_dir, database_path, answers_dir
from platform_catalog import supported_platforms
_startup_trace('local path helpers imported')

class Config:
    """基础配置"""
    
    DESKTOP_MODE = os.environ.get('GEO_DESKTOP_MODE') == '1'
    _startup_trace(f'desktop mode={DESKTOP_MODE}')

    # 获取当前文件所在目录（web_app目录）
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = app_data_dir() if DESKTOP_MODE else BASE_DIR
    _startup_trace(f'data directory={DATA_DIR}')
    
    # 实例目录（存放数据库等数据文件）
    INSTANCE_DIR = instance_dir() if DESKTOP_MODE else os.path.join(BASE_DIR, 'instance')
    os.makedirs(INSTANCE_DIR, exist_ok=True)  # 确保目录存在
    _startup_trace(f'instance directory={INSTANCE_DIR}')
    
    # 密钥
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # 数据库 - 使用绝对路径确保在任何位置启动都能找到正确的数据库文件
    DATABASE_PATH = database_path() if DESKTOP_MODE else os.path.join(INSTANCE_DIR, 'ai_monitor.db')
    _startup_trace(f'database path={DATABASE_PATH}')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{DATABASE_PATH}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ANSWERS_DIR = os.environ.get('GEO_ANSWERS_DIR') or (answers_dir() if DESKTOP_MODE else os.path.join(BASE_DIR, 'answers'))
    _startup_trace(f'answers directory={ANSWERS_DIR}')
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
    SUPPORTED_PLATFORMS = supported_platforms()
