"""
数据采集器 - 集成现有的采集功能
"""
import sys
import os
import json
import random
import time
import traceback
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# 获取当前北京时间 (CST, UTC+8)
def now_cst():
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)

# 添加父目录到路径，以便导入现有的采集模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db, MonitorTask, CollectionResult
from profile_utils import get_profile_dir
from local_paths import answers_dir


def check_control_command(task_id):
    """
    检查控制命令（线程安全版本）
    返回: (should_stop, is_paused)
    """
    try:
        from app import app
        with app.app_context():
            task = db.session.get(MonitorTask, task_id)
            if not task:
                return True, False
            
            if task.control_command == 'stop':
                print(f"    检测到 [停止] 命令，正在结束采集...")
                task.status = 'stopped'
                task.control_command = None
                db.session.commit()
                return True, False
            
            if task.control_command == 'pause':
                print(f"    检测到 [暂停] 命令，进入暂停状态...")
                task.status = 'paused'
                task.control_command = None
                db.session.commit()
                
                # 循环等待，直到命令变为 resume 或 stop
                while True:
                    time.sleep(2)
                    from models import MonitorTask as FreshTask
                    t = db.session.get(FreshTask, task_id)
                    if not t:
                        return True, False
                    if t.control_command == 'resume':
                        print(f"    检测到 [继续] 命令，恢复采集...")
                        t.status = 'running'
                        t.control_command = None
                        db.session.commit()
                        return False, False
                    if t.control_command == 'stop':
                        print(f"    检测到 [停止] 命令，正在结束采集...")
                        t.status = 'stopped'
                        t.control_command = None
                        db.session.commit()
                        return True, False
        
        return False, False
    except Exception as e:
        print(f"检查控制命令时出错: {e}")
        return False, False


def collect_platform(task_id, user_id, platform_id, questions, brand_keywords, 
                     screenshot_config, min_interval, max_interval, task_collection_interval):
    """
    采集单个平台的数据（独立函数，用于并行执行）
    每个平台使用独立的输出目录，避免并行执行时的文件冲突
    """
    from app import app
    
    print(f"\n[平台 {platform_id}] 开始采集...")
    
    # 检查该平台是否启用截图
    enable_screenshot_for_platform = screenshot_config.get(platform_id, True)
    print(f"[平台 {platform_id}] 截图: {'启用' if enable_screenshot_for_platform else '禁用'}")
    
    # 为每个平台创建独立的输出目录（避免并行冲突）
    platform_output_dir = os.path.join(answers_dir(), platform_id)
    os.makedirs(platform_output_dir, exist_ok=True)
    print(f"[平台 {platform_id}] 输出目录: {platform_output_dir}")
    
    try:
        # 动态导入平台模块
        import importlib
        platform_module = importlib.import_module(f'platforms.{platform_id}')
        
        # Only explicitly opted-in modules may replace the shared browser
        # resolver; all supported platforms otherwise get the same fallback.
        if getattr(platform_module, 'USE_CUSTOM_BROWSER', False) and hasattr(platform_module, 'launch_browser'):
            print(f"[平台 {platform_id}] 使用平台专用浏览器配置")
            browser, context, page = platform_module.launch_browser(profile_dir=get_profile_dir(platform_id, user_id))
            
            try:
                # 遍历每个问题
                for question_index, question in enumerate(questions):
                    # 检查控制命令（暂停/停止）
                    should_stop, _ = check_control_command(task_id)
                    if should_stop:
                        print(f"[平台 {platform_id}] 收到停止命令，退出采集")
                        return
                        
                    print(f"\n[平台 {platform_id}] 问题 [{question_index + 1}/{len(questions)}]: {question}")
                    
                    try:
                        # 如果不是第一个问题，刷新页面以清除之前的状态
                        if question_index > 0:
                            print(f"[平台 {platform_id}] 刷新页面，准备下一个问题...")
                            page.reload(wait_until="domcontentloaded", timeout=30000)
                            time.sleep(2)  # 等待页面完全加载
                        
                        # 调用平台的query函数
                        print(f"[平台 {platform_id}] 开始查询...")
                        
                        # 调用前记录平台目录下所有 png 文件
                        def _collect_pngs(base_dir):
                            """递归收集目录下所有 png 文件的绝对路径集合"""
                            found = set()
                            if os.path.exists(base_dir):
                                for root, dirs, files in os.walk(base_dir):
                                    for f in files:
                                        if f.lower().endswith('.png'):
                                            found.add(os.path.join(root, f))
                            return found
                        
                        pngs_before = _collect_pngs(platform_output_dir)
                        
                        # 调用平台的query函数，传入平台特定的输出目录
                        answer, references = platform_module.query(
                            page, 
                            question, 
                            brand_keywords=brand_keywords,
                            enable_screenshot=enable_screenshot_for_platform,
                            output_dir=platform_output_dir  # 新增：传递平台特定的输出目录
                        )
                        print(f"[平台 {platform_id}] 查询完成，答案长度: {len(answer) if answer else 0}")
                        
                        # 调用后对比，找到新增的截图文件（在平台独立目录中查找）
                        screenshot_path = None
                        if enable_screenshot_for_platform:
                            try:
                                time.sleep(0.5)  # 等待文件写入完成
                                pngs_after = _collect_pngs(platform_output_dir)
                                new_pngs = pngs_after - pngs_before
                                
                                if new_pngs:
                                    # 取最新的截图（按修改时间）
                                    screenshot_path = max(new_pngs, key=os.path.getmtime)
                                    print(f"[平台 {platform_id}] ✓ 截图已保存: {screenshot_path}")
                                else:
                                    print(f"[平台 {platform_id}] ⚠ 未检测到新截图文件")
                            except Exception as e:
                                print(f"[平台 {platform_id}] ⚠ 获取截图路径失败: {e}")
                        else:
                            print(f"[平台 {platform_id}] - 跳过截图（已禁用）")
                        
                        # 检查品牌词曝光
                        has_exposure = False
                        exposed_keywords = []
                        for keyword in brand_keywords:
                            if keyword in answer:
                                has_exposure = True
                                exposed_keywords.append(keyword)
                        
                        # 保存结果（需要在 app_context 内执行）
                        with app.app_context():
                            result = CollectionResult(
                                task_id=task_id,
                                question=question,
                                platform=platform_id,
                                answer=answer,
                                references=json.dumps(references, ensure_ascii=False),
                                screenshot_path=screenshot_path,
                                has_brand_exposure=has_exposure,
                                exposed_keywords=json.dumps(exposed_keywords, ensure_ascii=False)
                            )
                            db.session.add(result)
                            db.session.commit()
                        
                        print(f"[平台 {platform_id}] ✓ 采集成功")
                        print(f"[平台 {platform_id}] 品牌曝光: {'是' if has_exposure else '否'}")
                        if has_exposure:
                            print(f"[平台 {platform_id}] 曝光关键词: {exposed_keywords}")
                        
                        # 问题之间间隔
                        effective_min = min_interval or task_collection_interval or 30
                        effective_max = max_interval or effective_min + 90
                        effective_max = max(effective_max, effective_min)
                        wait_time = random.randint(effective_min, effective_max)
                        if question_index < len(questions) - 1:
                            print(f"[平台 {platform_id}] 等待 {wait_time} 秒后继续下一个问题...", end="", flush=True)
                            for remaining in range(wait_time, 0, -1):
                                # 等待期间也要检查控制命令
                                should_stop, _ = check_control_command(task_id)
                                if should_stop:
                                    print(f"\n[平台 {platform_id}] 收到停止命令，退出采集")
                                    return
                                time.sleep(1)
                                print(f"\r[平台 {platform_id}] 等待 {remaining} 秒后继续下一个问题...", end="", flush=True)
                            print()  # 换行
                    
                    except Exception as e:
                        print(f"[平台 {platform_id}] ✗ 采集失败: {e}")
                        traceback.print_exc()
                        
                        # 即使失败也要等待一下再继续
                        if question_index < len(questions) - 1:
                            print(f"[平台 {platform_id}] 等待 30 秒后继续...", end="", flush=True)
                            for remaining in range(30, 0, -1):
                                should_stop, _ = check_control_command(task_id)
                                if should_stop:
                                    print(f"\n[平台 {platform_id}] 收到停止命令，退出采集")
                                    return
                                time.sleep(1)
                                print(f"\r[平台 {platform_id}] 等待 {remaining} 秒后继续...", end="", flush=True)
                            print()  # 换行
                        continue
            
            finally:
                # 关闭浏览器
                print(f"[平台 {platform_id}] 关闭浏览器...")
                context.close()
                if browser:
                    browser.close()
        
        else:
            # 其他平台使用统一的浏览器工具
            from playwright.sync_api import sync_playwright
            from browser_utils import launch_browser
            
            user_data_dir = get_profile_dir(platform_id, user_id)
            
            with sync_playwright() as p:
                context, browser = launch_browser(p, headless=False, user_data_dir=user_data_dir)
                page = context.pages[0] if context.pages else context.new_page()
                
                try:
                    # 遍历每个问题
                    for question_index, question in enumerate(questions):
                        # 检查控制命令（暂停/停止）
                        should_stop, _ = check_control_command(task_id)
                        if should_stop:
                            print(f"[平台 {platform_id}] 收到停止命令，退出采集")
                            return
                            
                        print(f"\n[平台 {platform_id}] 问题 [{question_index + 1}/{len(questions)}]: {question}")
                        
                        try:
                            # 如果不是第一个问题，刷新页面以清除之前的状态
                            if question_index > 0:
                                print(f"[平台 {platform_id}] 刷新页面，准备下一个问题...")
                                page.reload(wait_until="domcontentloaded", timeout=30000)
                                time.sleep(2)  # 等待页面完全加载
                            
                            # 调用平台的query函数
                            print(f"[平台 {platform_id}] 开始查询...")
                            
                            # 调用前记录平台目录下所有 png 文件
                            def _collect_pngs_other(base_dir):
                                """递归收集目录下所有 png 文件的绝对路径集合"""
                                found = set()
                                if os.path.exists(base_dir):
                                    for root, dirs, files in os.walk(base_dir):
                                        for f in files:
                                            if f.lower().endswith('.png'):
                                                found.add(os.path.join(root, f))
                                return found
                            
                            pngs_before = _collect_pngs_other(platform_output_dir)
                            
                            # 调用平台的query函数，传入平台特定的输出目录
                            answer, references = platform_module.query(
                                page, 
                                question, 
                                brand_keywords=brand_keywords,
                                enable_screenshot=enable_screenshot_for_platform,
                                output_dir=platform_output_dir
                            )
                            print(f"[平台 {platform_id}] 查询完成，答案长度: {len(answer) if answer else 0}")
                            
                            # 调用后对比，找到新增的截图文件（在平台独立目录中查找）
                            screenshot_path = None
                            if enable_screenshot_for_platform:
                                try:
                                    time.sleep(0.5)  # 等待文件写入完成
                                    pngs_after = _collect_pngs_other(platform_output_dir)
                                    new_pngs = pngs_after - pngs_before
                                    
                                    if new_pngs:
                                        # 取最新的截图（按修改时间）
                                        screenshot_path = max(new_pngs, key=os.path.getmtime)
                                        print(f"[平台 {platform_id}] ✓ 截图已保存: {screenshot_path}")
                                    else:
                                        print(f"[平台 {platform_id}] ⚠ 未检测到新截图文件")
                                except Exception as e:
                                    print(f"[平台 {platform_id}] ⚠ 获取截图路径失败: {e}")
                            else:
                                print(f"[平台 {platform_id}] - 跳过截图（已禁用）")
                            
                            # 检查品牌词曝光
                            has_exposure = False
                            exposed_keywords = []
                            for keyword in brand_keywords:
                                if keyword in answer:
                                    has_exposure = True
                                    exposed_keywords.append(keyword)
                            
                            # 保存结果（需要在 app_context 内执行）
                            with app.app_context():
                                result = CollectionResult(
                                    task_id=task_id,
                                    question=question,
                                    platform=platform_id,
                                    answer=answer,
                                    references=json.dumps(references, ensure_ascii=False),
                                    screenshot_path=screenshot_path,
                                    has_brand_exposure=has_exposure,
                                    exposed_keywords=json.dumps(exposed_keywords, ensure_ascii=False)
                                )
                                db.session.add(result)
                                db.session.commit()
                            
                            print(f"[平台 {platform_id}] ✓ 采集成功")
                            print(f"[平台 {platform_id}] 品牌曝光: {'是' if has_exposure else '否'}")
                            if has_exposure:
                                print(f"[平台 {platform_id}] 曝光关键词: {exposed_keywords}")
                            
                            # 问题之间间隔
                            effective_min = min_interval or task_collection_interval or 30
                            effective_max = max_interval or effective_min + 90
                            effective_max = max(effective_max, effective_min)
                            wait_time = random.randint(effective_min, effective_max)
                            if question_index < len(questions) - 1:
                                print(f"[平台 {platform_id}] 等待 {wait_time} 秒后继续下一个问题...", end="", flush=True)
                                for remaining in range(wait_time, 0, -1):
                                    # 等待期间也要检查控制命令
                                    should_stop, _ = check_control_command(task_id)
                                    if should_stop:
                                        print(f"\n[平台 {platform_id}] 收到停止命令，退出采集")
                                        return
                                    time.sleep(1)
                                    print(f"\r[平台 {platform_id}] 等待 {remaining} 秒后继续下一个问题...", end="", flush=True)
                                print()  # 换行
                        
                        except Exception as e:
                            print(f"[平台 {platform_id}] ✗ 采集失败: {e}")
                            traceback.print_exc()
                            
                            # 即使失败也要等待一下再继续
                            if question_index < len(questions) - 1:
                                print(f"[平台 {platform_id}] 等待 30 秒后继续...", end="", flush=True)
                                for remaining in range(30, 0, -1):
                                    should_stop, _ = check_control_command(task_id)
                                    if should_stop:
                                        print(f"\n[平台 {platform_id}] 收到停止命令，退出采集")
                                        return
                                    time.sleep(1)
                                    print(f"\r[平台 {platform_id}] 等待 {remaining} 秒后继续...", end="", flush=True)
                                print()  # 换行
                            continue
                    
                finally:
                    # 关闭浏览器
                    print(f"[平台 {platform_id}] 关闭浏览器...")
                    context.close()
                    if browser:
                        browser.close()
    
    except Exception as e:
        print(f"[平台 {platform_id}] 采集失败: {e}")
        traceback.print_exc()
    
    print(f"[平台 {platform_id}] 采集完成")


def run_collection(task_id, min_interval=None, max_interval=None, interval=None):
    """
    执行数据采集任务（多平台并行执行）
    
    Args:
        task_id: 任务ID
        min_interval: 可选，最小采集间隔（秒）
        max_interval: 可选，最大采集间隔（秒）
        interval: 可选，固定采集间隔（秒），为保持向后兼容性保留此参数
                  如果提供了 interval，会将其作为 min_interval 和 max_interval 的值
    """
    # 处理旧参数 interval，保持向后兼容性
    if interval is not None and min_interval is None and max_interval is None:
        min_interval = interval
        max_interval = interval
    from app import app
    
    with app.app_context():
        # 查找任务
        task = db.session.get(MonitorTask, task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        
        # 确保开始时命令为空，状态为运行
        task.status = 'running'
        task.control_command = None
        db.session.commit()
        
        try:
            # 解析配置
            questions = json.loads(task.questions)
            platforms = json.loads(task.platforms)
            brand_keywords = json.loads(task.brand_keywords)
            screenshot_config = json.loads(task.screenshot_config) if task.screenshot_config else {}
            user_id = task.user_id
            
            print(f"开始采集任务: {task.name}")
            print(f"  问题数: {len(questions)}")
            print(f"  平台数: {len(platforms)}")
            print(f"  品牌词: {brand_keywords}")
            print(f"  截图配置: {screenshot_config}")
            
            # 验证并规范化 max_parallel_platforms（确保健壮性）
            max_parallel = task.max_parallel_platforms
            if max_parallel is None or max_parallel < 1:
                max_parallel = 3  # 默认值
                print(f"  警告: max_parallel_platforms 无效，使用默认值 3")
            print(f"  最大并行数: {max_parallel}")
            
            # 确定实际并行数（至少为1，最多为平台数）
            actual_parallel = max(1, min(len(platforms), max_parallel))
            execution_mode = "串行" if max_parallel == 1 else f"并行({actual_parallel}个)"
            print(f"  执行模式: {execution_mode}")
            
            # 导入现有的采集模块
            import config as _config
            
            # web_app 采集的截图和数据统一存到当前运行模式的数据目录
            WEBAPP_ANSWERS_DIR = answers_dir()
            os.makedirs(WEBAPP_ANSWERS_DIR, exist_ok=True)
            
            # 重置时间戳目录，确保每次新采集任务使用新目录
            import utils
            utils.reset_timestamp_dir()
            
            # 临时覆盖 OUTPUT_DIR，让平台模块把截图存到 web_app/answers/
            _original_output_dir = _config.OUTPUT_DIR
            _config.OUTPUT_DIR = WEBAPP_ANSWERS_DIR
            
            try:
                # 根据并行数决定执行模式
                if max_parallel == 1 or len(platforms) == 1:
                    # 串行执行模式
                    print(f"\n串行执行模式，逐个执行 {len(platforms)} 个平台...")
                    for index, platform_id in enumerate(platforms):
                        print(f"\n[{index + 1}/{len(platforms)}] 开始执行平台: {platform_id}")
                        collect_platform(
                            task_id, 
                            user_id,
                            platform_id, 
                            questions, 
                            brand_keywords, 
                            screenshot_config,
                            min_interval, 
                            max_interval,
                            task.collection_interval
                        )
                        print(f"[{index + 1}/{len(platforms)}] 平台 {platform_id} 执行完成")
                else:
                    # 多平台并行执行（带最大并发限制）
                    print(f"\n多平台并行模式，最大并发 {actual_parallel} 个平台...")
                    print(f"  总平台数: {len(platforms)} 个，将分批次执行")
                    print(f"  平台列表: {', '.join(platforms)}")
                    
                    # 使用线程池并行执行，限制最大并发数
                    with ThreadPoolExecutor(max_workers=actual_parallel) as executor:
                        # 提交所有平台的采集任务
                        futures = {}
                        for platform_id in platforms:
                            print(f"  提交平台任务: {platform_id}")
                            future = executor.submit(
                                collect_platform,
                                task_id,
                                user_id,
                                platform_id,
                                questions,
                                brand_keywords,
                                screenshot_config,
                                min_interval,
                                max_interval,
                                task.collection_interval
                            )
                            futures[future] = platform_id
                        
                        # 等待所有任务完成
                        print(f"\n等待所有平台采集完成... (当前最大并发: {actual_parallel})")
                        completed_count = 0
                        for future in as_completed(futures):
                            completed_count += 1
                            platform_id = futures[future]
                            try:
                                future.result()
                                print(f"  [{completed_count}/{len(platforms)}] 平台 {platform_id} 采集完成")
                            except Exception as e:
                                print(f"  [{completed_count}/{len(platforms)}] 平台 {platform_id} 采集异常: {e}")
                
                print(f"\n所有平台采集任务已完成")
                
            finally:
                # 恢复原始 OUTPUT_DIR
                _config.OUTPUT_DIR = _original_output_dir
            
            # 更新任务状态为完成（检查是否被停止）
            with app.app_context():
                current_task = db.session.get(MonitorTask, task_id)
                if current_task and current_task.status == 'running':
                    current_task.status = 'completed'
                    current_task.last_run_at = now_cst()
                    db.session.commit()
            
            print(f"\n任务完成: {task.name}")
            
        except Exception as e:
            # 捕获所有未处理的异常，更新任务状态为失败
            print(f"\n任务执行失败: {e}")
            traceback.print_exc()
            
            with app.app_context():
                current_task = db.session.get(MonitorTask, task_id)
                if current_task:
                    current_task.status = 'failed'
                    current_task.last_run_at = now_cst()
                    db.session.commit()
            raise


if __name__ == '__main__':
    # 测试采集功能
    if len(sys.argv) > 1:
        task_id = int(sys.argv[1])
        run_collection(task_id)
    else:
        print("用法: python collector.py <task_id>")
