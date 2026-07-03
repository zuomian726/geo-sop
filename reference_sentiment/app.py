"""
引用参考链接舆情分析 - 前端Web应用
"""
from flask import Flask, render_template, jsonify, request
import json
import logging
from datetime import datetime
import config
from models import ReferenceContent, ReferenceSentiment, init_db, get_db
from crawler import crawl_reference_url, batch_crawl_references, WebCrawler
from analyzer import analyze_reference_content, get_sentiment_statistics
from scheduler import ReferenceScheduler

# 初始化Flask应用
app = Flask(__name__)

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

# 初始化数据库
init_db()

# 调度器实例
scheduler = ReferenceScheduler()


@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/api/pending_references')
def get_pending_references():
    """获取待处理的引用链接（支持分页，按问题分组，支持任务和问题筛选）"""
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        platform = request.args.get('platform')
        task_id = request.args.get('task_id')
        question = request.args.get('question')
        time_range = request.args.get('time_range')
        
        # 先获取所有数据（不分页，包含已处理的数据）
        if task_id and task_id != '全部':
            all_pending = scheduler.get_pending_references_by_task(task_id=int(task_id), limit=None, time_range=time_range, include_processed=True)
        else:
            all_pending = scheduler.get_pending_references(limit=None, platform=platform, time_range=time_range, include_processed=True)
        
        # 问题筛选
        if question and question != '全部':
            all_pending = [item for item in all_pending if item['question'] == question]
        
        # 按问题分组（基于唯一URL）
        grouped = {}
        for item in all_pending:
            question = item['question']
            if question not in grouped:
                grouped[question] = {
                    'question': question,
                    'platforms': {},
                    'all_unique_urls': set()  # 问题级别的所有唯一URL
                }
            
            # 按平台统计（基于唯一URL）
            pf = item['platform']
            if pf not in grouped[question]['platforms']:
                grouped[question]['platforms'][pf] = {
                    'total_count': 0,
                    'unique_urls': set(),  # 使用set存储该平台的唯一URL
                    'collection_result_ids': []
                }
            
            # 将该采集结果的所有URL加入集合（自动去重）
            for ref in item['references']:
                url = ref if isinstance(ref, str) else ref.get('url', '')
                if url:
                    grouped[question]['platforms'][pf]['unique_urls'].add(url)
                    grouped[question]['all_unique_urls'].add(url)  # 同时加入问题级别的集合
            
            grouped[question]['platforms'][pf]['collection_result_ids'].append(item['collection_result_id'])
        
        # 计算每个平台的唯一URL数量，并添加问题级别的总数
        for question_data in grouped.values():
            question_data['total_count'] = len(question_data['all_unique_urls'])  # 问题级别的唯一URL总数
            del question_data['all_unique_urls']  # 移除临时集合
            for platform in question_data['platforms'].values():
                platform['total_count'] = len(platform['unique_urls'])
                # 将unique_urls转换为列表，保留给前端显示
                platform['unique_urls'] = list(platform['unique_urls'])
        
        # 转换为列表并排序
        grouped_list = list(grouped.values())
        
        # 计算总数（按问题数量）
        total = len(grouped_list)
        
        # 分页处理
        offset = (page - 1) * page_size
        pending = grouped_list[offset:offset + page_size]
        
        return jsonify({
            'success': True,
            'data': pending,
            'count': len(pending),
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size
        })
    except Exception as e:
        logger.error(f"获取待处理引用链接失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/pending_questions')
def get_pending_questions():
    """获取待处理引用的问题列表（用于筛选）"""
    try:
        task_id = request.args.get('task_id')
        
        # 获取待处理引用数据
        if task_id and task_id != '全部':
            all_pending = scheduler.get_pending_references_by_task(task_id=int(task_id), limit=None)
        else:
            all_pending = scheduler.get_pending_references(limit=None)
        
        # 提取所有问题
        questions = sorted(list(set([item['question'] for item in all_pending])))
        
        return jsonify({
            'success': True,
            'data': questions
        })
    except Exception as e:
        logger.error(f"获取待处理问题列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reference_details')
def get_reference_details():
    """获取引用链接详情列表"""
    try:
        collection_result_id = request.args.get('collection_result_id')
        
        if not collection_result_id:
            return jsonify({'success': False, 'error': '缺少参数'}), 400
        
        pending = scheduler.get_pending_references()
        item = None
        for p in pending:
            if p['collection_result_id'] == int(collection_result_id):
                item = p
                break
        
        if not item:
            return jsonify({'success': False, 'error': '未找到记录'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'collection_result_id': item['collection_result_id'],
                'task_id': item['task_id'],
                'question': item['question'],
                'platform': item['platform'],
                'references': item['references']
            }
        })
    except Exception as e:
        logger.error(f"获取引用链接详情失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks')
def get_tasks():
    """获取所有监控任务列表"""
    try:
        from scheduler import SessionLocal, MonitorTask
        db = SessionLocal()
        tasks = db.query(MonitorTask).all()
        result = [{'id': task.id, 'name': task.name} for task in tasks]
        db.close()
        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/platforms')
def get_platforms():
    """获取所有平台列表"""
    try:
        platforms = ['全部', 'doubao', 'deepseek', 'yuanbao', 'kimi', 'qianwen', 'wenxin', 'chatgpt']
        return jsonify({
            'success': True,
            'data': platforms
        })
    except Exception as e:
        logger.error(f"获取平台列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/crawled_contents')
def get_crawled_contents():
    """获取已采集的内容（支持分页、任务筛选、问题筛选）"""
    db = None
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        status = request.args.get('status', 'success')  # 默认只返回成功采集的
        task_id = request.args.get('task_id')
        question = request.args.get('question')
        
        db = next(get_db())
        query = db.query(ReferenceContent).order_by(ReferenceContent.created_at.desc())
        
        if status:
            query = query.filter(ReferenceContent.crawl_status == status)
        
        # 获取 collection_result_id -> (task_id, question) 的映射
        cr_id_map = scheduler.get_all_collection_result_map_with_task()
        
        # 如果有任务筛选或问题筛选，需要先获取符合条件的 collection_result_ids
        filtered_cr_ids = None
        if task_id and task_id != '全部':
            filtered_cr_ids = [cr_id for cr_id, (tid, q) in cr_id_map.items() if tid == int(task_id)]
        if question and question != '全部':
            if filtered_cr_ids is None:
                filtered_cr_ids = [cr_id for cr_id, (tid, q) in cr_id_map.items() if q == question]
            else:
                filtered_cr_ids = [cr_id for cr_id in filtered_cr_ids if cr_id_map[cr_id][1] == question]
        
        if filtered_cr_ids:
            query = query.filter(ReferenceContent.collection_result_id.in_(filtered_cr_ids))
        
        # 计算总数
        total = query.count()
        
        # 分页
        offset = (page - 1) * page_size
        contents = query.offset(offset).limit(page_size).all()
        
        result = [content.to_dict() for content in contents]
        
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result),
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size
        })
    except Exception as e:
        logger.error(f"获取已采集内容失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/crawled_questions')
def get_crawled_questions():
    """获取已采集内容的问题列表（用于筛选）"""
    try:
        task_id = request.args.get('task_id')
        
        # 获取 collection_result_id -> (task_id, question) 的映射
        cr_id_map = scheduler.get_all_collection_result_map_with_task()
        
        # 获取所有已采集内容的 collection_result_ids
        db = next(get_db())
        cr_ids_with_content = set([row[0] for row in db.query(ReferenceContent.collection_result_id).distinct().all()])
        db.close()
        
        # 筛选出有内容的问题
        questions = set()
        for cr_id in cr_ids_with_content:
            if cr_id in cr_id_map:
                tid, q = cr_id_map[cr_id]
                if task_id and task_id != '全部':
                    if tid == int(task_id):
                        questions.add(q)
                else:
                    questions.add(q)
        
        return jsonify({
            'success': True,
            'data': sorted(list(questions))
        })
    except Exception as e:
        logger.error(f"获取已采集问题列表失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sentiment_results')
def get_sentiment_results():
    """获取舆情分析结果（支持分页和情感筛选）"""
    db = None
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        sentiment = request.args.get('sentiment')
        
        db = next(get_db())
        query = db.query(ReferenceSentiment).order_by(ReferenceSentiment.created_at.desc())
        
        if sentiment:
            query = query.filter_by(sentiment=sentiment)
        
        # 计算总数
        total = query.count()
        
        # 分页
        offset = (page - 1) * page_size
        results = query.offset(offset).limit(page_size).all()
        
        # 获取URL和标题信息
        result_list = []
        for res in results:
            res_dict = res.to_dict()
            # 获取关联的内容信息
            content = db.query(ReferenceContent).filter_by(id=res.reference_content_id).first()
            if content:
                res_dict['url'] = content.url
                res_dict['title'] = content.title
            result_list.append(res_dict)
        
        return jsonify({
            'success': True,
            'data': result_list,
            'count': len(result_list),
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size
        })
    except Exception as e:
        logger.error(f"获取舆情分析结果失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/stats')
def get_stats():
    """获取数据看板统计信息"""
    db = None
    try:
        db = next(get_db())
        
        # 获取所有成功采集的URL（去重）
        crawled_results = db.query(ReferenceContent.collection_result_id, ReferenceContent.url).filter(
            ReferenceContent.crawl_status == 'success'
        ).distinct().all()
        
        # 构建已采集URL集合和按collection_result_id分组的已采集URL
        crawled_urls = set()
        cr_id_to_crawled_urls = {}
        for cr_id, url in crawled_results:
            crawled_urls.add(url)
            if cr_id not in cr_id_to_crawled_urls:
                cr_id_to_crawled_urls[cr_id] = set()
            cr_id_to_crawled_urls[cr_id].add(url)
        
        # 所有已采集内容的总数（基于唯一URL）
        total_crawled_count = len(crawled_urls)
        
        # 获取待处理引用
        all_references = scheduler.get_pending_references(limit=None, include_processed=True)
        
        # 统计待处理列表中的唯一URL及其所属的collection_result_id
        all_unique_urls = set()
        cr_id_to_all_urls = {}
        
        for item in all_references:
            cr_id = item['collection_result_id']
            refs = item['references']
            
            if cr_id not in cr_id_to_all_urls:
                cr_id_to_all_urls[cr_id] = set()
            
            for ref in refs:
                if isinstance(ref, dict) and 'url' in ref:
                    url = ref['url']
                    all_unique_urls.add(url)
                    cr_id_to_all_urls[cr_id].add(url)
                elif isinstance(ref, str):
                    all_unique_urls.add(ref)
                    cr_id_to_all_urls[cr_id].add(ref)
        
        # 计算待处理列表中的已采集数（只统计在待处理列表中的已采集URL）
        crawled_in_pending = 0
        for cr_id, url_set in cr_id_to_all_urls.items():
            if cr_id in cr_id_to_crawled_urls:
                crawled_in_pending += len(url_set & cr_id_to_crawled_urls[cr_id])
        
        # 待处理数量 = 待处理列表中的总URL数 - 待处理列表中已采集的URL数
        pending_count = len(all_unique_urls) - crawled_in_pending
        
        # 舆情统计
        positive_count = db.query(ReferenceSentiment).filter(ReferenceSentiment.sentiment == 'positive').count()
        negative_count = db.query(ReferenceSentiment).filter(ReferenceSentiment.sentiment == 'negative').count()
        neutral_count = db.query(ReferenceSentiment).filter(ReferenceSentiment.sentiment == 'neutral').count()
        
        return jsonify({
            'success': True,
            'pending_count': pending_count,
            'crawled_count': total_crawled_count,  # 显示所有已采集内容的总数
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count
        })
    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/sentiment_stats')
def get_sentiment_stats():
    """获取舆情统计信息"""
    try:
        collection_result_id = request.args.get('collection_result_id')
        stats = get_sentiment_statistics(collection_result_id)
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        logger.error(f"获取舆情统计失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/crawl', methods=['POST'])
def crawl_single():
    """采集单个引用链接"""
    try:
        data = request.get_json()
        collection_result_id = data.get('collection_result_id')
        url = data.get('url')
        
        if not collection_result_id or not url:
            return jsonify({'success': False, 'error': '缺少参数'}), 400
        
        content = crawl_reference_url(collection_result_id, url)
        
        return jsonify({
            'success': True,
            'data': content.to_dict()
        })
    except Exception as e:
        logger.error(f"采集引用链接失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/retry_crawl', methods=['POST'])
def retry_crawl():
    """重新采集已采集的内容"""
    db = None
    try:
        data = request.get_json()
        content_id = data.get('content_id')
        
        if not content_id:
            return jsonify({'success': False, 'error': '缺少参数'}), 400
        
        db = next(get_db())
        content = db.query(ReferenceContent).filter_by(id=content_id).first()
        
        if not content:
            return jsonify({'success': False, 'error': '内容不存在'}), 404
        
        # 重新采集
        crawler = WebCrawler()
        result = crawler.crawl(content.url)
        
        if result['success']:
            content.title = result['title']
            content.content = result['content']
            content.html_content = result['html_content']
            content.crawl_status = 'success'
            content.crawl_error = None
            logger.info(f"重新采集成功: {content.url}")
        else:
            content.crawl_status = 'failed'
            content.crawl_error = result['error']
            logger.error(f"重新采集失败: {content.url} - {result['error']}")
        
        db.commit()
        
        return jsonify({
            'success': True,
            'data': content.to_dict()
        })
    except Exception as e:
        logger.error(f"重新采集失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/crawl_stats')
def get_crawl_stats():
    """获取采集统计信息（按问题分组，基于唯一URL）"""
    db = None
    try:
        db = next(get_db())
        
        # 获取所有成功采集的URL（去重）
        crawled_results = db.query(ReferenceContent.collection_result_id, ReferenceContent.url).filter(
            ReferenceContent.crawl_status == 'success'
        ).distinct().all()
        
        # 构建已采集URL集合
        crawled_urls = set()
        cr_id_to_crawled_urls = {}  # collection_result_id -> 已采集URL集合
        for cr_id, url in crawled_results:
            crawled_urls.add(url)
            if cr_id not in cr_id_to_crawled_urls:
                cr_id_to_crawled_urls[cr_id] = set()
            cr_id_to_crawled_urls[cr_id].add(url)
        
        # 从数据库获取完整的 collection_result_id -> question 映射（关键修复）
        cr_id_to_question = scheduler.get_all_collection_result_map()
        
        # 先获取所有待处理引用（用于获取问题名称列表和所有引用URL）
        all_references = scheduler.get_pending_references(limit=None, include_processed=True)
        
        # 构建问题名称到 collection_result_id 的映射
        question_to_cr_ids = {}
        
        # 存储每个 collection_result_id 的所有唯一URL
        cr_id_to_all_urls = {}
        
        for item in all_references:
            question = item['question']
            cr_id = item['collection_result_id']
            if question not in question_to_cr_ids:
                question_to_cr_ids[question] = set()
            question_to_cr_ids[question].add(cr_id)
            # cr_id_to_question 已经从数据库获取，这里不需要再设置
            
            # 提取该采集结果的唯一URL（处理字典或字符串格式）
            if cr_id not in cr_id_to_all_urls:
                cr_id_to_all_urls[cr_id] = set()
            
            refs = item['references']
            for ref in refs:
                if isinstance(ref, dict) and 'url' in ref:
                    cr_id_to_all_urls[cr_id].add(ref['url'])
                elif isinstance(ref, str):
                    cr_id_to_all_urls[cr_id].add(ref)
        
        # 按问题分组统计（基于唯一URL）
        stats = {}
        
        # 初始化所有问题的统计
        for question in question_to_cr_ids:
            stats[question] = {
                'total_count': 0,
                'crawled_count': 0,
                'pending_count': 0
            }
        
        # 统计每个问题的总引用数（基于唯一URL，同一个URL在多个采集结果中出现只算一次）
        question_to_all_urls = {}  # question -> 该问题的所有唯一URL集合
        for cr_id, url_set in cr_id_to_all_urls.items():
            if cr_id in cr_id_to_question:
                question = cr_id_to_question[cr_id]
                if question not in question_to_all_urls:
                    question_to_all_urls[question] = set()
                question_to_all_urls[question].update(url_set)
        
        for question, url_set in question_to_all_urls.items():
            if question in stats:
                stats[question]['total_count'] = len(url_set)
        
        # 统计每个问题的已采集数（基于唯一URL，同一个URL在多个采集结果中出现只算一次）
        question_to_crawled_urls = {}  # question -> 该问题的已采集唯一URL集合
        for cr_id, crawled_url_set in cr_id_to_crawled_urls.items():
            if cr_id in cr_id_to_question:
                question = cr_id_to_question[cr_id]
                if question not in question_to_crawled_urls:
                    question_to_crawled_urls[question] = set()
                question_to_crawled_urls[question].update(crawled_url_set)
        
        for question, crawled_url_set in question_to_crawled_urls.items():
            if question in stats:
                stats[question]['crawled_count'] = len(crawled_url_set)
        
        # 计算未采集数量（总引用数 - 已采集数）
        for question in stats:
            stats[question]['pending_count'] = stats[question]['total_count'] - stats[question]['crawled_count']
        
        return jsonify({
            'success': True,
            'data': stats
        })
    except Exception as e:
        logger.error(f"获取采集统计失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/batch_crawl', methods=['POST'])
def batch_crawl():
    """批量采集引用链接"""
    db = None
    try:
        data = request.get_json()
        collection_result_id = data.get('collection_result_id')
        urls = data.get('urls', [])
        mode = data.get('mode', 'pending')  # pending: 只采集未采集的, all: 重新采集所有
        
        if not collection_result_id or not urls:
            return jsonify({'success': False, 'error': '缺少参数'}), 400
        
        db = next(get_db())
        
        # 根据模式筛选URL
        if mode == 'pending':
            # 只采集未采集的URL
            pending_urls = []
            for url in urls:
                existing = db.query(ReferenceContent).filter(
                    ReferenceContent.collection_result_id == collection_result_id,
                    ReferenceContent.url == url
                ).first()
                if not existing or existing.crawl_status != 'success':
                    pending_urls.append(url)
            urls = pending_urls
        else:
            # 重新采集所有URL，先删除旧记录
            db.query(ReferenceContent).filter(
                ReferenceContent.collection_result_id == collection_result_id
            ).delete()
            db.commit()
        
        if not urls:
            return jsonify({'success': True, 'data': [], 'count': 0, 'message': '没有需要采集的URL'})
        
        contents = batch_crawl_references(collection_result_id, urls)
        # batch_crawl_references 已经返回字典列表，不需要再转换
        
        return jsonify({
            'success': True,
            'data': contents,
            'count': len(contents)
        })
    except Exception as e:
        logger.error(f"批量采集引用链接失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/analyze', methods=['POST'])
def analyze_single():
    """分析单个内容的舆情"""
    try:
        data = request.get_json()
        reference_content_id = data.get('reference_content_id')
        
        if not reference_content_id:
            return jsonify({'success': False, 'error': '缺少参数'}), 400
        
        sentiment = analyze_reference_content(reference_content_id)
        
        return jsonify({
            'success': True,
            'data': sentiment.to_dict()
        })
    except Exception as e:
        logger.error(f"舆情分析失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/batch_analyze', methods=['POST'])
def batch_analyze():
    """批量分析已采集内容的舆情"""
    db = None
    try:
        db = next(get_db())
        
        # 获取所有已成功采集但尚未分析的内容
        contents = db.query(ReferenceContent).filter(
            ReferenceContent.crawl_status == 'success',
            ReferenceContent.content.isnot(None)
        ).all()
        
        if not contents:
            return jsonify({
                'success': True,
                'message': '没有需要分析的内容',
                'success_count': 0,
                'failed_count': 0,
                'total_count': 0
            })
        
        # 使用默认舆情配置
        from config import DEFAULT_SENTIMENT_CONFIG
        sentiment_config = DEFAULT_SENTIMENT_CONFIG
        
        success_count = 0
        failed_count = 0
        
        for content in contents:
            try:
                # 检查是否已存在分析结果
                existing = db.query(ReferenceSentiment).filter_by(
                    reference_content_id=content.id
                ).first()
                
                if not existing:
                    analyze_reference_content(content.id, sentiment_config)
                    success_count += 1
                else:
                    # 如果已存在分析结果，跳过
                    success_count += 1
            except Exception as e:
                logger.error(f"分析内容失败 {content.id}: {str(e)}")
                failed_count += 1
        
        return jsonify({
            'success': True,
            'message': f'批量分析完成',
            'success_count': success_count,
            'failed_count': failed_count,
            'total_count': len(contents)
        })
    except Exception as e:
        logger.error(f"批量分析失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/clear_sentiment', methods=['POST'])
def clear_sentiment():
    """清空所有舆情分析结果"""
    db = None
    try:
        db = next(get_db())
        
        # 删除所有舆情分析结果
        deleted_count = db.query(ReferenceSentiment).delete()
        db.commit()
        
        logger.info(f"清空舆情分析结果: 共删除 {deleted_count} 条记录")
        
        return jsonify({
            'success': True,
            'message': f'已清空所有舆情分析结果，共删除 {deleted_count} 条记录',
            'deleted_count': deleted_count
        })
    except Exception as e:
        logger.error(f"清空舆情分析结果失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/reanalyze', methods=['POST'])
def reanalyze():
    """重新分析所有已采集内容（先清空再分析）"""
    db = None
    try:
        db = next(get_db())
        
        # 先清空所有舆情分析结果
        deleted_count = db.query(ReferenceSentiment).delete()
        db.commit()
        
        # 获取所有已成功采集的内容
        contents = db.query(ReferenceContent).filter(
            ReferenceContent.crawl_status == 'success',
            ReferenceContent.content.isnot(None)
        ).all()
        
        if not contents:
            return jsonify({
                'success': True,
                'message': '没有需要分析的内容',
                'deleted_count': deleted_count,
                'success_count': 0,
                'failed_count': 0,
                'total_count': 0
            })
        
        # 使用默认舆情配置
        from config import DEFAULT_SENTIMENT_CONFIG
        sentiment_config = DEFAULT_SENTIMENT_CONFIG
        
        success_count = 0
        failed_count = 0
        
        for content in contents:
            try:
                analyze_reference_content(content.id, sentiment_config)
                success_count += 1
            except Exception as e:
                logger.error(f"重新分析内容失败 {content.id}: {str(e)}")
                failed_count += 1
        
        return jsonify({
            'success': True,
            'message': f'重新分析完成',
            'deleted_count': deleted_count,
            'success_count': success_count,
            'failed_count': failed_count,
            'total_count': len(contents)
        })
    except Exception as e:
        logger.error(f"重新分析失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if db:
            db.close()


@app.route('/api/run_scheduler', methods=['POST'])
def run_scheduler_once():
    """运行一次调度"""
    try:
        data = request.get_json()
        limit = data.get('limit', 10)
        
        scheduler.run_once(limit=limit)
        
        return jsonify({'success': True, 'message': '调度执行完成'})
    except Exception as e:
        logger.error(f"调度执行失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/scheduler_status')
def scheduler_status():
    """获取调度器状态"""
    return jsonify({
        'success': True,
        'running': scheduler.running
    })


@app.route('/api/start_scheduler', methods=['POST'])
def start_scheduler():
    """启动调度器"""
    try:
        if scheduler.running:
            return jsonify({'success': False, 'error': '调度器已在运行中'}), 400
        
        data = request.get_json()
        interval = data.get('interval', 60)
        
        import threading
        thread = threading.Thread(target=scheduler.run_loop, args=(interval,), daemon=True)
        thread.start()
        
        return jsonify({'success': True, 'message': '调度器已启动'})
    except Exception as e:
        logger.error(f"启动调度器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stop_scheduler', methods=['POST'])
def stop_scheduler():
    """停止调度器"""
    try:
        scheduler.stop()
        return jsonify({'success': True, 'message': '调度器已停止'})
    except Exception as e:
        logger.error(f"停止调度器失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/content/<int:content_id>')
def get_content_detail(content_id):
    """获取内容详情"""
    try:
        db = next(get_db())
        content = db.query(ReferenceContent).filter_by(id=content_id).first()
        
        if not content:
            return jsonify({'success': False, 'error': '内容不存在'}), 404
        
        return jsonify({'success': True, 'data': content.to_dict()})
    except Exception as e:
        logger.error(f"获取内容详情失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sentiment/<int:sentiment_id>')
def get_sentiment_detail(sentiment_id):
    """获取舆情分析详情"""
    try:
        db = next(get_db())
        sentiment = db.query(ReferenceSentiment).filter_by(id=sentiment_id).first()
        
        if not sentiment:
            return jsonify({'success': False, 'error': '分析结果不存在'}), 404
        
        return jsonify({'success': True, 'data': sentiment.to_dict()})
    except Exception as e:
        logger.error(f"获取舆情分析详情失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=6002)
