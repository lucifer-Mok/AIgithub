"""
爬虫主入口
每日执行流程：
  1. 爬取 GitHub Trending（今日/本周/本月）
  2. 通过 Search API 补充各 AI topic 的热门 repo
  3. 分类打标，写入数据库
"""

import asyncio
import logging
import time
from datetime import date

from database import SessionLocal
from crawler.github_client import GitHubClient, AI_SEARCH_TOPICS, AI_KEYWORD_QUERIES
from crawler.storage import (
    get_category_map,
    upsert_repo,
    upsert_daily_stat,
    get_repos_needing_translation,
    apply_translations,
    save_crawl_log,
)
from crawler.translator import batch_process

logger = logging.getLogger(__name__)


async def run_daily_crawl() -> dict:
    """
    执行每日完整爬取任务
    
    Returns:
        {
            "status": "success" | "failed" | "partial",
            "total_fetched": int,
            "ai_filtered": int,
            "duration_seconds": int,
        }
    """
    start_time = time.time()
    today = date.today()
    total_fetched = 0
    ai_filtered = 0
    errors = []

    logger.info(f"=== Daily crawl started: {today} ===")

    from config import settings as cfg
    client = GitHubClient()
    db = SessionLocal()

    try:
        category_map = get_category_map(db)
        logger.info(f"Loaded {len(category_map)} categories")

        # ── 阶段 1：爬取 Trending 页面（daily + weekly）────────────
        logger.info("Phase 1: Fetching GitHub Trending...")
        trending_repos = await client.fetch_trending(since="daily")
        trending_weekly = await client.fetch_trending(since="weekly")

        # weekly 里 stars_today 实际是本周增量，字段名复用
        # 合并去重，daily 优先（有今日精确数据）
        seen = {r["full_name"] for r in trending_repos}
        for r in trending_weekly:
            if r["full_name"] not in seen:
                trending_repos.append(r)
                seen.add(r["full_name"])

        total_fetched += len(trending_repos)
        logger.info(f"  Got {len(trending_repos)} trending repos (daily+weekly)")

        for repo_data in trending_repos:
            # Trending 页面没有 topics，尝试从 API 补充（有 Token 时）
            repo_data["topics"] = []

            repo = upsert_repo(db, repo_data, category_map)
            if repo:
                ai_filtered += 1
                upsert_daily_stat(
                    db, repo,
                    stars_today=repo_data.get("stars_today", 0),
                    rank=repo_data.get("rank", 0),
                    stat_date=today,
                )

        db.commit()
        logger.info(f"  Saved {ai_filtered} AI repos from trending")

        # ── 阶段 2：Search API 并发请求（最多3个同时），串行入库 ────
        logger.info("Phase 2: Fetching repos by AI topics (concurrent x3)...")
        api_count = 0
        api_saved_names = []
        # Semaphore 在当前事件循环里创建，避免跨循环问题
        sem = asyncio.Semaphore(3 if cfg.github_token else 1)

        async def fetch_one(coro):
            async with sem:
                return await coro

        # 并发请求所有 topic
        topic_tasks = [fetch_one(client.search_ai_repos(t, min_stars=cfg.min_stars_topic, per_page=20))
                       for t in AI_SEARCH_TOPICS]
        topic_results_raw = await asyncio.gather(*topic_tasks, return_exceptions=True)

        total_fetched += sum(len(r) for r in topic_results_raw if isinstance(r, list))
        logger.info(f"  All {len(AI_SEARCH_TOPICS)} topic requests done")

        # 串行入库
        for i, repos in enumerate(topic_results_raw):
            if isinstance(repos, Exception):
                errors.append(f"topic error: {repos}")
                continue
            for repo_data in repos:
                try:
                    repo = upsert_repo(db, repo_data, category_map)
                    if repo:
                        api_count += 1
                        api_saved_names.append(repo_data.get("full_name"))
                        upsert_daily_stat(db, repo, stars_today=0, rank=0, stat_date=today)
                except Exception:
                    db.rollback()
        try:
            db.commit()
        except Exception as e:
            logger.warning(f"  commit error: {e}"); db.rollback()

        ai_filtered += api_count
        logger.info(f"  Saved {api_count} repos from topic search")

        # ── 阶段 2b：关键词全文搜索（并发）────────────────────────────
        logger.info("Phase 2b: Fetching repos by keyword search (concurrent x3)...")
        kw_count = 0

        kw_tasks = [fetch_one(client.search_by_keyword(kw, min_stars=cfg.min_stars_keyword, per_page=20))
                    for kw, _ in AI_KEYWORD_QUERIES]
        kw_results_raw = await asyncio.gather(*kw_tasks, return_exceptions=True)

        total_fetched += sum(len(r) for r in kw_results_raw if isinstance(r, list))
        logger.info(f"  All {len(AI_KEYWORD_QUERIES)} keyword requests done")

        # 串行入库
        for repos in kw_results_raw:
            if isinstance(repos, Exception):
                errors.append(f"keyword error: {repos}")
                continue
            for repo_data in repos:
                try:
                    repo = upsert_repo(db, repo_data, category_map)
                    if repo:
                        kw_count += 1
                        api_saved_names.append(repo_data.get("full_name"))
                        upsert_daily_stat(db, repo, stars_today=0, rank=0, stat_date=today)
                except Exception:
                    db.rollback()
        try:
            db.commit()
        except Exception as e:
            logger.warning(f"  commit error: {e}"); db.rollback()

        ai_filtered += kw_count
        logger.info(f"  Saved {kw_count} additional AI repos from keyword search")

        # ── 阶段 2c：执行用户自定义追踪 ─────────────────────────────
        logger.info("Phase 2c: Running custom tracks...")
        from crawler.track_service import run_custom_tracks
        custom_result = await run_custom_tracks(db, client)
        ai_filtered += custom_result["saved"]
        total_fetched += custom_result["total"]
        logger.info(f"  Custom tracks: fetched={custom_result['total']}, saved={custom_result['saved']}")

        # ── 阶段 3：翻译（后台异步，不阻塞爬取完成）────────────────
        all_saved_names = list({
            *[r.get("full_name") for r in trending_repos],
            *api_saved_names,
        })
        repos_for_translation = get_repos_needing_translation(db, all_saved_names)
        logger.info(f"  Translation candidates: {len(repos_for_translation)} repos")

        logger.info("Phase 3: Starting translation in background...")
        from crawler.translator import batch_process, batch_process_free

        async def _run_translation():
            try:
                if cfg.deepseek_api_key:
                    logger.info("  Translation: using DeepSeek")
                    translations = await batch_process(repos_for_translation, client, concurrency=3)
                else:
                    logger.info("  Translation: using free Google translator")
                    translations = await batch_process_free(repos_for_translation, concurrency=5)
                translated_count = apply_translations(db, translations)
                logger.info(f"  Translation done: {translated_count} repos")
            except asyncio.CancelledError:
                logger.info("  Translation task cancelled (server shutdown)")
            except RuntimeError as e:
                if "shutdown" in str(e).lower():
                    logger.info("  Translation task stopped (executor shutdown)")
                else:
                    logger.error(f"  Translation failed: {e}")
            except Exception as e:
                logger.error(f"  Translation failed: {e}")

        asyncio.create_task(_run_translation())
        logger.info("  Translation task started in background")

        duration = int(time.time() - start_time)
        status = "partial" if errors else "success"

        save_crawl_log(
            db,
            crawl_date=today,
            status=status,
            total_fetched=total_fetched,
            ai_filtered=ai_filtered,
            duration_seconds=duration,
            error_msg="; ".join(errors[:5]) if errors else "",
        )

        logger.info(
            f"=== Crawl finished: status={status}, "
            f"total={total_fetched}, ai={ai_filtered}, "
            f"duration={duration}s ==="
        )

        return {
            "status": status,
            "total_fetched": total_fetched,
            "ai_filtered": ai_filtered,
            "duration_seconds": duration,
        }

    except Exception as e:
        duration = int(time.time() - start_time)
        logger.error(f"Crawl failed with exception: {e}", exc_info=True)

        save_crawl_log(
            db,
            crawl_date=today,
            status="failed",
            total_fetched=total_fetched,
            ai_filtered=ai_filtered,
            duration_seconds=duration,
            error_msg=str(e),
        )

        return {
            "status": "failed",
            "total_fetched": total_fetched,
            "ai_filtered": ai_filtered,
            "duration_seconds": duration,
            "error": str(e),
        }

    finally:
        db.close()


async def _enrich_trending_topics(client, db, category_map, today):
    """
    为 Trending 页面爬到的 repo 补充 topics（调用 API）
    仅在有 Token 时建议开启，否则容易触发速率限制
    """
    from models import Repo, DailyStat
    repos_without_topics = (
        db.query(Repo)
        .join(DailyStat, DailyStat.repo_id == Repo.id)
        .filter(
            DailyStat.stat_date == today,
            DailyStat.rank_position > 0,
            Repo.topics == None,
        )
        .limit(25)
        .all()
    )

    for repo in repos_without_topics:
        detail = await client.get_repo_detail(repo.full_name)
        if detail and detail.get("topics"):
            repo.topics = detail["topics"]
            # 重新分类
            from crawler.classifier import classify_repo
            cls = classify_repo(repo.repo_name, repo.description, repo.topics)
            if cls["category_slug"]:
                repo.category_id = category_map.get(cls["category_slug"])
                repo.sub_categories = cls["sub_categories"]
                repo.ai_score = cls["ai_score"]

    db.commit()
    logger.info(f"Enriched topics for {len(repos_without_topics)} repos")


def run_crawl_sync() -> dict:
    """同步包装，供调度器调用"""
    return asyncio.run(run_daily_crawl())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = asyncio.run(run_daily_crawl())
    print(result)
