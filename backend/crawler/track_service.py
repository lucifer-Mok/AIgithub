"""
自定义追踪服务
支持：
  1. 输入 GitHub URL 或 owner/repo → 立即拉取分析入库，并自动提取关键词加入追踪
  2. 手动添加关键词/topic 追踪
  3. 每次爬取时自动执行所有激活的自定义追踪
"""

import logging
import re
import asyncio
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import CustomTrack, Repo
from crawler.github_client import GitHubClient
from crawler.classifier import classify_repo
from crawler.storage import get_category_map, upsert_repo, upsert_daily_stat

logger = logging.getLogger(__name__)

# 从 repo 信息中自动提取追踪关键词的规则
# 取 topics 里有价值的词 + 描述里的核心词
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "for", "with", "that", "this",
    "from", "your", "you", "are", "is", "it", "in", "of", "to",
    "open", "source", "free", "tool", "tools", "app", "web", "api",
    "github", "repo", "project", "code", "build", "use", "using",
}


def _parse_full_name(input_str: str) -> Optional[str]:
    """
    从各种输入格式解析出 owner/repo
    支持：
      - https://github.com/owner/repo
      - https://github.com/owner/repo/tree/main/...
      - owner/repo
      - repo（仅名称，无法解析，返回 None）
    """
    input_str = input_str.strip().rstrip("/")

    # URL 格式
    url_match = re.search(r"github\.com/([^/]+/[^/\s?#]+)", input_str)
    if url_match:
        return url_match.group(1)

    # owner/repo 格式
    if re.match(r"^[\w.-]+/[\w.-]+$", input_str):
        return input_str

    return None


def _extract_track_keywords(repo_data: dict) -> list[str]:
    """
    从 repo 信息中提取有价值的追踪关键词
    优先用 topics，其次从名称和描述提取
    """
    keywords = []

    # 1. 直接用 topics（最精准）
    topics = repo_data.get("topics", []) or []
    for t in topics:
        t = t.strip().lower()
        if t and len(t) > 2 and t not in _STOP_WORDS:
            keywords.append(t)

    # 2. 从描述提取 2-3 个核心词组合
    description = repo_data.get("description", "") or ""
    if description:
        # 提取描述里的关键短语（取前 5 个有意义的词）
        words = re.findall(r"[a-zA-Z]{3,}", description.lower())
        meaningful = [w for w in words if w not in _STOP_WORDS][:5]
        if len(meaningful) >= 2:
            # 组合成 2-3 词的搜索短语
            keywords.append(" ".join(meaningful[:3]))

    # 3. repo 名称本身（去掉连字符）
    repo_name = repo_data.get("repo_name", "").lower().replace("-", " ").replace("_", " ")
    if repo_name and len(repo_name) > 3:
        keywords.append(repo_name)

    # 去重，最多返回 5 个
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
        if len(result) >= 5:
            break

    return result


async def add_repo_track(
    db: Session,
    input_str: str,
    description: str = "",
) -> dict:
    """
    添加 repo 追踪：输入 GitHub URL 或 owner/repo
    1. 解析 full_name
    2. 从 GitHub API 拉取 repo 详情
    3. 分类入库
    4. 提取关键词，加入 custom_tracks
    5. 返回处理结果

    Returns:
        {"success": bool, "repo": dict, "tracks_added": list, "message": str}
    """
    full_name = _parse_full_name(input_str)
    if not full_name:
        return {
            "success": False,
            "message": f"无法解析 GitHub 地址：{input_str}，请输入 owner/repo 格式或完整 URL",
        }

    client = GitHubClient()

    # 拉取 repo 详情
    logger.info(f"Fetching repo details: {full_name}")
    repo_data = await client.get_repo_detail(full_name)
    if not repo_data:
        return {
            "success": False,
            "message": f"无法获取 repo 信息：{full_name}，请检查地址是否正确",
        }

    # 分类入库
    category_map = get_category_map(db)
    repo = upsert_repo(db, repo_data, category_map)

    if repo:
        upsert_daily_stat(db, repo, stars_today=0, rank=0, stat_date=date.today())
        db.commit()
        logger.info(f"Repo saved: {full_name}, category_id={repo.category_id}")
    else:
        logger.info(f"Classifier filtered {full_name}, force saving as user-tracked")
        repo = _force_upsert_repo(db, repo_data, category_map)
        db.commit()

    # 立即触发翻译（异步，不阻塞返回）
    if repo:
        asyncio.create_task(_translate_single_repo(db, repo_data, client))

    # 添加 repo 本身到追踪列表
    tracks_added = []
    _upsert_track(db, "repo", full_name, source_repo=full_name,
                  description=description or repo_data.get("description", "")[:200])
    tracks_added.append({"type": "repo", "value": full_name})

    # 提取关键词，加入追踪
    keywords = _extract_track_keywords(repo_data)
    for kw in keywords:
        added = _upsert_track(
            db, "keyword", kw,
            min_stars=1000,
            source_repo=full_name,
            description=f"从 {full_name} 自动提取",
        )
        if added:
            tracks_added.append({"type": "keyword", "value": kw})

    # topics 也加入追踪
    for topic in (repo_data.get("topics", []) or [])[:5]:
        added = _upsert_track(
            db, "topic", topic,
            min_stars=1000,
            source_repo=full_name,
            description=f"从 {full_name} 自动提取",
        )
        if added:
            tracks_added.append({"type": "topic", "value": topic})

    db.commit()

    return {
        "success": True,
        "repo": {
            "full_name": full_name,
            "description": repo_data.get("description", ""),
            "stars_total": repo_data.get("stars_total", 0),
            "language": repo_data.get("language", ""),
            "topics": repo_data.get("topics", []),
        },
        "tracks_added": tracks_added,
        "message": f"成功添加追踪：{full_name}，提取了 {len(tracks_added)} 个追踪规则",
    }


async def add_keyword_track(
    db: Session,
    keyword: str,
    min_stars: int = 1000,
    description: str = "",
) -> dict:
    """手动添加关键词追踪"""
    added = _upsert_track(db, "keyword", keyword.strip(),
                          min_stars=min_stars, description=description)
    db.commit()
    return {
        "success": True,
        "added": added,
        "message": f"{'新增' if added else '已存在'}关键词追踪：{keyword}",
    }


async def add_topic_track(
    db: Session,
    topic: str,
    min_stars: int = 1000,
    description: str = "",
) -> dict:
    """手动添加 topic 追踪"""
    added = _upsert_track(db, "topic", topic.strip(),
                          min_stars=min_stars, description=description)
    db.commit()
    return {
        "success": True,
        "added": added,
        "message": f"{'新增' if added else '已存在'} topic 追踪：{topic}",
    }


async def run_custom_tracks(db: Session, client: GitHubClient) -> dict:
    """
    执行所有激活的自定义追踪，在每日爬取时调用
    Returns: {"total": int, "saved": int}
    """
    tracks = db.query(CustomTrack).filter(CustomTrack.is_active == 1).all()
    if not tracks:
        return {"total": 0, "saved": 0}

    category_map = get_category_map(db)
    today = date.today()
    total_fetched = 0
    saved = 0

    for track in tracks:
        try:
            repos = []

            if track.track_type == "repo":
                # 直接更新单个 repo 的最新数据
                repo_data = await client.get_repo_detail(track.value)
                if repo_data:
                    repos = [repo_data]

            elif track.track_type == "keyword":
                repos = await client.search_by_keyword(
                    track.value,
                    min_stars=track.min_stars or 1000,
                    per_page=20,
                )

            elif track.track_type == "topic":
                repos = await client.search_ai_repos(
                    track.value,
                    min_stars=track.min_stars or 1000,
                    per_page=20,
                )

            total_fetched += len(repos)
            for repo_data in repos:
                repo = upsert_repo(db, repo_data, category_map)
                if not repo:
                    repo = _force_upsert_repo(db, repo_data, category_map)
                if repo:
                    upsert_daily_stat(db, repo, stars_today=0, rank=0, stat_date=today)
                    saved += 1

            # 更新最后爬取时间
            track.last_crawled_at = datetime.now()
            db.commit()

        except Exception as e:
            logger.warning(f"Custom track failed [{track.track_type}:{track.value}]: {e}")
            db.rollback()  # 回滚失败的事务，让 Session 恢复正常
            continue

    logger.info(f"Custom tracks done: fetched={total_fetched}, saved={saved}")
    return {"total": total_fetched, "saved": saved}


def get_all_tracks(db: Session) -> list[dict]:
    """获取所有追踪配置"""
    tracks = db.query(CustomTrack).order_by(CustomTrack.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "track_type": t.track_type,
            "value": t.value,
            "min_stars": t.min_stars,
            "source_repo": t.source_repo,
            "description": t.description,
            "is_active": bool(t.is_active),
            "last_crawled_at": t.last_crawled_at.isoformat() if t.last_crawled_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tracks
    ]


def toggle_track(db: Session, track_id: int, is_active: bool) -> bool:
    """启用/禁用追踪"""
    track = db.query(CustomTrack).filter(CustomTrack.id == track_id).first()
    if not track:
        return False
    track.is_active = 1 if is_active else 0
    db.commit()
    return True


def delete_track(db: Session, track_id: int) -> bool:
    """删除追踪"""
    track = db.query(CustomTrack).filter(CustomTrack.id == track_id).first()
    if not track:
        return False
    db.delete(track)
    db.commit()
    return True


# ── 内部工具函数 ─────────────────────────────────────────────────────

def _upsert_track(
    db: Session,
    track_type: str,
    value: str,
    min_stars: int = 0,
    source_repo: str = "",
    description: str = "",
) -> bool:
    """插入追踪记录，已存在则跳过，返回是否新增"""
    existing = (
        db.query(CustomTrack)
        .filter(CustomTrack.track_type == track_type, CustomTrack.value == value)
        .first()
    )
    if existing:
        return False

    track = CustomTrack(
        track_type=track_type,
        value=value,
        min_stars=min_stars,
        source_repo=source_repo or None,
        description=description or None,
        is_active=1,
    )
    db.add(track)
    return True


def _force_upsert_repo(db: Session, repo_data: dict, category_map: dict):
    """强制入库（用户手动追踪的 repo，即使分类器认为不是 AI 相关也保存）"""
    from models import Repo
    full_name = repo_data.get("full_name", "")
    repo = db.query(Repo).filter(Repo.full_name == full_name).first()
    if repo:
        repo.stars_total = repo_data.get("stars_total", repo.stars_total)
        repo.description = repo_data.get("description") or repo.description
    else:
        repo = Repo(
            github_id=full_name,
            owner=repo_data.get("owner", ""),
            repo_name=repo_data.get("repo_name", ""),
            full_name=full_name,
            description=repo_data.get("description", ""),
            language=repo_data.get("language", ""),
            html_url=repo_data.get("html_url", f"https://github.com/{full_name}"),
            homepage=repo_data.get("homepage", ""),
            stars_total=repo_data.get("stars_total", 0),
            forks_total=repo_data.get("forks_total", 0),
            topics=repo_data.get("topics", []),
            ai_score=0.1,  # 用户手动追踪，给个最低分
        )
        db.add(repo)
    db.flush()
    return repo


async def _translate_single_repo(db, repo_data: dict, client):
    """
    为单个 repo 触发翻译（添加追踪时立即调用）
    有 DeepSeek Key 用 DeepSeek，否则用免费翻译
    """
    from crawler.translator import batch_process, batch_process_free, need_translate
    from crawler.storage import get_repos_needing_translation, apply_translations
    from config import settings

    full_name = repo_data.get("full_name", "")
    if not full_name:
        return

    try:
        repos_info = get_repos_needing_translation(db, [full_name])
        if not repos_info:
            return

        if settings.deepseek_api_key:
            translations = await batch_process(repos_info, client, concurrency=1)
        else:
            translations = await batch_process_free(repos_info, concurrency=1)

        if translations:
            apply_translations(db, translations)
            logger.info(f"Translated on-add: {full_name}")
    except Exception as e:
        logger.warning(f"Translation failed for {full_name}: {e}")
