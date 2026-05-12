from sqlalchemy import (
    Column, Integer, String, Text, Float, Date,
    DateTime, JSON, Enum, ForeignKey, func
)
from sqlalchemy.orm import relationship
from database import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "ai_github"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    slug = Column(String(50), nullable=False, unique=True)
    description = Column(String(200))
    icon = Column(String(50))
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    repos = relationship("Repo", back_populates="category")


class Repo(Base):
    __tablename__ = "repos"
    __table_args__ = {"schema": "ai_github"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    github_id = Column(String(300), unique=True)
    owner = Column(String(100), nullable=False)
    repo_name = Column(String(200), nullable=False)
    full_name = Column(String(300), nullable=False)
    description = Column(Text)
    language = Column(String(50))
    html_url = Column(String(500))
    homepage = Column(String(500))
    stars_total = Column(Integer, default=0)
    forks_total = Column(Integer, default=0)
    watchers = Column(Integer, default=0)
    open_issues = Column(Integer, default=0)
    topics = Column(JSON)
    category_id = Column(Integer, ForeignKey("ai_github.categories.id"))
    sub_categories = Column(JSON)
    has_chinese_readme = Column(Integer, default=0)
    chinese_readme_path = Column(String(100))
    name_zh = Column(String(300))
    summary_zh = Column(Text)
    tags_zh = Column(JSON)
    desc_hash = Column(String(64))
    translated_at = Column(DateTime)
    ai_score = Column(Float, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="repos")
    daily_stats = relationship("DailyStat", back_populates="repo")


class DailyStat(Base):
    __tablename__ = "daily_stats"
    __table_args__ = {"schema": "ai_github"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("ai_github.repos.id"), nullable=False)
    stat_date = Column(Date, nullable=False)
    stars_today = Column(Integer, default=0)
    stars_total = Column(Integer, default=0)
    forks_today = Column(Integer, default=0)
    rank_position = Column(Integer)
    trending_language = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())

    repo = relationship("Repo", back_populates="daily_stats")


class CustomTrack(Base):
    """用户自定义追踪配置：支持追踪指定 repo、关键词、topic"""
    __tablename__ = "custom_tracks"
    __table_args__ = {"schema": "ai_github"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_type = Column(Enum("repo", "keyword", "topic"), nullable=False, comment="追踪类型")
    value = Column(String(500), nullable=False, comment="repo全名 或 关键词 或 topic")
    min_stars = Column(Integer, default=0, comment="关键词/topic搜索时的最低star数")
    source_repo = Column(String(300), comment="来源repo（从哪个repo提取的关键词）")
    description = Column(String(500), comment="备注说明")
    is_active = Column(Integer, default=1, comment="是否启用")
    last_crawled_at = Column(DateTime, comment="最后爬取时间")
    created_at = Column(DateTime, server_default=func.now())


class CrawlLog(Base):
    __tablename__ = "crawl_logs"
    __table_args__ = {"schema": "ai_github"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    crawl_date = Column(Date, nullable=False)
    status = Column(Enum("success", "failed", "partial"), default="success")
    total_fetched = Column(Integer, default=0)
    ai_filtered = Column(Integer, default=0)
    error_msg = Column(Text)
    duration_seconds = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
