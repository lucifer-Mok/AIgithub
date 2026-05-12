"""
GitHub 数据获取客户端
双轨策略：
  1. GitHub Search API —— 按 topic/关键词搜索 AI 相关 repo，稳定结构化
  2. GitHub Trending 页面爬取 —— 获取每日 trending 列表和今日新增 star 数
无 Token 时自动降级到 60次/小时限制，有 Token 则 5000次/小时
"""

import asyncio
import re
import time
import logging
from datetime import date
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from config import settings, runtime

logger = logging.getLogger(__name__)

# GitHub Trending 页面地址
TRENDING_URL = "https://github.com/trending"

# Search API 搜索的 AI 相关 topic 列表
AI_SEARCH_TOPICS = [
    "llm", "large-language-model", "gpt", "chatgpt", "openai",
    "langchain", "llamaindex", "rag", "retrieval-augmented-generation",
    "ai-agent", "autonomous-agent", "mcp", "model-context-protocol",
    "stable-diffusion", "image-generation", "text-to-image",
    "fine-tuning", "rlhf", "lora", "quantization",
    "vector-database", "embedding", "semantic-search",
    "speech-recognition", "text-to-speech",
    "computer-vision", "object-detection",
    "reinforcement-learning", "robotics",
    "ai-safety", "alignment",
    "code-generation", "coding-assistant",
    "ollama", "vllm", "inference",
    "multimodal", "vision-language-model",
]

# 全文关键词搜索列表（搜索 name+description，捕获没打 topic 标签的优质项目）
# 格式: (query, min_stars)
AI_KEYWORD_QUERIES = [
    # 近期热门方向，容易漏掉的
    ("ai agent framework", 200),
    ("llm application framework", 200),
    ("open source claude alternative", 100),
    ("ai coding assistant ide", 200),
    ("local llm inference", 200),
    ("ai design tool", 200),
    ("mcp server tools", 100),
    ("ai workflow automation", 200),
    ("multimodal ai model", 300),
    ("ai benchmark evaluation", 200),
    ("prompt engineering framework", 200),
    ("ai memory persistent", 100),
    ("generative ai platform", 300),
    ("ai powered search", 200),
    ("neural network visualization", 200),
    # 补充：agentic/skills 类
    ("agentic skills framework", 100),
    ("claude code skills", 100),
    ("ai superpowers coding", 100),
    ("coding agent workflow", 200),
    # 补充：新兴热门
    ("vibe coding tool", 100),
    ("ai pair programmer", 200),
    ("context window management", 100),
    ("ai terminal assistant", 200),
    ("open source devin", 100),
]

# 中文 README 文件名匹配列表（按优先级排序）
CHINESE_README_NAMES = [
    "README.zh-CN.md",
    "README.zh-cn.md",
    "README_zh-CN.md",
    "README.zh.md",
    "README_ZH.md",
    "README_CN.md",
    "README-CN.md",
    "README-ZH.md",
    "readme.zh-cn.md",
    "readme_cn.md",
]
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _build_api_headers() -> dict:
    """构建 GitHub API 请求头，Token 可选"""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AIGithubTracker/1.0",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
        logger.debug("Using GitHub Token for API requests")
    else:
        logger.debug("No GitHub Token configured, using unauthenticated requests (60 req/hour)")
    return headers


class GitHubClient:
    def __init__(self):
        self._api_headers = _build_api_headers()
        # 无 Token 时请求间隔 2 秒，有 Token 时 0.5 秒
        self._request_delay = 0.5 if settings.github_token else 2.0

    async def fetch_trending(
        self,
        since: str = "daily",
        language: str = "",
    ) -> list[dict]:
        """
        爬取 GitHub Trending 页面
        
        Args:
            since: "daily" | "weekly" | "monthly"
            language: 编程语言筛选，空字符串表示全部
            
        Returns:
            list of repo dicts with keys:
                full_name, owner, repo_name, description, language,
                html_url, stars_total, stars_today, forks_total, rank
        """
        url = TRENDING_URL
        params = {"since": since}
        if language:
            url = f"{TRENDING_URL}/{language}"

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(url, params=params, headers=BROWSER_HEADERS)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch trending page: {e}")
                return []

        return self._parse_trending_html(resp.text)

    def _parse_trending_html(self, html: str) -> list[dict]:
        """解析 GitHub Trending 页面 HTML"""
        soup = BeautifulSoup(html, "lxml")
        repos = []

        # 每个 repo 是一个 article 标签
        articles = soup.select("article.Box-row")
        for rank, article in enumerate(articles, start=1):
            try:
                repo = self._parse_article(article, rank)
                if repo:
                    repos.append(repo)
            except Exception as e:
                logger.warning(f"Failed to parse article at rank {rank}: {e}")
                continue

        logger.info(f"Parsed {len(repos)} repos from trending page")
        return repos

    def _parse_article(self, article, rank: int) -> Optional[dict]:
        """解析单个 trending repo 条目"""
        # repo 全名：owner/name
        h2 = article.select_one("h2.h3 a")
        if not h2:
            return None

        href = h2.get("href", "").strip("/")
        parts = href.split("/")
        if len(parts) != 2:
            return None
        owner, repo_name = parts[0], parts[1]

        # 描述
        desc_el = article.select_one("p.col-9")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # 编程语言
        lang_el = article.select_one('[itemprop="programmingLanguage"]')
        language = lang_el.get_text(strip=True) if lang_el else ""

        # 总 star 数
        stars_el = article.select_one('a[href$="/stargazers"]')
        stars_total = self._parse_number(stars_el.get_text(strip=True) if stars_el else "0")

        # 总 fork 数
        forks_el = article.select_one('a[href$="/forks"]')
        forks_total = self._parse_number(forks_el.get_text(strip=True) if forks_el else "0")

        # 今日新增 star
        stars_today_el = article.select_one("span.d-inline-block.float-sm-right")
        stars_today_text = stars_today_el.get_text(strip=True) if stars_today_el else "0"
        stars_today = self._parse_number(stars_today_text)

        return {
            "full_name": f"{owner}/{repo_name}",
            "owner": owner,
            "repo_name": repo_name,
            "description": description,
            "language": language,
            "html_url": f"https://github.com/{owner}/{repo_name}",
            "stars_total": stars_total,
            "stars_today": stars_today,
            "forks_total": forks_total,
            "rank": rank,
        }

    def _parse_number(self, text: str) -> int:
        """解析数字字符串，如 '1,234' -> 1234，'2.1k' -> 2100"""
        text = text.strip().lower().replace(",", "")
        # 提取数字部分
        match = re.search(r"([\d.]+)\s*([km]?)", text)
        if not match:
            return 0
        num = float(match.group(1))
        suffix = match.group(2)
        if suffix == "k":
            num *= 1000
        elif suffix == "m":
            num *= 1_000_000
        return int(num)

    async def search_by_keyword(
        self,
        keyword: str,
        min_stars: int = 200,
        per_page: int = 20,
    ) -> list[dict]:
        """
        通过关键词全文搜索（搜索 name+description），
        捕获没有打 topic 标签但内容相关的优质项目

        Args:
            keyword: 搜索关键词，会在 name 和 description 中匹配
            min_stars: 最低 star 数
            per_page: 每页数量
        """
        url = "https://api.github.com/search/repositories"
        # in:name,description 表示在名称和描述中搜索
        params = {
            "q": f"{keyword} in:name,description stars:>={min_stars}",
            "sort": "stars",
            "order": "desc",
            "per_page": min(per_page, 100),
        }

        await asyncio.sleep(self._request_delay)

        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            try:
                resp = await client.get(url, params=params, headers=self._api_headers)
                if resp.status_code == 401:
                    logger.error("GitHub Token is invalid or expired (401)")
                    runtime.github_token_invalid = True
                    return []
                if resp.status_code == 403:
                    logger.warning("GitHub API rate limit hit, sleeping 60s...")
                    await asyncio.sleep(60)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return [self._normalize_api_repo(r) for r in data.get("items", [])]
            except httpx.HTTPError as e:
                logger.error(f"GitHub keyword search error for '{keyword}': {e}")
                return []

    async def search_ai_repos(
        self,
        topic: str,
        min_stars: int = 100,
        per_page: int = 30,
    ) -> list[dict]:
        """
        通过 GitHub Search API 搜索指定 topic 的 AI 相关 repo
        
        Args:
            topic: GitHub topic 标签
            min_stars: 最低 star 数过滤
            per_page: 每页数量（最大 100）
        """
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"topic:{topic} stars:>={min_stars}",
            "sort": "stars",
            "order": "desc",
            "per_page": min(per_page, 100),
        }

        await asyncio.sleep(self._request_delay)

        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            try:
                resp = await client.get(url, params=params, headers=self._api_headers)
                if resp.status_code == 401:
                    logger.error("GitHub Token is invalid or expired (401)")
                    runtime.github_token_invalid = True
                    return []
                if resp.status_code == 403:
                    logger.warning("GitHub API rate limit hit, sleeping 60s...")
                    await asyncio.sleep(60)
                    return []
                resp.raise_for_status()
                data = resp.json()
                return [self._normalize_api_repo(r) for r in data.get("items", [])]
            except httpx.HTTPError as e:
                logger.error(f"GitHub API error for topic '{topic}': {e}")
                return []

    async def get_repo_detail(self, full_name: str) -> Optional[dict]:
        """
        获取单个 repo 的详细信息（topics、homepage 等）
        """
        url = f"https://api.github.com/repos/{full_name}"
        await asyncio.sleep(self._request_delay)

        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            try:
                resp = await client.get(url, headers=self._api_headers)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 401:
                    logger.error("GitHub Token is invalid or expired (401)")
                    runtime.github_token_invalid = True
                    return None
                if resp.status_code == 403:
                    logger.warning("Rate limit hit on repo detail fetch")
                    await asyncio.sleep(60)
                    return None
                resp.raise_for_status()
                return self._normalize_api_repo(resp.json())
            except httpx.HTTPError as e:
                logger.error(f"Failed to get repo detail for {full_name}: {e}")
                return None

    async def detect_chinese_readme(self, full_name: str) -> tuple[bool, str]:
        """
        检测 repo 根目录是否有中文 README 文件

        Returns:
            (has_chinese_readme: bool, readme_path: str)
            例如: (True, "README.zh-CN.md")
        """
        url = f"https://api.github.com/repos/{full_name}/contents/"
        await asyncio.sleep(self._request_delay)

        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            try:
                resp = await client.get(url, headers=self._api_headers)
                if resp.status_code != 200:
                    return False, ""

                files = resp.json()
                if not isinstance(files, list):
                    return False, ""

                # 获取根目录所有文件名（不区分大小写匹配）
                file_names = {f["name"]: f["name"] for f in files if f.get("type") == "file"}
                file_names_lower = {k.lower(): v for k, v in file_names.items()}

                for candidate in CHINESE_README_NAMES:
                    if candidate.lower() in file_names_lower:
                        actual_name = file_names_lower[candidate.lower()]
                        return True, actual_name

                return False, ""

            except Exception as e:
                logger.warning(f"Failed to detect Chinese README for {full_name}: {e}")
                return False, ""

    async def fetch_chinese_readme(self, full_name: str, readme_path: str) -> str:
        """
        获取中文 README 的原始内容（Markdown 文本）

        Returns:
            README 文本内容，失败返回空字符串
        """
        # 优先用 raw 地址，不消耗 API 配额
        raw_url = f"https://raw.githubusercontent.com/{full_name}/HEAD/{readme_path}"
        await asyncio.sleep(0.3)

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(raw_url, headers=BROWSER_HEADERS)
                if resp.status_code == 200:
                    return resp.text
                return ""
            except Exception as e:
                logger.warning(f"Failed to fetch Chinese README for {full_name}: {e}")
                return ""

    def _normalize_api_repo(self, data: dict) -> dict:
        """将 GitHub API 返回的 repo 数据标准化"""
        return {
            "full_name": data.get("full_name", ""),
            "owner": data.get("owner", {}).get("login", ""),
            "repo_name": data.get("name", ""),
            "description": data.get("description") or "",
            "language": data.get("language") or "",
            "html_url": data.get("html_url", ""),
            "homepage": data.get("homepage") or "",
            "stars_total": data.get("stargazers_count", 0),
            "forks_total": data.get("forks_count", 0),
            "watchers": data.get("watchers_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "topics": data.get("topics", []),
            "stars_today": 0,  # API 不提供今日增量，trending 页面才有
            "rank": 0,
        }

    async def check_rate_limit(self) -> dict:
        """查询当前 API 速率限制状态"""
        token_preview = settings.github_token[:8] if settings.github_token else "EMPTY"
        logger.info(f"check_rate_limit: using token={token_preview}... header_auth={self._api_headers.get('Authorization', 'NONE')[:20]}")
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            try:
                resp = await client.get(
                    "https://api.github.com/rate_limit",
                    headers=self._api_headers,
                )
                if resp.status_code == 401:
                    return {"error": "401 Unauthorized", "token_invalid": True}
                data = resp.json()
                core = data.get("resources", {}).get("core", {})
                search = data.get("resources", {}).get("search", {})
                return {
                    "has_token": bool(settings.github_token),
                    "core_remaining": core.get("remaining", 0),
                    "core_limit": core.get("limit", 0),
                    "search_remaining": search.get("remaining", 0),
                    "search_limit": search.get("limit", 0),
                    "reset_at": core.get("reset", 0),
                }
            except Exception as e:
                return {"error": str(e)}
