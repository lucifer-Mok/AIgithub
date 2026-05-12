"""
DeepSeek 翻译 & 摘要生成模块

处理优先级：
  1. repo 有中文 README → 直接从中文 README 提炼摘要（不消耗翻译 token）
  2. description 已是中文 → 跳过
  3. description 内容未变化（hash 相同）→ 跳过
  4. 没有 DEEPSEEK_API_KEY → 跳过
  5. 以上都不满足 → 调用 DeepSeek 翻译英文描述
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# 中文字符正则
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def is_chinese(text: str, threshold: float = 0.2) -> bool:
    """判断文本是否已经是中文（中文字符占比超过阈值）"""
    if not text or not text.strip():
        return False
    cjk_count = len(_CJK_PATTERN.findall(text))
    return cjk_count / len(text) >= threshold


def compute_hash(text: str) -> str:
    """计算文本 MD5 hash，用于判断内容是否变化"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def need_translate(description: str, existing_hash: Optional[str]) -> tuple[bool, str]:
    """
    判断是否需要调用 DeepSeek 翻译

    Returns:
        (should_translate: bool, new_hash: str)
    """
    if not settings.deepseek_api_key:
        return False, ""

    content = (description or "").strip()
    if not content:
        return False, ""

    # 已经是中文，不翻译
    if is_chinese(content):
        return False, compute_hash(content)

    new_hash = compute_hash(content)

    # 内容没有变化，不重复翻译
    if existing_hash and existing_hash == new_hash:
        return False, new_hash

    return True, new_hash


# ── Prompt 模板 ──────────────────────────────────────────────────────

_TRANSLATE_PROMPT = """你是一个专业的 AI/开源技术分析师。
用户会给你一个 GitHub 项目的信息，请你用中文输出以下内容（JSON格式）：

{
  "name_zh": "项目中文名称（简洁，保留英文缩写）",
  "summary_zh": "2-3句话的中文摘要，说清楚：这是什么、解决什么问题、适合谁用",
  "tags_zh": ["标签1", "标签2", "标签3"]
}

要求：
- name_zh：直译或意译，保留知名缩写（如 LLM、RAG、MCP、API）
- summary_zh：技术准确，通俗易懂，不要废话，不要"这是一个..."开头
- tags_zh：3-5个精准中文技术标签，如"多Agent框架"、"推理加速"、"向量检索"
- 只输出 JSON，不要其他内容"""

_README_SUMMARY_PROMPT = """你是一个专业的 AI/开源技术分析师。
用户会给你一个 GitHub 项目的中文 README 内容（可能很长），请提炼输出 JSON：

{
  "name_zh": "项目中文名称",
  "summary_zh": "2-3句话摘要，说清楚：这是什么、解决什么问题、适合谁用",
  "tags_zh": ["标签1", "标签2", "标签3"]
}

要求：
- 直接从 README 中提炼，不要编造
- summary_zh 简洁有力，不超过 100 字
- 只输出 JSON，不要其他内容"""


# ── 工具函数 ─────────────────────────────────────────────────────────

def extract_readme_preview(readme_content: str, max_chars: int = 2000) -> str:
    """
    从 README 中提取前段有效内容用于摘要
    跳过徽章行、纯链接行，保留有意义的文字段落
    """
    lines = readme_content.splitlines()
    useful_lines = []
    char_count = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过纯徽章行（大量 ![...](...) 的行）
        if stripped.count("![") > 2:
            continue
        # 跳过 HTML 注释
        if stripped.startswith("<!--"):
            continue
        useful_lines.append(stripped)
        char_count += len(stripped)
        if char_count >= max_chars:
            break

    return "\n".join(useful_lines)


async def _call_deepseek(system_prompt: str, user_content: str) -> Optional[dict]:
    """调用 DeepSeek API 的通用方法"""
    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.deepseek_base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        return {
            "name_zh": str(result.get("name_zh", "")).strip(),
            "summary_zh": str(result.get("summary_zh", "")).strip(),
            "tags_zh": result.get("tags_zh", []) if isinstance(result.get("tags_zh"), list) else [],
        }


# ── 核心翻译函数 ─────────────────────────────────────────────────────

async def summarize_from_readme(repo_name: str, readme_content: str) -> Optional[dict]:
    """
    从中文 README 内容提炼摘要（不需要翻译，直接提炼）
    """
    if not settings.deepseek_api_key or not readme_content:
        return None

    preview = extract_readme_preview(readme_content, max_chars=2000)
    if not preview:
        return None

    user_content = f"项目名称: {repo_name}\n\n中文README内容:\n{preview}"
    try:
        return await _call_deepseek(_README_SUMMARY_PROMPT, user_content)
    except Exception as e:
        logger.error(f"Failed to summarize README for '{repo_name}': {e}")
        return None


async def translate_repo(
    repo_name: str,
    description: str,
    topics: list[str],
    language: str,
) -> Optional[dict]:
    """
    调用 DeepSeek 翻译英文描述，生成中文摘要
    """
    if not settings.deepseek_api_key:
        return None

    topics_str = ", ".join(topics) if topics else "无"
    user_content = (
        f"项目名称: {repo_name}\n"
        f"描述: {description or '无'}\n"
        f"Topics: {topics_str}\n"
        f"主要语言: {language or '未知'}"
    )
    try:
        return await _call_deepseek(_TRANSLATE_PROMPT, user_content)
    except httpx.HTTPStatusError as e:
        logger.error(f"DeepSeek API HTTP error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"DeepSeek translation failed for '{repo_name}': {e}")
        return None


# ── 批量处理入口 ─────────────────────────────────────────────────────

async def batch_process(
    repos: list[dict],
    client,  # GitHubClient 实例，用于检测和拉取中文 README
    concurrency: int = 3,
) -> dict[str, dict]:
    """
    批量处理翻译/摘要，按优先级自动选择策略：
      1. 有中文 README → 从 README 提炼
      2. 描述未变化/已是中文 → 跳过
      3. 其他 → 翻译英文描述

    Args:
        repos: list of {
            "full_name", "repo_name", "description",
            "topics", "language", "desc_hash",
            "has_chinese_readme", "chinese_readme_path"
        }
        client: GitHubClient 实例
        concurrency: 并发数

    Returns:
        dict: full_name -> {"name_zh", "summary_zh", "tags_zh", "desc_hash",
                            "has_chinese_readme", "chinese_readme_path"}
    """
    if not settings.deepseek_api_key:
        logger.info("DeepSeek API key not configured, skipping all translation")
        return {}

    results = {}
    semaphore = asyncio.Semaphore(concurrency)

    async def _process_one(repo: dict):
        full_name = repo["full_name"]
        repo_name = repo.get("repo_name", "")

        async with semaphore:
            await asyncio.sleep(0.5)  # 控制请求频率

            # ── 策略 1：检测并使用中文 README ──────────────────────
            # 如果数据库里已记录有中文 README，直接用；否则检测一次
            has_cn = repo.get("has_chinese_readme", 0)
            cn_path = repo.get("chinese_readme_path", "")

            if not has_cn:
                has_cn_bool, cn_path = await client.detect_chinese_readme(full_name)
                has_cn = 1 if has_cn_bool else 0

            if has_cn and cn_path:
                logger.debug(f"{full_name}: found Chinese README at {cn_path}")
                readme_content = await client.fetch_chinese_readme(full_name, cn_path)
                if readme_content:
                    result = await summarize_from_readme(repo_name, readme_content)
                    if result:
                        result["desc_hash"] = compute_hash(repo.get("description", ""))
                        result["has_chinese_readme"] = 1
                        result["chinese_readme_path"] = cn_path
                        results[full_name] = result
                        logger.info(f"Summarized from Chinese README: {full_name}")
                        return

            # ── 策略 2：翻译英文描述 ────────────────────────────────
            should, new_hash = need_translate(
                repo.get("description", ""),
                repo.get("desc_hash"),
            )
            if not should:
                # 记录中文 README 检测结果（即使不需要翻译）
                if has_cn and cn_path and not repo.get("has_chinese_readme"):
                    results[full_name] = {
                        "has_chinese_readme": has_cn,
                        "chinese_readme_path": cn_path,
                    }
                return

            result = await translate_repo(
                repo_name=repo_name,
                description=repo.get("description", ""),
                topics=repo.get("topics", []),
                language=repo.get("language", ""),
            )
            if result:
                result["desc_hash"] = new_hash
                result["has_chinese_readme"] = has_cn
                result["chinese_readme_path"] = cn_path
                results[full_name] = result
                logger.debug(f"Translated: {full_name}")

    await asyncio.gather(*[_process_one(r) for r in repos])
    logger.info(f"Processed {len(results)}/{len(repos)} repos (translate/summarize)")
    return results


# ── 免费翻译（deep-translator 降级方案）────────────────────────────

def _free_translate(text: str) -> str:
    """
    使用 deep-translator 的 GoogleTranslator 免费翻译
    不需要 API Key，直接调用 Google 翻译网页接口
    失败时返回原文
    """
    if not text or not text.strip():
        return text
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source="auto", target="zh-CN").translate(text[:500])
        return result or text
    except Exception as e:
        logger.warning(f"Free translation failed: {e}")
        return text


async def batch_process_free(
    repos: list[dict],
    concurrency: int = 5,
) -> dict[str, dict]:
    """
    使用免费翻译批量处理（无需 DeepSeek Key）
    只翻译 description，不生成摘要和标签
    同样跳过：已是中文、内容未变化的 repo
    """
    results = {}
    semaphore = asyncio.Semaphore(concurrency)

    async def _translate_one(repo: dict):
        full_name = repo["full_name"]
        description = repo.get("description", "").strip()

        if not description:
            return
        # 已是中文，跳过
        if is_chinese(description):
            return
        # 内容未变化，跳过
        new_hash = compute_hash(description)
        if repo.get("desc_hash") and repo["desc_hash"] == new_hash:
            return

        async with semaphore:
            # 在线程池里跑同步翻译，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            translated = await loop.run_in_executor(None, _free_translate, description)

            if translated and translated != description:
                results[full_name] = {
                    "summary_zh": translated,   # 存到 summary_zh 字段
                    "desc_hash": new_hash,
                }
                logger.debug(f"Free translated: {full_name}")

            # 控制频率，避免被封
            await asyncio.sleep(0.3)

    await asyncio.gather(*[_translate_one(r) for r in repos])
    logger.info(f"Free translated {len(results)}/{len(repos)} repos")
    return results
