"""
舆情分析模块
用于分析引用链接内容的舆情
"""
import re
import logging
import json
from typing import List, Dict
import config
from models import ReferenceContent, ReferenceSentiment, get_db

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


class SentimentAnalyzer:
    """舆情分析器"""

    def __init__(self, positive_words: List[str] = None, negative_words: List[str] = None):
        """
        初始化分析器

        Args:
            positive_words: 正向关键词列表
            negative_words: 负向关键词列表
        """
        self.positive_words = positive_words or []
        self.negative_words = negative_words or []

        # 编译正则表达式（提高匹配效率）
        self.positive_patterns = [re.compile(word, re.IGNORECASE) for word in self.positive_words]
        self.negative_patterns = [re.compile(word, re.IGNORECASE) for word in self.negative_words]

    def analyze(self, content: str, title: str = None) -> Dict:
        """
        分析内容舆情

        Args:
            content: 文本内容
            title: 标题（可选）

        Returns:
            dict: {
                'sentiment': str,  # positive, negative, neutral
                'sentiment_score': int,  # 0-100
                'keywords': list,  # 匹配到的关键词
                'positive_count': int,  # 正向词出现次数
                'negative_count': int,  # 负向词出现次数
                'details': dict  # 详细分析
            }
        """
        # 合并标题和内容
        full_text = f"{title or ''} {content}"

        # 统计关键词出现次数
        positive_matches = []
        negative_matches = []

        for pattern in self.positive_patterns:
            matches = pattern.findall(full_text)
            if matches:
                positive_matches.extend(matches)

        for pattern in self.negative_patterns:
            matches = pattern.findall(full_text)
            if matches:
                negative_matches.extend(matches)

        positive_count = len(positive_matches)
        negative_count = len(negative_matches)

        # 计算情感分数
        total_count = positive_count + negative_count
        if total_count == 0:
            sentiment = 'neutral'
            sentiment_score = 50
        else:
            positive_ratio = positive_count / total_count
            sentiment_score = int(positive_ratio * 100)

            if sentiment_score >= 60:
                sentiment = 'positive'
            elif sentiment_score <= 40:
                sentiment = 'negative'
            else:
                sentiment = 'neutral'

        # 提取匹配到的关键词
        keywords = list(set(positive_matches + negative_matches))

        # 详细分析
        details = {
            'positive_count': positive_count,
            'negative_count': negative_count,
            'positive_words': list(set(positive_matches)),
            'negative_words': list(set(negative_matches)),
            'total_keywords': total_count,
            'text_length': len(content),
            'has_title': bool(title)
        }

        return {
            'sentiment': sentiment,
            'sentiment_score': sentiment_score,
            'keywords': keywords,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'details': details
        }

    def analyze_with_ai(self, content: str, title: str = None, ai_config: Dict = None) -> Dict:
        """
        使用AI进行智能舆情分析

        Args:
            content: 文本内容
            title: 标题（可选）
            ai_config: AI配置 {
                'platform': str,  # AI平台类型
                'api_url': str,  # API地址
                'api_key': str,  # API密钥
                'model_name': str,  # 模型名称
                'prompt': str  # 分析提示词
            }

        Returns:
            dict: 分析结果
        """
        # TODO: 实现AI分析逻辑
        # 这里可以集成OpenAI、通义千问等AI平台
        logger.info("AI分析功能待实现")

        # 暂时返回基础分析结果
        return self.analyze(content, title)


def analyze_reference_content(reference_content_id: int, sentiment_config: Dict = None) -> ReferenceSentiment:
    """
    分析引用链接内容舆情并保存到数据库

    Args:
        reference_content_id: 引用内容ID
        sentiment_config: 舆情配置 {
            'positive_words': list,
            'negative_words': list,
            'enable_ai_sentiment': bool,
            'ai_config': dict
        }

    Returns:
        ReferenceSentiment: 保存的分析结果记录
    """
    db = next(get_db())

    try:
        # 获取引用内容
        content_record = db.query(ReferenceContent).filter_by(id=reference_content_id).first()
        if not content_record:
            raise ValueError(f"引用内容不存在: {reference_content_id}")

        # 检查是否已存在分析结果
        existing = db.query(ReferenceSentiment).filter_by(
            reference_content_id=reference_content_id
        ).first()

        if existing:
            logger.info(f"舆情分析已存在: {reference_content_id}")
            return existing

        # 创建新记录
        sentiment_record = ReferenceSentiment(
            reference_content_id=reference_content_id,
            collection_result_id=content_record.collection_result_id,
            analysis_status='pending'
        )
        db.add(sentiment_record)
        db.commit()
        db.refresh(sentiment_record)

        # 提取配置
        positive_words = sentiment_config.get('positive_words', []) if sentiment_config else []
        negative_words = sentiment_config.get('negative_words', []) if sentiment_config else []
        enable_ai = sentiment_config.get('enable_ai_sentiment', False) if sentiment_config else False
        ai_config = sentiment_config.get('ai_config', {}) if sentiment_config else {}

        # 创建分析器
        analyzer = SentimentAnalyzer(positive_words, negative_words)

        # 执行分析
        if enable_ai and ai_config:
            result = analyzer.analyze_with_ai(
                content_record.content or "",
                content_record.title,
                ai_config
            )
        else:
            result = analyzer.analyze(
                content_record.content or "",
                content_record.title
            )

        # 保存结果
        sentiment_record.sentiment = result['sentiment']
        sentiment_record.sentiment_score = result['sentiment_score']
        sentiment_record.keywords = json.dumps(result['keywords'], ensure_ascii=False)
        sentiment_record.analysis_details = json.dumps(result['details'], ensure_ascii=False)
        sentiment_record.analysis_status = 'success'

        db.commit()
        logger.info(f"舆情分析成功: {reference_content_id} - {result['sentiment']}")

        return sentiment_record

    except Exception as e:
        db.rollback()
        logger.error(f"舆情分析失败: {reference_content_id} - {str(e)}")

        # 更新错误状态
        if 'sentiment_record' in locals():
            sentiment_record.analysis_status = 'failed'
            sentiment_record.analysis_error = str(e)
            db.commit()

        raise
    finally:
        db.close()


def batch_analyze_contents(content_ids: List[int], sentiment_config: Dict = None) -> List[ReferenceSentiment]:
    """
    批量分析引用内容舆情

    Args:
        content_ids: 引用内容ID列表
        sentiment_config: 舆情配置

    Returns:
        list: 分析结果记录列表
    """
    results = []
    for content_id in content_ids:
        try:
            sentiment_record = analyze_reference_content(content_id, sentiment_config)
            results.append(sentiment_record)
        except Exception as e:
            logger.error(f"批量分析失败: {content_id} - {str(e)}")

    return results


def get_sentiment_statistics(collection_result_id: int = None) -> Dict:
    """
    获取舆情统计信息

    Args:
        collection_result_id: 采集结果ID（可选，不传则统计全部）

    Returns:
        dict: 统计信息 {
            'total': int,
            'positive': int,
            'negative': int,
            'neutral': int,
            'average_score': float
        }
    """
    db = next(get_db())

    try:
        query = db.query(ReferenceSentiment).filter_by(analysis_status='success')

        if collection_result_id:
            query = query.filter_by(collection_result_id=collection_result_id)

        sentiments = query.all()

        total = len(sentiments)
        positive = sum(1 for s in sentiments if s.sentiment == 'positive')
        negative = sum(1 for s in sentiments if s.sentiment == 'negative')
        neutral = sum(1 for s in sentiments if s.sentiment == 'neutral')

        average_score = 0
        if total > 0:
            average_score = sum(s.sentiment_score for s in sentiments) / total

        return {
            'total': total,
            'positive': positive,
            'negative': negative,
            'neutral': neutral,
            'average_score': round(average_score, 2)
        }

    finally:
        db.close()