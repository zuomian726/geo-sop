"""
调度器模块
用于从现有数据库中读取引用链接，并调度采集和分析任务
"""
import json
import logging
import time
from typing import List, Dict
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import config
from models import ReferenceContent, ReferenceSentiment, get_db
from crawler import batch_crawl_references
from analyzer import batch_analyze_contents

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 连接现有数据库（只读，用于读取采集结果和任务信息）
existing_engine = create_engine(config.EXISTING_DATABASE_URI, echo=False)
SessionLocal = sessionmaker(bind=existing_engine)
ExistingBase = declarative_base()


# 读取现有数据库的模型
class CollectionResult(ExistingBase):
    """采集结果模型（只读）"""
    __tablename__ = 'collection_results'

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, nullable=False)
    question = Column(Text, nullable=False)
    platform = Column(String(50), nullable=False)
    answer = Column(Text)
    references = Column(Text)
    created_at = Column(DateTime)


class MonitorTask(ExistingBase):
    """监控任务模型（只读）"""
    __tablename__ = 'monitor_tasks'

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    brand_name = Column(String(100))
    brand_keywords = Column(Text, nullable=False)
    sentiment_config_id = Column(Integer)


class SentimentConfig(ExistingBase):
    """舆情配置模型（只读）"""
    __tablename__ = 'sentiment_configs'

    id = Column(Integer, primary_key=True)
    positive_words = Column(Text, default='[]')
    negative_words = Column(Text, default='[]')
    enable_ai_sentiment = Column(Boolean, default=False)
    ai_api_url = Column(String(500))
    ai_api_key = Column(String(255))
    ai_model_name = Column(String(100))
    ai_prompt = Column(Text)


class ReferenceScheduler:
    """引用链接调度器"""

    def __init__(self):
        self.running = False

    def get_pending_references(self, limit: int = None, platform: str = None, time_range: str = None, include_processed: bool = False) -> List[Dict]:
        """
        获取待处理的引用链接

        Args:
            limit: 限制数量
            platform: 平台筛选（None表示全部）
            time_range: 时间范围筛选（all/today/yesterday/week/month）
            include_processed: 是否包含已处理的引用（默认False，只返回未处理的）

        Returns:
            list: [{
                'collection_result_id': int,
                'task_id': int,
                'task_name': str,
                'question': str,
                'platform': str,
                'references': list
            }]
        """
        from datetime import datetime, timedelta
        
        db = SessionLocal()

        try:
            # 查询有引用链接的采集结果，并左关联任务表获取任务名称
            query = db.query(CollectionResult, MonitorTask.name.label('task_name')).outerjoin(
                MonitorTask, CollectionResult.task_id == MonitorTask.id
            ).filter(
                CollectionResult.references.isnot(None),
                CollectionResult.references != ''
            )

            # 平台筛选
            if platform and platform != '全部':
                query = query.filter(CollectionResult.platform == platform)

            # 时间范围筛选
            if time_range and time_range != 'all':
                now = datetime.now()
                if time_range == 'today':
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    query = query.filter(CollectionResult.created_at >= start_time)
                elif time_range == 'yesterday':
                    start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    query = query.filter(CollectionResult.created_at >= start_time, CollectionResult.created_at < end_time)
                elif time_range == 'week':
                    start_time = now - timedelta(days=7)
                    query = query.filter(CollectionResult.created_at >= start_time)
                elif time_range == 'month':
                    start_time = now - timedelta(days=30)
                    query = query.filter(CollectionResult.created_at >= start_time)

            # 排除已处理的（从新数据库中查询）
            if not include_processed:
                new_db = next(get_db())
                processed_ids = new_db.query(ReferenceContent.collection_result_id).distinct().all()
                new_db.close()
                if processed_ids:
                    processed_ids = [id[0] for id in processed_ids]
                    query = query.filter(~CollectionResult.id.in_(processed_ids))

            # 按时间倒序
            query = query.order_by(CollectionResult.created_at.desc())

            if limit:
                query = query.limit(limit)

            results = query.all()

            # 解析引用链接
            pending_references = []
            for result, task_name in results:
                try:
                    references = json.loads(result.references) if result.references else []
                    if references:
                        pending_references.append({
                            'collection_result_id': result.id,
                            'task_id': result.task_id,
                            'task_name': task_name,
                            'question': result.question,
                            'platform': result.platform,
                            'references': references
                        })
                except json.JSONDecodeError:
                    logger.warning(f"引用链接解析失败: {result.id}")
                    continue

            return pending_references

        finally:
            db.close()

    def get_all_collection_result_map(self) -> Dict[int, str]:
        """
        获取所有采集结果的 ID -> question 映射（从现有数据库直接获取）
        
        Returns:
            dict: {collection_result_id: question}
        """
        db = SessionLocal()
        
        try:
            results = db.query(CollectionResult.id, CollectionResult.question).all()
            return {cr.id: cr.question for cr in results}
        
        finally:
            db.close()

    def get_all_collection_result_map_with_task(self) -> Dict[int, tuple]:
        """
        获取所有采集结果的 ID -> (task_id, question) 映射（从现有数据库直接获取）
        
        Returns:
            dict: {collection_result_id: (task_id, question)}
        """
        db = SessionLocal()
        
        try:
            results = db.query(CollectionResult.id, CollectionResult.task_id, CollectionResult.question).all()
            return {cr.id: (cr.task_id, cr.question) for cr in results}
        
        finally:
            db.close()

    def get_pending_references_by_task(self, task_id: int, limit: int = None, time_range: str = None, include_processed: bool = True) -> List[Dict]:
        """
        根据任务ID获取待处理的引用链接

        Args:
            task_id: 任务ID
            limit: 限制数量
            time_range: 时间范围筛选（all/today/yesterday/week/month）
            include_processed: 是否包含已处理的引用（默认True，包含所有数据）

        Returns:
            list: [{
                'collection_result_id': int,
                'task_id': int,
                'task_name': str,
                'question': str,
                'platform': str,
                'references': list
            }]
        """
        from datetime import datetime, timedelta
        
        db = SessionLocal()

        try:
            # 查询指定任务的有引用链接的采集结果，并左关联任务表获取任务名称
            query = db.query(CollectionResult, MonitorTask.name.label('task_name')).outerjoin(
                MonitorTask, CollectionResult.task_id == MonitorTask.id
            ).filter(
                CollectionResult.task_id == task_id,
                CollectionResult.references.isnot(None),
                CollectionResult.references != ''
            )

            # 时间范围筛选
            if time_range and time_range != 'all':
                now = datetime.now()
                if time_range == 'today':
                    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    query = query.filter(CollectionResult.created_at >= start_time)
                elif time_range == 'yesterday':
                    start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    query = query.filter(CollectionResult.created_at >= start_time, CollectionResult.created_at < end_time)
                elif time_range == 'week':
                    start_time = now - timedelta(days=7)
                    query = query.filter(CollectionResult.created_at >= start_time)
                elif time_range == 'month':
                    start_time = now - timedelta(days=30)
                    query = query.filter(CollectionResult.created_at >= start_time)

            # 排除已处理的（从新数据库中查询）
            new_db = next(get_db())
            processed_ids = new_db.query(ReferenceContent.collection_result_id).distinct().all()
            new_db.close()
            if processed_ids:
                processed_ids = [id[0] for id in processed_ids]
                query = query.filter(~CollectionResult.id.in_(processed_ids))

            # 按时间倒序
            query = query.order_by(CollectionResult.created_at.desc())

            if limit:
                query = query.limit(limit)

            results = query.all()

            # 解析引用链接
            pending_references = []
            for result, task_name in results:
                try:
                    references = json.loads(result.references) if result.references else []
                    if references:
                        pending_references.append({
                            'collection_result_id': result.id,
                            'task_id': result.task_id,
                            'task_name': task_name,
                            'question': result.question,
                            'platform': result.platform,
                            'references': references
                        })
                except json.JSONDecodeError:
                    logger.warning(f"引用链接解析失败: {result.id}")
                    continue

            return pending_references

        finally:
            db.close()

    def get_sentiment_config(self, task_id: int) -> Dict:
        """
        获取任务的舆情配置

        Args:
            task_id: 任务ID

        Returns:
            dict: 舆情配置
        """
        db = SessionLocal()

        try:
            # 查询任务
            task = db.query(MonitorTask).filter_by(id=task_id).first()
            if not task or not task.sentiment_config_id:
                return None

            # 查询舆情配置
            sentiment_config = db.query(SentimentConfig).filter_by(id=task.sentiment_config_id).first()
            if not sentiment_config:
                return None

            return {
                'positive_words': json.loads(sentiment_config.positive_words) if sentiment_config.positive_words else [],
                'negative_words': json.loads(sentiment_config.negative_words) if sentiment_config.negative_words else [],
                'enable_ai_sentiment': sentiment_config.enable_ai_sentiment,
                'ai_config': {
                    'api_url': sentiment_config.ai_api_url,
                    'api_key': sentiment_config.ai_api_key,
                    'model_name': sentiment_config.ai_model_name,
                    'prompt': sentiment_config.ai_prompt
                }
            }

        finally:
            db.close()

    def process_references(self, pending_references: List[Dict]):
        """
        处理引用链接

        Args:
            pending_references: 待处理的引用链接列表
        """
        for item in pending_references:
            collection_result_id = item['collection_result_id']
            task_id = item['task_id']
            references = item['references']

            logger.info(f"开始处理引用链接: 采集结果ID={collection_result_id}, 任务ID={task_id}, 引用数量={len(references)}")

            try:
                # 提取URL列表（处理字典或字符串两种格式）
                urls = []
                for ref in references:
                    if isinstance(ref, dict) and 'url' in ref:
                        urls.append(ref['url'])
                    elif isinstance(ref, str):
                        urls.append(ref)

                # 1. 采集引用链接内容
                logger.info(f"开始采集引用链接内容...")
                content_records = batch_crawl_references(collection_result_id, urls)

                # 2. 获取舆情配置
                sentiment_config = self.get_sentiment_config(task_id)
                logger.info(f"舆情配置: {sentiment_config}")

                # 3. 分析舆情
                if content_records:
                    content_ids = [record.id for record in content_records]
                    logger.info(f"开始分析舆情: {len(content_ids)} 条内容")

                    sentiment_records = batch_analyze_contents(content_ids, sentiment_config)

                    # 统计结果
                    positive_count = sum(1 for s in sentiment_records if s.sentiment == 'positive')
                    negative_count = sum(1 for s in sentiment_records if s.sentiment == 'negative')
                    neutral_count = sum(1 for s in sentiment_records if s.sentiment == 'neutral')

                    logger.info(f"舆情分析完成: 正向={positive_count}, 负向={negative_count}, 中性={neutral_count}")

                logger.info(f"引用链接处理完成: {collection_result_id}")

            except Exception as e:
                logger.error(f"处理引用链接失败: {collection_result_id} - {str(e)}")

            # 避免请求过快
            time.sleep(2)

    def run_once(self, limit: int = None):
        """
        运行一次调度

        Args:
            limit: 处理数量限制
        """
        logger.info("开始调度...")

        # 获取待处理的引用链接
        pending_references = self.get_pending_references(limit)

        if not pending_references:
            logger.info("没有待处理的引用链接")
            return

        logger.info(f"找到 {len(pending_references)} 条待处理的引用链接")

        # 处理引用链接
        self.process_references(pending_references)

        logger.info("调度完成")

    def run_loop(self, interval: int = None):
        """
        循环运行调度

        Args:
            interval: 调度间隔（秒）
        """
        if interval is None:
            interval = config.SENTIMENT_INTERVAL

        self.running = True
        logger.info(f"开始循环调度，间隔: {interval} 秒")

        while self.running:
            try:
                self.run_once(limit=config.SENTIMENT_BATCH_SIZE)
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("收到中断信号，停止调度")
                break
            except Exception as e:
                logger.error(f"调度出错: {str(e)}")
                time.sleep(interval)

        self.running = False
        logger.info("调度已停止")

    def stop(self):
        """停止调度"""
        self.running = False
        logger.info("正在停止调度...")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='引用链接舆情分析调度器')
    parser.add_argument('--once', action='store_true', help='只运行一次')
    parser.add_argument('--interval', type=int, default=config.SENTIMENT_INTERVAL, help='调度间隔（秒）')
    parser.add_argument('--limit', type=int, default=config.SENTIMENT_BATCH_SIZE, help='每次处理数量')

    args = parser.parse_args()

    # 初始化数据库
    from models import init_db
    init_db()

    # 创建调度器
    scheduler = ReferenceScheduler()

    if args.once:
        # 只运行一次
        scheduler.run_once(limit=args.limit)
    else:
        # 循环运行
        try:
            scheduler.run_loop(interval=args.interval)
        except KeyboardInterrupt:
            scheduler.stop()


if __name__ == '__main__':
    main()