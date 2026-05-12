"""
数据存储层
负责将爬取到的 repo 数据写入 MySQL
"""

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import Category, Repo, DailyStat, CrawlLog
from crawler.classifier import classify_repo

logger = logging.getLogger(__name__)


def get_category_map(db: Session) -> dict[str, int]:
    """获取 slug -> id 的分类映射"""
    categories = db.query(Category).all()
    return {c.slug: c.id for c in categories}


def upsert_repo(db: Session, repo_data: dict, category_map: dict) -> Optional[Repo]:
    """
    插入或更新 repo 记录

    Returns:
        Repo 对象，非 AI 相关或失败返回 None
    """
    full_name = repo_data.get("full_name", "")
    if not full_name:
        return None

    # 分类
    classification = classify_repo(
        name=repo_data.get("repo_name", ""),
        description=repo_data.get("description", ""),
        topics=repo_data.get("topics", []),
    )

    if not classification["is_ai"]:
        return None

    category_id = category_map.get(classification["category_slug"])

    try:
        repo = db.query(Repo).filter(Repo.github_id == full_name).first()

        if repo:
            repo.description = (repo_data.get("description") or repo.description or "")[:1000]
            repo.language = repo_data.get("language") or repo.language
            repo.homepage = repo_data.get("homepage") or repo.homepage
            repo.stars_total = repo_data.get("stars_total", repo.stars_total)
            repo.forks_total = repo_data.get("forks_total", repo.forks_total)
            repo.watchers = repo_data.get("watchers", repo.watchers)
            repo.open_issues = repo_data.get("open_issues", repo.open_issues)
            if repo_data.get("topics"):
                repo.topics = repo_data["topics"]
            repo.category_id = category_id
            repo.sub_categories = classification["sub_categories"]
            repo.ai_score = classification["ai_score"]
        else:
            repo = Repo(
                github_id=full_name,
                owner=repo_data.get("owner", ""),
                repo_name=repo_data.get("repo_name", ""),
                full_name=full_name,
                description=(repo_data.get("description", "") or "")[:1000],
                language=repo_data.get("language", ""),
                html_url=repo_data.get("html_url", f"https://github.com/{full_name}"),
                homepage=repo_data.get("homepage", ""),
                stars_total=repo_data.get("stars_total", 0),
                forks_total=repo_data.get("forks_total", 0),
                watchers=repo_data.get("watchers", 0),
                open_issues=repo_data.get("open_issues", 0),
                topics=repo_data.get("topics", []),
                category_id=category_id,
                sub_categories=classification["sub_categories"],
                ai_score=classification["ai_score"],
            )
            db.add(repo)

        db.flush()
        return repo

    except Exception as e:
        logger.error(f"Failed to upsert repo {full_name}: {e}")
        db.rollback()
        return None


def upsert_daily_stat(
    db: Session,
    repo: Repo,
    stars_today: int,
    rank: int,
    stat_date: Optional[date] = None,
    trending_language: str = "",
) -> bool:
    """插入或更新每日统计记录"""
    if stat_date is None:
        stat_date = date.today()

    try:
        stat = (
            db.query(DailyStat)
            .filter(DailyStat.repo_id == repo.id, DailyStat.stat_date == stat_date)
            .first()
        )

        if stat:
            stat.stars_today = max(stat.stars_today, stars_today)
            stat.stars_total = repo.stars_total
            stat.rank_position = rank if rank > 0 else stat.rank_position
        else:
            stat = DailyStat(
                repo_id=repo.id,
                stat_date=stat_date,
                stars_today=stars_today,
                stars_total=repo.stars_total,
                forks_today=0,
                rank_position=rank,
                trending_language=trending_language,
            )
            db.add(stat)

        return True

    except Exception as e:
        logger.error(f"Failed to upsert daily stat for repo {repo.id}: {e}")
        return False


def get_repos_needing_translation(db: Session, full_names: list[str]) -> list[dict]:
    """
    从数据库中查出需要翻译的 repo 信息（含已有的 desc_hash、中文README状态）
    """
    if not full_names:
        return []

    repos = (
        db.query(
            Repo.full_name, Repo.repo_name, Repo.description,
            Repo.topics, Repo.language, Repo.desc_hash,
            Repo.has_chinese_readme, Repo.chinese_readme_path,
        )
        .filter(Repo.full_name.in_(full_names))
        .all()
    )

    return [
        {
            "full_name": r.full_name,
            "repo_name": r.repo_name,
            "description": r.description or "",
            "topics": r.topics or [],
            "language": r.language or "",
            "desc_hash": r.desc_hash,
            "has_chinese_readme": r.has_chinese_readme or 0,
            "chinese_readme_path": r.chinese_readme_path or "",
        }
        for r in repos
    ]


def apply_translations(db: Session, translations: dict[str, dict]) -> int:
    """
    将翻译结果批量写回数据库

    Args:
        translations: full_name -> {"name_zh", "summary_zh", "tags_zh", "desc_hash"}

    Returns:
        更新的记录数
    """
    if not translations:
        return 0

    updated = 0
    now = datetime.now()

    for full_name, result in translations.items():
        repo = db.query(Repo).filter(Repo.full_name == full_name).first()
        if not repo:
            continue
        if result.get("name_zh"):
            repo.name_zh = result["name_zh"]
        if result.get("summary_zh"):
            repo.summary_zh = result["summary_zh"]
        if result.get("tags_zh"):
            repo.tags_zh = result["tags_zh"]
        if result.get("desc_hash"):
            repo.desc_hash = result["desc_hash"]
        # 更新中文 README 检测结果
        if "has_chinese_readme" in result:
            repo.has_chinese_readme = result["has_chinese_readme"]
        if result.get("chinese_readme_path"):
            repo.chinese_readme_path = result["chinese_readme_path"]
        # 只有真正翻译/摘要了才更新时间
        if result.get("summary_zh"):
            repo.translated_at = now
        updated += 1
    try:
        db.commit()
        logger.info(f"Applied {updated} translations to database")
    except Exception as e:
        logger.error(f"Failed to apply translations: {e}")
        db.rollback()

    return updated


def save_crawl_log(
    db: Session,
    crawl_date: date,
    status: str,
    total_fetched: int,
    ai_filtered: int,
    duration_seconds: int,
    error_msg: str = "",
) -> None:
    """记录爬取日志"""
    try:
        log = CrawlLog(
            crawl_date=crawl_date,
            status=status,
            total_fetched=total_fetched,
            ai_filtered=ai_filtered,
            duration_seconds=duration_seconds,
            error_msg=error_msg or None,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save crawl log: {e}")
