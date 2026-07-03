"""
数据库模型 - 引用链接舆情分析
"""
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone, timedelta
import json
import config

# 创建数据库引擎（使用现有数据库）
engine = create_engine(config.DATABASE_URI, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def now_cst():
    """获取当前北京时间"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)


class ReferenceContent(Base):
    """引用链接内容模型"""
    __tablename__ = 'reference_contents'

    id = Column(Integer, primary_key=True)
    collection_result_id = Column(Integer, nullable=False, index=True)  # 关联的采集结果ID
    url = Column(String(500), nullable=False)  # 引用链接URL
    title = Column(String(255))  # 网页标题
    content = Column(Text)  # 网页内容（纯文本）
    html_content = Column(Text)  # 网页HTML内容（可选）

    # 采集状态
    crawl_status = Column(String(20), default='pending')  # pending, success, failed
    crawl_error = Column(Text)  # 采集错误信息

    # 时间戳
    created_at = Column(DateTime, default=now_cst)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'collection_result_id': self.collection_result_id,
            'url': self.url,
            'title': self.title,
            'content': self.content,
            'crawl_status': self.crawl_status,
            'crawl_error': self.crawl_error,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }


class ReferenceSentiment(Base):
    """引用链接舆情分析结果模型"""
    __tablename__ = 'reference_sentiments'

    id = Column(Integer, primary_key=True)
    reference_content_id = Column(Integer, nullable=False, index=True)  # 关联的内容ID
    collection_result_id = Column(Integer, nullable=False, index=True)  # 关联的采集结果ID

    # 舆情分析结果
    sentiment = Column(String(20))  # positive, negative, neutral
    sentiment_score = Column(Integer)  # 情感分数（0-100）
    keywords = Column(Text)  # 关键词（JSON数组）

    # 分析详情
    analysis_details = Column(Text)  # 分析详情（JSON对象）

    # 分析状态
    analysis_status = Column(String(20), default='pending')  # pending, success, failed
    analysis_error = Column(Text)  # 分析错误信息

    # 时间戳
    created_at = Column(DateTime, default=now_cst)
    updated_at = Column(DateTime, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'reference_content_id': self.reference_content_id,
            'collection_result_id': self.collection_result_id,
            'sentiment': self.sentiment,
            'sentiment_score': self.sentiment_score,
            'keywords': json.loads(self.keywords) if self.keywords else [],
            'analysis_details': json.loads(self.analysis_details) if self.analysis_details else {},
            'analysis_status': self.analysis_status,
            'analysis_error': self.analysis_error,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }


# 创建表（如果不存在）
def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


# 数据库会话管理
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()