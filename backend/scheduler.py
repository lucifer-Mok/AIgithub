"""
定时任务调度器
每天凌晨 2:00 自动执行爬取
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from crawler.runner import run_crawl_sync

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def start_scheduler():
    """启动定时调度器"""
    # 每天凌晨 2:00 执行
    _scheduler.add_job(
        run_crawl_sync,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_crawl",
        name="Daily AI GitHub Crawl",
        replace_existing=True,
        misfire_grace_time=3600,  # 错过执行时，1小时内补跑
    )
    _scheduler.start()
    logger.info("Scheduler started. Daily crawl scheduled at 02:00 CST")


def stop_scheduler():
    """停止调度器"""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def get_scheduler_status() -> dict:
    """获取调度器状态"""
    if not _scheduler.running:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        })

    return {"running": True, "jobs": jobs}
