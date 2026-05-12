"""
系统配置接口
直接读写 .env 文件，修改后热加载，无需重启
"""

import re
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ENV_PATH = Path(__file__).parent.parent / ".env"

# 可配置的 key 白名单（防止任意写入）
ALLOWED_KEYS = {
    "GITHUB_TOKEN",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
}

# 敏感字段，返回时脱敏
SECRET_KEYS = {"GITHUB_TOKEN", "DEEPSEEK_API_KEY"}


def _read_env() -> dict[str, str]:
    """读取 .env 文件，返回 key->value 字典"""
    result = {}
    if not ENV_PATH.exists():
        return result
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def _write_env_key(key: str, value: str):
    """更新 .env 文件中的某个 key，保留注释和其他内容"""
    if not ENV_PATH.exists():
        raise FileNotFoundError(".env file not found")

    content = ENV_PATH.read_text(encoding="utf-8")
    # 匹配 KEY=任意值（包括空值）
    pattern = re.compile(rf"^({re.escape(key)}\s*=).*$", re.MULTILINE)

    if pattern.search(content):
        # key 已存在，替换
        new_content = pattern.sub(rf"\g<1>{value}", content)
    else:
        # key 不存在，追加
        new_content = content.rstrip() + f"\n{key}={value}\n"

    ENV_PATH.write_text(new_content, encoding="utf-8")


def _reload_settings():
    """重新加载 settings（热加载）"""
    from dotenv import load_dotenv
    load_dotenv(str(ENV_PATH), override=True)
    # 更新现有 settings 对象的属性，而不是替换对象
    # 替换对象会导致其他模块持有旧引用
    import config
    new = config.Settings()
    config.settings.github_token = new.github_token
    config.settings.deepseek_api_key = new.deepseek_api_key
    config.settings.deepseek_base_url = new.deepseek_base_url
    config.settings.deepseek_model = new.deepseek_model


@router.get("/config/verify/github")
async def verify_github_token():
    """验证 GitHub Token 是否有效"""
    from crawler.github_client import GitHubClient
    from config import settings as cfg

    # 如果运行时已标记为失效，直接返回
    if cfg.github_token_invalid:
        return {"valid": False, "reason": "Token 在上次请求中返回 401，请更新", "status": "invalid"}

    client = GitHubClient()
    if not client._api_headers.get("Authorization"):
        return {"valid": False, "reason": "未配置", "status": "empty"}
    try:
        result = await client.check_rate_limit()
        if "error" in result:
            return {"valid": False, "reason": "验证失败", "status": "error"}
        if result.get("core_limit", 0) == 0:
            cfg.github_token_invalid = True
            return {"valid": False, "reason": "Token 已失效或无效", "status": "invalid"}
        cfg.github_token_invalid = False  # 验证成功，清除失效标记
        return {
            "valid": True,
            "status": "ok",
            "remaining": result.get("core_remaining", 0),
            "limit": result.get("core_limit", 0),
            "reason": f"有效，剩余 {result.get('core_remaining', 0)}/{result.get('core_limit', 0)} 次",
        }
    except Exception as e:
        return {"valid": False, "reason": str(e), "status": "error"}
    """脱敏：只显示前4位和后4位"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


# ── 接口 ─────────────────────────────────────────────────────────────

@router.get("/config")
def get_config():
    """获取当前配置（敏感字段脱敏）"""
    env = _read_env()
    result = {}
    for key in ALLOWED_KEYS:
        value = env.get(key, "")
        result[key] = {
            "value": _mask(value) if key in SECRET_KEYS else value,
            "is_set": bool(value),
            "is_secret": key in SECRET_KEYS,
        }
    return result


class ConfigUpdateRequest(BaseModel):
    key: str
    value: str


@router.post("/config")
def update_config(req: ConfigUpdateRequest):
    """更新单个配置项并热加载"""
    key = req.key.upper().strip()
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"不允许修改的配置项: {key}")

    try:
        _write_env_key(key, req.value.strip())
        _reload_settings()
        # 更新 Token 时清除失效标记
        if key == "GITHUB_TOKEN":
            import config
            config.settings.github_token_invalid = False
        return {
            "success": True,
            "message": f"{key} 已更新并生效",
            "is_set": bool(req.value.strip()),
        }
    except Exception as e:
        raise HTTPException(500, f"更新失败: {e}")


@router.delete("/config/{key}")
def clear_config(key: str):
    """清空某个配置项"""
    key = key.upper().strip()
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"不允许修改的配置项: {key}")
    try:
        _write_env_key(key, "")
        _reload_settings()
        return {"success": True, "message": f"{key} 已清空"}
    except Exception as e:
        raise HTTPException(500, f"清空失败: {e}")
