from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "ai_github"

    github_token: str = ""

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 爬取配置
    min_stars_topic: int = 500
    min_stars_keyword: int = 200

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def db_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 运行时状态（不属于配置，不从 .env 读取，重启后自动重置）
class _RuntimeState:
    github_token_invalid: bool = False

runtime = _RuntimeState()
