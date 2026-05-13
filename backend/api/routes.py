"""
FastAPI 路由
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import get_db
from models import Category, Repo, DailyStat, CrawlLog
from crawler.runner import run_daily_crawl

router = APIRouter()


# ── 分类 ────────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """获取所有分类"""
    cats = db.query(Category).order_by(Category.sort_order).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "slug": c.slug,
            "description": c.description,
            "icon": c.icon,
        }
        for c in cats
    ]


# ── Repo 列表 ────────────────────────────────────────────────────────

@router.get("/repos")
def list_repos(
    category: Optional[str] = Query(None),
    date_str: Optional[str] = Query(None, alias="date"),
    sort: str = Query("stars_today"),
    order: str = Query("desc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    获取 repo 列表
    - stars_today：按日期查 daily_stats，默认最近有数据的日期
    - stars_total / ai_score：查全量 repos，不依赖日期
    """
    # 分类过滤（两种模式都需要）
    cat_id = None
    if category:
        cat = db.query(Category).filter(Category.slug == category).first()
        if not cat:
            raise HTTPException(404, f"Category '{category}' not found")
        cat_id = cat.id

    # ── 全量模式（总星数 / AI相关度）────────────────────────────────
    if sort in ("stars_total", "ai_score"):
        if sort == "stars_total":
            sort_col = desc(Repo.stars_total) if order == "desc" else Repo.stars_total
        else:
            sort_col = desc(Repo.ai_score) if order == "desc" else Repo.ai_score
        query = db.query(Repo)
        if cat_id:
            query = query.filter(Repo.category_id == cat_id)
        query = query.order_by(sort_col)
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "date": None,
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [_format_repo(r, None) for r in items],
        }

    # ── 日期模式（今日热度）─────────────────────────────────────────
    if date_str:
        try:
            stat_date = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")
    else:
        # 自动找最近有数据的日期
        latest = db.query(DailyStat.stat_date).order_by(desc(DailyStat.stat_date)).first()
        stat_date = latest.stat_date if latest else date.today()

    query = (
        db.query(Repo, DailyStat)
        .join(DailyStat, DailyStat.repo_id == Repo.id)
        .filter(DailyStat.stat_date == stat_date)
        .filter(DailyStat.stars_today > 0)  # 只显示真正上了 Trending 的
    )
    if cat_id:
        query = query.filter(Repo.category_id == cat_id)
    query = query.order_by(desc(DailyStat.stars_today) if order == "desc" else DailyStat.stars_today)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "date": stat_date.isoformat(),
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_format_repo(repo, stat) for repo, stat in items],
    }


@router.get("/repos/search")
def search_repos(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """全量搜索 repo（搜索名称、描述、中文摘要）"""
    keyword = f"%{q}%"
    from sqlalchemy import or_
    query = (
        db.query(Repo)
        .filter(
            or_(
                Repo.full_name.like(keyword),
                Repo.description.like(keyword),
                Repo.summary_zh.like(keyword),
                Repo.name_zh.like(keyword),
            )
        )
        .order_by(desc(Repo.stars_total))
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    # 搜索结果不依赖 daily_stats，stars_today 设为 0
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {**_format_repo(r, type('S', (), {'stars_today': 0, 'rank_position': 0})()),
             "stars_today": 0, "rank": 0}
            for r in items
        ],
    }


@router.post("/repos/{full_name:path}/translate")
async def translate_repo_on_demand(
    full_name: str,
    engine: str = Query("auto", description="翻译引擎: auto | deepseek | google"),
    db: Session = Depends(get_db),
):
    """
    按需翻译单个 repo
    engine: auto=自动选择, deepseek=DeepSeek, google=Google免费翻译
    """
    from config import settings as cfg
    from crawler.translator import translate_repo, batch_process_free, is_chinese
    from crawler.storage import apply_translations

    repo = db.query(Repo).filter(Repo.full_name == full_name).first()
    if not repo:
        raise HTTPException(404, "Repo not found")

    description = repo.description or ""
    if not description:
        raise HTTPException(400, "No description to translate")

    # 已是中文且有摘要，直接返回
    if repo.summary_zh and is_chinese(repo.summary_zh):
        return {"success": True, "summary_zh": repo.summary_zh, "cached": True}

    # 选择翻译引擎
    use_deepseek = (engine == "deepseek" or (engine == "auto" and cfg.deepseek_api_key))
    use_google = (engine == "google" or (engine == "auto" and not cfg.deepseek_api_key))

    if use_deepseek and cfg.deepseek_api_key:
        result = await translate_repo(
            repo_name=repo.repo_name,
            description=description,
            topics=repo.topics or [],
            language=repo.language or "",
        )
        if result:
            repo.name_zh = result.get("name_zh") or repo.name_zh
            repo.summary_zh = result.get("summary_zh") or repo.summary_zh
            repo.tags_zh = result.get("tags_zh") or repo.tags_zh
            db.commit()
            return {"success": True, "summary_zh": repo.summary_zh, "name_zh": repo.name_zh,
                    "tags_zh": repo.tags_zh, "engine": "deepseek"}
        raise HTTPException(500, "DeepSeek translation failed")

    elif use_google:
        from crawler.translator import _free_translate, compute_hash
        import asyncio
        loop = asyncio.get_event_loop()
        translated = await loop.run_in_executor(None, _free_translate, description)
        if translated and translated != description:
            repo.summary_zh = translated
            repo.desc_hash = compute_hash(description)
            db.commit()
            return {"success": True, "summary_zh": translated, "engine": "google"}
        raise HTTPException(500, "Google translation failed")

    raise HTTPException(400, "No translation engine available. Configure DEEPSEEK_API_KEY or use engine=google")


@router.get("/repos/{full_name:path}")
def get_repo(full_name: str, db: Session = Depends(get_db)):
    """获取单个 repo 详情及近 30 天趋势"""
    repo = db.query(Repo).filter(Repo.full_name == full_name).first()
    if not repo:
        raise HTTPException(404, "Repo not found")

    # 近 30 天统计
    thirty_days_ago = date.today() - timedelta(days=30)
    stats = (
        db.query(DailyStat)
        .filter(
            DailyStat.repo_id == repo.id,
            DailyStat.stat_date >= thirty_days_ago,
        )
        .order_by(DailyStat.stat_date)
        .all()
    )

    cat = db.query(Category).filter(Category.id == repo.category_id).first()

    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "repo_name": repo.repo_name,
        "name_zh": repo.name_zh,
        "description": repo.description,
        "summary_zh": repo.summary_zh,
        "tags_zh": repo.tags_zh or [],
        "language": repo.language,
        "html_url": repo.html_url,
        "homepage": repo.homepage,
        "stars_total": repo.stars_total,
        "forks_total": repo.forks_total,
        "topics": repo.topics or [],
        "category": {"name": cat.name, "slug": cat.slug, "icon": cat.icon} if cat else None,
        "sub_categories": repo.sub_categories or [],
        "ai_score": repo.ai_score,
        "has_chinese_readme": bool(repo.has_chinese_readme),
        "trend": [
            {
                "date": s.stat_date.isoformat(),
                "stars_today": s.stars_today,
                "stars_total": s.stars_total,
                "rank": s.rank_position,
            }
            for s in stats
        ],
    }


# ── 统计概览 ─────────────────────────────────────────────────────────

@router.get("/stats/overview")
def stats_overview(
    date_str: Optional[str] = Query(None, alias="date"),
    sort: str = Query("stars_today", description="当前排序模式，影响分类数量统计"),
    db: Session = Depends(get_db),
):
    """首页概览数据：各分类 repo 数量、今日总新增 star 等"""
    if date_str:
        try:
            stat_date = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(400, "Invalid date format")
    else:
        stat_date = date.today()

    # 如果当天没有数据，自动回退到最近有数据的日期
    today_count = (
        db.query(func.count(DailyStat.id))
        .filter(DailyStat.stat_date == stat_date)
        .scalar() or 0
    )
    if today_count == 0 and not date_str:
        latest = (
            db.query(DailyStat.stat_date)
            .order_by(desc(DailyStat.stat_date))
            .first()
        )
        if latest:
            stat_date = latest.stat_date

    # 各分类数量：今日热度模式用当天 daily_stats，其他模式用全库
    if sort == "stars_today":
        category_counts = (
            db.query(Category.name, Category.slug, Category.icon, func.count(DailyStat.id))
            .outerjoin(Repo, Repo.category_id == Category.id)
            .outerjoin(DailyStat, (DailyStat.repo_id == Repo.id) & (DailyStat.stat_date == stat_date) & (DailyStat.stars_today > 0))
            .group_by(Category.id)
            .order_by(Category.sort_order)
            .all()
        )
    else:
        category_counts = (
            db.query(Category.name, Category.slug, Category.icon, func.count(Repo.id))
            .outerjoin(Repo, Repo.category_id == Category.id)
            .group_by(Category.id)
            .order_by(Category.sort_order)
            .all()
        )

    # 今日新增 star（从 daily_stats 取最近有数据的日期）
    total_stars_today = (
        db.query(func.sum(DailyStat.stars_today))
        .filter(DailyStat.stat_date == stat_date)
        .scalar()
        or 0
    )

    # 当日 trending repo 数（有今日增量的）
    total_repos_today = (
        db.query(func.count(DailyStat.id))
        .filter(DailyStat.stat_date == stat_date)
        .scalar()
        or 0
    )

    # 当日 Trending 数量（有今日增量记录的）
    trending_today = (
        db.query(func.count(DailyStat.id))
        .filter(DailyStat.stat_date == stat_date, DailyStat.stars_today > 0)
        .scalar() or 0
    )

    # 数据库总 repo 数
    total_repos_all = db.query(func.count(Repo.id)).scalar() or 0

    return {
        "date": stat_date.isoformat(),
        "total_repos_today": total_repos_all,
        "total_repos_all": total_repos_all,
        "trending_today": trending_today,
        "total_stars_today": total_stars_today,
        "categories": [
            {"name": name, "slug": slug, "icon": icon, "count": count}
            for name, slug, icon, count in category_counts
        ],
    }


@router.get("/stats/history")
def stats_history(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """近 N 天每日新增 repo 数量趋势"""
    start_date = date.today() - timedelta(days=days)
    rows = (
        db.query(DailyStat.stat_date, func.count(DailyStat.id))
        .filter(DailyStat.stat_date >= start_date)
        .group_by(DailyStat.stat_date)
        .order_by(DailyStat.stat_date)
        .all()
    )
    return [{"date": r[0].isoformat(), "count": r[1]} for r in rows]


# ── 爬虫控制 ─────────────────────────────────────────────────────────

@router.post("/crawl/trigger")
async def trigger_crawl(background_tasks: BackgroundTasks):
    """手动触发一次爬取（后台异步执行）"""
    background_tasks.add_task(run_daily_crawl)
    return {"message": "Crawl task started in background"}


@router.get("/crawl/logs")
def crawl_logs(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """获取最近的爬取日志"""
    logs = (
        db.query(CrawlLog)
        .order_by(desc(CrawlLog.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": l.id,
            "crawl_date": l.crawl_date.isoformat(),
            "status": l.status,
            "total_fetched": l.total_fetched,
            "ai_filtered": l.ai_filtered,
            "duration_seconds": l.duration_seconds,
            "error_msg": l.error_msg,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


# ── 自定义追踪 ───────────────────────────────────────────────────────

from pydantic import BaseModel

class AddRepoTrackRequest(BaseModel):
    input: str          # GitHub URL 或 owner/repo
    description: str = ""

class AddKeywordTrackRequest(BaseModel):
    keyword: str
    min_stars: int = 100
    description: str = ""

class AddTopicTrackRequest(BaseModel):
    topic: str
    min_stars: int = 100
    description: str = ""


@router.get("/tracks")
def list_tracks(db: Session = Depends(get_db)):
    """获取所有自定义追踪配置"""
    from crawler.track_service import get_all_tracks
    return get_all_tracks(db)


@router.post("/tracks/repo")
async def add_repo_track(req: AddRepoTrackRequest, db: Session = Depends(get_db)):
    """
    添加 repo 追踪
    输入 GitHub URL 或 owner/repo，自动拉取分析入库并提取关键词
    """
    from crawler.track_service import add_repo_track as _add
    return await _add(db, req.input, req.description)


@router.post("/tracks/keyword")
async def add_keyword_track(req: AddKeywordTrackRequest, db: Session = Depends(get_db)):
    """手动添加关键词追踪"""
    from crawler.track_service import add_keyword_track as _add
    return await _add(db, req.keyword, req.min_stars, req.description)


@router.post("/tracks/topic")
async def add_topic_track(req: AddTopicTrackRequest, db: Session = Depends(get_db)):
    """手动添加 topic 追踪"""
    from crawler.track_service import add_topic_track as _add
    return await _add(db, req.topic, req.min_stars, req.description)


@router.patch("/tracks/{track_id}")
def update_track(
    track_id: int,
    is_active: Optional[bool] = Query(None),
    min_stars: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """更新追踪规则（启用/禁用 或 修改最低 Star 数）"""
    from crawler.track_service import toggle_track as _toggle
    from models import CustomTrack
    track = db.query(CustomTrack).filter(CustomTrack.id == track_id).first()
    if not track:
        raise HTTPException(404, "Track not found")
    if is_active is not None:
        track.is_active = 1 if is_active else 0
    if min_stars is not None:
        track.min_stars = max(0, min_stars)
    db.commit()
    return {"success": True}


@router.delete("/tracks/{track_id}")
def delete_track(track_id: int, db: Session = Depends(get_db)):
    """删除追踪"""
    from crawler.track_service import delete_track as _delete
    ok = _delete(db, track_id)
    if not ok:
        raise HTTPException(404, "Track not found")
    return {"success": True}

def _format_repo(repo: Repo, stat) -> dict:
    return {
        "id": repo.id,
        "full_name": repo.full_name,
        "owner": repo.owner,
        "repo_name": repo.repo_name,
        "name_zh": repo.name_zh,
        "description": repo.description,
        "summary_zh": repo.summary_zh,
        "tags_zh": repo.tags_zh or [],
        "language": repo.language,
        "html_url": repo.html_url,
        "stars_total": repo.stars_total,
        "stars_today": stat.stars_today if stat else 0,
        "forks_total": repo.forks_total,
        "topics": repo.topics or [],
        "category_id": repo.category_id,
        "sub_categories": repo.sub_categories or [],
        "ai_score": repo.ai_score,
        "rank": stat.rank_position if stat else 0,
        "has_chinese_readme": bool(repo.has_chinese_readme),
    }
