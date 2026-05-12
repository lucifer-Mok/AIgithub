"""
系统配置接口
直接读写 .env 文件，修改后热加载，无需重启
"""

import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

ENV_PATH = Path(__file__).parent.parent / ".env"

ALLOWED_KEYS = {
    "GITHUB_TOKEN",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "MIN_STARS_TOPIC",
    "MIN_STARS_KEYWORD",
}

SECRET_KEYS = {"GITHUB_TOKEN", "DEEPSEEK_API_KEY"}


def _read_env() -> dict[str, str]:
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
    if not ENV_PATH.exists():
        raise FileNotFoundError(".env file not found")
    content = ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(rf"^({re.escape(key)}\s*=).*$", re.MULTILINE)
    if pattern.search(content):
        new_content = pattern.sub(rf"\g<1>{value}", content)
    else:
        new_content = content.rstrip() + f"\n{key}={value}\n"
    ENV_PATH.write_text(new_content, encoding="utf-8")


def _reload_settings():
    from dotenv import load_dotenv
    load_dotenv(str(ENV_PATH), override=True)
    import config
    new = config.Settings()
    config.settings.github_token = new.github_token
    config.settings.deepseek_api_key = new.deepseek_api_key
    config.settings.deepseek_base_url = new.deepseek_base_url
    config.settings.deepseek_model = new.deepseek_model
    config.settings.min_stars_topic = new.min_stars_topic
    config.settings.min_stars_keyword = new.min_stars_keyword


def _mask(value: str) -> str:
    """脱敏：只显示前4位和后4位"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


# ── 接口 ─────────────────────────────────────────────────────────────

@router.get("/config/verify/github")
async def verify_github_token():
    """验证 GitHub Token 是否有效"""
    from crawler.github_client import GitHubClient
    from config import settings as cfg, runtime

    if runtime.github_token_invalid:
        return {"valid": False, "reason": "Token 在上次请求中返回 401，请更新", "status": "invalid"}

    client = GitHubClient()
    if not client._api_headers.get("Authorization"):
        return {"valid": False, "reason": "未配置", "status": "empty"}
    try:
        result = await client.check_rate_limit()
        if "error" in result:
            if result.get("token_invalid"):
                runtime.github_token_invalid = True
                return {"valid": False, "reason": "Token 无效（401）", "status": "invalid"}
            return {"valid": False, "reason": f"验证失败: {result['error']}", "status": "error"}
        if result.get("core_limit", 0) == 0:
            # 无 Token 时 limit 也是 60，不应该是 0，说明解析异常
            return {"valid": False, "reason": "无法获取速率限制信息", "status": "error"}
        runtime.github_token_invalid = False
        return {
            "valid": True,
            "status": "ok",
            "remaining": result.get("core_remaining", 0),
            "limit": result.get("core_limit", 0),
            "reason": f"有效，剩余 {result.get('core_remaining', 0)}/{result.get('core_limit', 0)} 次",
        }
    except Exception as e:
        return {"valid": False, "reason": str(e), "status": "error"}


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
        if key == "GITHUB_TOKEN":
            import config
            config.runtime.github_token_invalid = False
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
