"""应用配置。

基于 ``pydantic-settings`` 从环境变量与 ``.env`` 文件加载配置。
所有存储路径默认落在 ``~/.resume-agent/``，可通过环境变量覆盖。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置。

    字段名与环境变量一一对应（无前缀）。支持从 ``.env`` 文件读取。
    存储路径若以 ``~`` 开头，会自动展开为用户家目录。
    """

    # === LLM 配置 ===
    llm_provider: str = "openai"  # openai / claude / deepseek / custom
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o"  # deepseek 用 deepseek-chat

    # === Embedding 配置 ===
    embedding_provider: str = "openai"  # openai / deepseek
    embedding_model: str = "text-embedding-3-small"

    # === MinerU 文档解析 API ===
    mineru_api_token: str = ""
    mineru_api_base: str = "https://mineru.net"

    # === Tavily Web 搜索 API（US-11 导师建议增强）===
    tavily_api_key: str = ""

    # === 数据存储 ===
    resume_agent_home: Path = Path.home() / ".resume-agent"
    sqlite_path: Path = Path.home() / ".resume-agent" / "data.db"
    chroma_path: Path = Path.home() / ".resume-agent" / "chroma"
    files_root: Path = Path.home() / ".resume-agent" / "files"

    # === 服务 ===
    host: str = "0.0.0.0"
    port: int = 5173
    debug: bool = False
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 路径展开 ---
    @field_validator(
        "resume_agent_home",
        "sqlite_path",
        "chroma_path",
        "files_root",
        mode="before",
    )
    @classmethod
    def _expand_user(cls, value: object) -> object:
        """展开路径中的 ``~`` 为用户家目录。"""
        if isinstance(value, str):
            return Path(value).expanduser()
        if isinstance(value, Path):
            return value.expanduser()
        return value

    # --- 派生属性 ---
    @property
    def llm_configured(self) -> bool:
        """是否已配置 LLM API Key。"""
        return bool(self.llm_api_key)

    @property
    def cors_origin_list(self) -> list[str]:
        """解析 CORS 来源字符串为列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        """确保所有存储目录存在。"""
        self.resume_agent_home.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.files_root.mkdir(parents=True, exist_ok=True)


settings = Settings()
