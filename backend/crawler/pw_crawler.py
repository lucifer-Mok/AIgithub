"""
Playwright 爬虫
用真实浏览器抓取 GitHub Search 页面，完全不需要 Token
抓取策略：
  - GitHub Search 按 stars 排序，筛选 AI 相关关键词
  - 每个关键词抓一页（10条），多关键词覆盖不同分类
"""

import asyncio
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger(__name__)

# 搜索关键词列表，覆盖各 AI 分类
# 格式: (query, since)  since: "" | "daily" | "weekly" | "monthly"
SEARCH_QUERIES = [
    # LLM
    ("llm language model", ""),
    ("large language model pytorch", ""),
    ("chatgpt openai api", ""),
    ("ollama local llm", ""),
    # RAG
    ("rag retrieval augmented generation", ""),
    ("vector database embedding", ""),
    ("langchain llamaindex", ""),
    # Agent
    ("ai agent autonomous", ""),
    ("multi agent framework", ""),
    ("mcp model context protocol", ""),
    # 图像视觉
    ("stable diffusion image generation", ""),
    ("text to image diffusion", ""),
    # 训练微调
    ("llm fine tuning lora", ""),
    ("rlhf reinforcement learning", ""),
    # 推理部署
    ("llm inference serving vllm", ""),
    ("model quantization gguf", ""),
    # 代码生成
    ("ai coding assistant code generation", ""),
    # 音频语音
    ("speech recognition tts whisper", ""),
    # 工具链
    ("ai framework sdk toolkit", ""),
    # 具身智能
    ("robotics embodied ai", ""),
]

# GitHub Search URL 模板
SEARCH_URL = "https://github.com/search?q={query}&type=repositories&s=stars&o=desc"


class PlaywrightCrawler:
    def __init__(self):
        self._browser: Optional[Browser] = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        await self._pw.stop()

    async def _new_page(self) -> Page:
        context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()
        # 屏蔽图片/字体加速加载
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )
        return page

    async def search_repos(self, query: str, max_results: int = 10) -> list[dict]:
        """
        搜索 GitHub，返回 repo 列表
        """
        url = SEARCH_URL.format(query=query.replace(" ", "+"))
        page = await self._new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等待搜索结果加载
            await page.wait_for_selector(
                "div[data-testid='results-list'], .search-results",
                timeout=15000,
            )
            await asyncio.sleep(1)  # 等 JS 渲染完成

            html = await page.content()
            repos = self._parse_search_results(html)
            logger.debug(f"Search '{query}': found {len(repos)} repos")
            return repos[:max_results]

        except Exception as e:
            logger.warning(f"Search failed for query '{query}': {e}")
            return []
        finally:
            await page.context.close()

    def _parse_search_results(self, html: str) -> list[dict]:
        """解析 GitHub Search 结果页面"""
        soup = BeautifulSoup(html, "lxml")
        repos = []

        # GitHub Search 结果的容器
        # 新版 GitHub 用 data-testid="results-list"
        result_items = soup.select("div[data-testid='results-list'] > div")
        if not result_items:
            # 兼容旧版结构
            result_items = soup.select("li.repo-list-item, div.search-result")

        for item in result_items:
            try:
                repo = self._parse_search_item(item)
                if repo:
                    repos.append(repo)
            except Exception as e:
                logger.debug(f"Failed to parse search item: {e}")
                continue

        return repos

    def _parse_search_item(self, item) -> Optional[dict]:
        """解析单个搜索结果条目"""
        # repo 链接
        link = item.select_one("a[href*='/'][data-hydro-click]") or item.select_one("h3 a, h2 a")
        if not link:
            return None

        href = link.get("href", "").strip("/")
        # 过滤掉非 repo 链接（如 /topics/xxx）
        parts = href.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None

        owner, repo_name = parts[0], parts[1]
        full_name = f"{owner}/{repo_name}"

        # 描述
        desc_el = item.select_one("p[class*='description'], p[class*='color-fg-muted']")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # 编程语言
        lang_el = item.select_one("[itemprop='programmingLanguage'], span[class*='language']")
        language = lang_el.get_text(strip=True) if lang_el else ""

        # Star 数
        star_el = item.select_one(
            "a[href$='/stargazers'] span, "
            "span[class*='stars'], "
            "a[href*='stargazers']"
        )
        stars_text = star_el.get_text(strip=True) if star_el else "0"
        stars_total = self._parse_number(stars_text)

        # Topics
        topic_els = item.select("a[data-ga-click*='topic'], a[class*='topic-tag']")
        topics = [t.get_text(strip=True) for t in topic_els]

        return {
            "full_name": full_name,
            "owner": owner,
            "repo_name": repo_name,
            "description": description,
            "language": language,
            "html_url": f"https://github.com/{full_name}",
            "homepage": "",
            "stars_total": stars_total,
            "forks_total": 0,
            "watchers": stars_total,
            "open_issues": 0,
            "topics": topics,
            "stars_today": 0,
            "rank": 0,
        }

    def _parse_number(self, text: str) -> int:
        """解析数字，如 '12.3k' -> 12300"""
        text = text.strip().lower().replace(",", "")
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

    async def fetch_all_ai_repos(self, max_per_query: int = 10) -> list[dict]:
        """
        批量搜索所有 AI 相关关键词，去重后返回
        """
        all_repos: dict[str, dict] = {}  # full_name -> repo，自动去重

        for query, _ in SEARCH_QUERIES:
            try:
                repos = await self.search_repos(query, max_results=max_per_query)
                for r in repos:
                    fn = r["full_name"]
                    # 保留 stars 更多的那条
                    if fn not in all_repos or r["stars_total"] > all_repos[fn]["stars_total"]:
                        all_repos[fn] = r
                # 每次搜索间隔 2 秒，避免被限流
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Query '{query}' failed: {e}")
                continue

        result = list(all_repos.values())
        logger.info(f"Playwright search total: {len(result)} unique repos from {len(SEARCH_QUERIES)} queries")
        return result
