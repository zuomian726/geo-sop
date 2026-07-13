"""
定时调度器模块
使用 APScheduler 实现每日定时任务自动采集
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask

from models import db, MonitorTask

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = None


def init_scheduler(app: Flask):
    """初始化调度器"""
    global scheduler
    
    if scheduler is not None:
        return scheduler
    
    scheduler = BackgroundScheduler(timezone='Asia/Shanghai')
    
    # 添加每日检查任务（每分钟检查一次是否有需要执行的任务）
    scheduler.add_job(
        func=lambda: check_and_run_scheduled_tasks(app),
        trigger='cron',
        minute='*',  # 每分钟检查
        id='daily_task_checker',
        name='检查每日定时任务',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("定时调度器已启动")
    
    # 启动时注册所有已启用的定时任务
    with app.app_context():
        tasks = MonitorTask.query.filter_by(schedule_enabled=True).all()
        for task in tasks:
            if task.schedule_type in ['daily', 'weekly']:
                logger.info(f"注册已配置的定时任务: {task.name} ({task.schedule_type})")
    
    return scheduler


def check_and_run_scheduled_tasks(app: Flask):
    """检查并执行到时的定时任务（仅作为备用机制）"""
    with app.app_context():
        # 使用上海时区
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        current_time = now.strftime('%H:%M')
        current_date = now.date()
        current_weekday = now.weekday()  # 0=周一, 6=周日
        
        # 查找需要执行的任务（只处理没有专用cron任务的任务，避免重复触发）
        tasks = MonitorTask.query.filter_by(schedule_enabled=True).all()
        
        for task in tasks:
            try:
                # 检查任务是否已经有专用cron任务
                has_dedicated_job = False
                if scheduler:
                    try:
                        job_id_prefix = f"task_{task.id}"
                        for job in scheduler.get_jobs():
                            if job.id.startswith(job_id_prefix):
                                has_dedicated_job = True
                                break
                    except:
                        pass
                
                # 如果有专用cron任务，跳过（由专用任务处理）
                if has_dedicated_job:
                    continue
                
                schedule_config = json.loads(task.schedule_config) if task.schedule_config else {}
                
                if task.schedule_type == 'daily':
                    # 每日执行
                    run_times = schedule_config.get('run_times', ['09:00'])
                    
                    for r_time in run_times:
                        # 1. 检查是否到达或超过了设定时间
                        # 2. 检查今天是否还没跑过这个时间点的任务
                        
                        # 构造今天的计划执行时间点
                        try:
                            hour, minute = map(int, r_time.split(':'))
                            planned_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        except:
                            continue

                        # 判断逻辑：
                        # a) 当前时间 >= 计划时间
                        # b) 最后运行时间为空，或者最后运行日期早于今天，或者最后运行日期是今天但时间早于计划时间且当前已过计划时间
                        
                        should_run = False
                        if now >= planned_time:
                            if not task.last_run_at:
                                should_run = True
                            else:
                                # 处理本地化时间比较
                                # 注意：db 中的 last_run_at 是不带时区的上海时间
                                last_run = task.last_run_at
                                if last_run.date() < current_date:
                                    should_run = True
                                elif last_run.date() == current_date:
                                    last_run_time_str = last_run.strftime('%H:%M')
                                    # 如果今天跑过了，但跑的时间比当前的计划时间点早
                                    # 并且当前时间已经到了计划时间点
                                    if last_run_time_str < r_time:
                                        should_run = True
                        
                        if should_run:
                            # 额外检查：避免在同一分钟内重复触发
                            # 或者如果已经过了计划时间太久（比如超过1小时），可能就不自动补跑了，视需求而定
                            # 这里允许在计划时间后的 5 分钟内“补跑”
                            is_in_window = (current_time == r_time)
                            is_catch_up = (now >= planned_time and now < planned_time + timedelta(minutes=10))
                            
                            if is_in_window or is_catch_up:
                                logger.info(f"触发每日定时任务: {task.name} (计划时间: {r_time}, 当前时间: {current_time})")
                                run_task_async(app, task.id)
                                break # 一个任务在一次检查中只触发一个时间点
                
                elif task.schedule_type == 'weekly':
                    # 每周执行
                    run_weekdays = schedule_config.get('run_weekdays', [0])  # 默认周一
                    run_time = schedule_config.get('run_time', '09:00')
                    
                    if current_weekday in run_weekdays and current_time == run_time:
                        # 检查该时间点是否本周已执行过
                        if task.last_run_at:
                            if task.last_run_at.date() == current_date:
                                continue
                        
                        logger.info(f"触发每周定时任务: {task.name} ({run_weekdays} {run_time})")
                        run_task_async(app, task.id)
                        
            except Exception as e:
                logger.error(f"执行定时任务 {task.id} 失败: {e}")


def run_task_async(app: Flask, task_id: int):
    """异步执行采集任务"""
    import threading
    
    def run_in_background():
        from collector import run_collection
        
        with app.app_context():
            task = db.session.get(MonitorTask, task_id)
            if not task:
                return
            
            # 检查任务状态
            if task.status == 'running':
                logger.info(f"任务 {task.name} 正在执行中，跳过")
                return
            
            # 更新任务状态
            task.status = 'running'
            task.last_run_at = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
            db.session.commit()
            
            try:
                run_collection(task_id, min_interval=task.collection_interval, max_interval=task.collection_interval)
                logger.info(f"定时任务执行完成: {task.name}")
            except Exception as e:
                logger.error(f"定时任务执行失败: {task.name}, 错误: {e}")
                task.status = 'failed'
                db.session.commit()
            finally:
                try:
                    from cloud_sync import cloud_sync_enabled, sync_user_workspace, upload_workspace_assets
                    if cloud_sync_enabled():
                        sync_user_workspace(task.user_id)
                        upload_workspace_assets(task.user_id, task_ids=[task_id])
                except Exception as sync_error:
                    logger.warning(f"定时任务云端同步失败: {sync_error}")
    
    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()


def add_task_job(app: Flask, task_id: int):
    """为指定任务添加调度任务"""
    global scheduler
    
    if scheduler is None:
        return
    
    with app.app_context():
        task = db.session.get(MonitorTask, task_id)
        if not task:
            return
        
        schedule_config = json.loads(task.schedule_config) if task.schedule_config else {}
        
        if task.schedule_type == 'daily' and task.schedule_enabled:
            run_times = schedule_config.get('run_times', ['09:00'])
            job_id = f"task_{task_id}"
            
            # 移除旧任务（如果存在）
            for i in range(10):
                try:
                    scheduler.remove_job(f"{job_id}_{i}")
                except:
                    pass
            
            # 添加新任务（使用多个触发器，每个时间点一个）
            for i, run_time in enumerate(run_times):
                hour, minute = run_time.split(':')
                trigger = CronTrigger(hour=hour, minute=minute, timezone='Asia/Shanghai')
                scheduler.add_job(
                    func=lambda tid=task_id: run_task_async(app, tid),
                    trigger=trigger,
                    id=f"{job_id}_{i}",
                    name=f"任务-{task.name}-{run_time}",
                    replace_existing=True,
                    max_instances=1
                )
            
            logger.info(f"已为任务 {task.name} 添加每日调度: {run_times}")
        
        elif task.schedule_type == 'weekly' and task.schedule_enabled:
            run_weekdays = schedule_config.get('run_weekdays', [0])
            run_time = schedule_config.get('run_time', '09:00')
            hour, minute = run_time.split(':')
            job_id = f"task_{task_id}"
            
            # 移除旧任务
            try:
                scheduler.remove_job(job_id)
            except:
                pass
            
            # 添加每周任务
            trigger = CronTrigger(day_of_week=','.join(str(d) for d in run_weekdays),
                                 hour=hour, minute=minute, timezone='Asia/Shanghai')
            scheduler.add_job(
                func=lambda tid=task_id: run_task_async(app, tid),
                trigger=trigger,
                id=job_id,
                name=f"任务-{task.name}-每周",
                replace_existing=True,
                max_instances=1
            )
            
            logger.info(f"已为任务 {task.name} 添加每周调度: 星期{run_weekdays} {run_time}")


def remove_task_job(task_id: int):
    """移除指定任务的调度任务"""
    global scheduler
    
    if scheduler is None:
        return
    
    job_id = f"task_{task_id}"
    
    # 移除所有相关的调度任务
    for i in range(10):  # 假设最多10个执行时间点
        try:
            scheduler.remove_job(f"{job_id}_{i}")
        except:
            pass
    
    logger.info(f"已移除任务 {task_id} 的调度")


def shutdown_scheduler():
    """关闭调度器"""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("定时调度器已关闭")
