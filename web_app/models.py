"""
数据库模型
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
import json

db = SQLAlchemy()

def now_cst():
    """获取当前北京时间"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)


class User(UserMixin, db.Model):
    """用户模型"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_cst)
    
    # 关系
    tasks = db.relationship('MonitorTask', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }


class GeoManuscript(db.Model):
    """GEO稿件模型"""
    __tablename__ = 'geo_manuscripts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('monitor_tasks.id'), nullable=True) # 关联的任务（旧字段）
    task_ids = db.Column(db.Text, nullable=True) # 关联的任务ID列表（JSON数组，新字段）
    
    title = db.Column(db.String(255), nullable=False) # 稿件标题/备注
    url = db.Column(db.Text, nullable=False) # 稿件URL或关键特征
    
    created_at = db.Column(db.DateTime, default=now_cst)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'task_id': self.task_id,
            'task_ids': json.loads(self.task_ids) if self.task_ids else [],
            'title': self.title,
            'url': self.url,
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }


class MonitorTask(db.Model):
    """监控任务模型"""
    __tablename__ = 'monitor_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # 任务基本信息
    name = db.Column(db.String(200), nullable=False)  # 任务名称
    brand_name = db.Column(db.String(100))  # 品牌名称
    brand_keywords = db.Column(db.Text, nullable=False)  # 品牌关键词（JSON数组）
    competitor_brands = db.Column(db.Text)  # 竞品品牌（JSON数组，选填）
    
    # 监控配置
    questions = db.Column(db.Text, nullable=False)  # 监控问题列表（JSON数组）
    platforms = db.Column(db.Text, nullable=False)  # 选择的AI平台（JSON数组）
    screenshot_config = db.Column(db.Text)  # 截图配置（JSON对象：{platform_id: boolean}）
    collection_interval = db.Column(db.Integer, default=20)  # 采集间隔（秒）
    max_parallel_platforms = db.Column(db.Integer, default=3)  # 最大并行平台数（1=串行，>1=并行）
    
    # 调度配置
    schedule_type = db.Column(db.String(20), default='manual')  # manual, daily, weekly
    schedule_config = db.Column(db.Text)  # 调度配置（JSON）
    schedule_enabled = db.Column(db.Boolean, default=False)  # 是否启用自动调度
    
    # 舆情配置（任务级别）
    sentiment_config_id = db.Column(db.Integer, db.ForeignKey('sentiment_configs.id'), nullable=True)
    
    # 状态
    status = db.Column(db.String(20), default='pending')  # pending, running, paused, completed, failed, stopped
    control_command = db.Column(db.String(20)) # 控制命令: pause, resume, stop
    last_run_at = db.Column(db.DateTime)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=now_cst)
    updated_at = db.Column(db.DateTime, default=now_cst, onupdate=now_cst)
    
    # 关系
    results = db.relationship('CollectionResult', backref='task', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'brand_name': self.brand_name,
            'brand_keywords': json.loads(self.brand_keywords) if self.brand_keywords else [],
            'competitor_brands': json.loads(self.competitor_brands) if self.competitor_brands else [],
            'questions': json.loads(self.questions) if self.questions else [],
            'platforms': json.loads(self.platforms) if self.platforms else [],
            'screenshot_config': json.loads(self.screenshot_config) if self.screenshot_config else {},
            'collection_interval': self.collection_interval,
            'max_parallel_platforms': self.max_parallel_platforms,
            'schedule_type': self.schedule_type,
            'schedule_config': json.loads(self.schedule_config) if self.schedule_config else {},
            'schedule_enabled': self.schedule_enabled,
            'sentiment_config_id': self.sentiment_config_id,
            'status': self.status,
            'last_run_at': self.last_run_at.strftime('%Y-%m-%dT%H:%M:%S+08:00') if self.last_run_at else None,
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'updated_at': self.updated_at.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }


class CollectionResult(db.Model):
    """采集结果模型"""
    __tablename__ = 'collection_results'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('monitor_tasks.id'), nullable=False)
    
    # 采集信息
    question = db.Column(db.Text, nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    
    # AI回答
    answer = db.Column(db.Text)
    
    # 引用参考（JSON数组）
    references = db.Column(db.Text)
    
    # 截图路径
    screenshot_path = db.Column(db.String(500))
    
    # 品牌词曝光
    has_brand_exposure = db.Column(db.Boolean, default=False)
    exposed_keywords = db.Column(db.Text)  # 曝光的关键词（JSON数组）
    
    # 智能舆情分析结果（JSON格式）
    ai_sentiment_result = db.Column(db.Text)
    ai_sentiment_updated_at = db.Column(db.DateTime)
    
    # 排名信息（JSON格式）- 解析AI回答中的排名
    rankings = db.Column(db.Text)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=now_cst)
    
    def to_dict(self):
        import os
        
        # 处理截图路径：将绝对路径转换为 Web 可访问的相对路径
        screenshot_url = None
        if self.screenshot_path:
            # 统一用正斜杠，兼容 Windows 反斜杠
            path = self.screenshot_path.replace(os.sep, '/').replace('\\', '/')
            # 匹配 web_app/answers/（web_app 采集）或 answers/（main.py 采集）
            # 注意：路径中可能包含父目录，所以用 rfind 从末尾查找
            for marker in ['/web_app/answers/', '/answers/']:
                idx = path.rfind(marker)
                if idx != -1:
                    # 从 marker 开头开始截取（去掉前面的 /）
                    screenshot_url = path[idx + 1:]
                    break
        
        return {
            'id': self.id,
            'task_id': self.task_id,
            'question': self.question,
            'platform': self.platform,
            'answer': self.answer,
            'references': json.loads(self.references) if self.references else [],
            'screenshot_path': self.screenshot_path,  # 原始路径
            'screenshot_url': screenshot_url,  # Web访问URL
            'has_brand_exposure': self.has_brand_exposure,
            'exposed_keywords': json.loads(self.exposed_keywords) if self.exposed_keywords else [],
            'rankings': json.loads(self.rankings) if self.rankings else [],
            'ai_sentiment_result': json.loads(self.ai_sentiment_result) if self.ai_sentiment_result else None,
            'ai_sentiment_updated_at': self.ai_sentiment_updated_at.strftime('%Y-%m-%dT%H:%M:%S+08:00') if self.ai_sentiment_updated_at else None,
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }


class SentimentConfig(db.Model):
    """舆情配置模型"""
    __tablename__ = 'sentiment_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # 配置名称
    name = db.Column(db.String(100), nullable=False)
    
    # 正向关键词（JSON数组）
    positive_words = db.Column(db.Text, default='[]')
    
    # 负向关键词（JSON数组）
    negative_words = db.Column(db.Text, default='[]')
    
    # 是否启用智能舆情分析
    enable_ai_sentiment = db.Column(db.Boolean, default=False)
    
    # AI平台类型
    ai_platform = db.Column(db.String(50))
    
    # AI平台API配置
    ai_api_url = db.Column(db.String(500))
    ai_api_key = db.Column(db.String(255))
    ai_model_name = db.Column(db.String(100))
    
    # AI分析Prompt
    ai_prompt = db.Column(db.Text)
    
    # 是否为默认配置
    is_default = db.Column(db.Boolean, default=False)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=now_cst)
    updated_at = db.Column(db.DateTime, default=now_cst, onupdate=now_cst)
    
    # 关系
    tasks = db.relationship('MonitorTask', backref='sentiment_config', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'positive_words': json.loads(self.positive_words) if self.positive_words else [],
            'negative_words': json.loads(self.negative_words) if self.negative_words else [],
            'enable_ai_sentiment': self.enable_ai_sentiment,
            'ai_platform': self.ai_platform,
            'ai_api_url': self.ai_api_url,
            'ai_api_key': self.ai_api_key,
            'ai_model_name': self.ai_model_name,
            'ai_prompt': self.ai_prompt,
            'is_default': self.is_default,
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%S+08:00'),
            'updated_at': self.updated_at.strftime('%Y-%m-%dT%H:%M:%S+08:00')
        }
