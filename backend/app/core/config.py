"""Application configuration driven by environment variables (.env)."""
from functools import lru_cache
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 统一约定：.env 放项目根目录（compose/本地均可用）。
        # 本地开发在 backend/ 下运行时会回退读取上级目录的 .env。
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # runtime
    app_name: str = "contract-review"
    app_env: str = "dev"
    debug: bool = True
    server_host: str = "0.0.0.0"
    server_port: int = 8080

    # mysql
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "contract"
    mysql_password: str = "change-me"
    mysql_db: str = "contract_review"
    database_url: str = ""

    # redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_fake: bool = False

    # jwt
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Agent 推理：DeepSeek 官方 OpenAI-compatible API
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_review_model: str = "deepseek-flash"
    llm_chat_model: str = "deepseek-flash"
    llm_intent_model: str = "deepseek-flash"
    llm_allowed_models: str = ""  # 可选逗号分隔白名单，限制推理成本；不约束向量/精排

    # RAG 向量化：阿里云百炼 OpenAI-compatible Embedding API
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024

    # RAG 精排：阿里云百炼 OpenAI-compatible Rerank API（完整 /reranks URL）
    rerank_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = "qwen3-rerank"

    # 兼容旧版单一 SiliconFlow 配置；新部署优先使用上面的独立变量
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"

    # qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_location: str = ""
    qdrant_collection_regulations: str = "kb_regulations"
    qdrant_collection_institution: str = "kb_institution"
    qdrant_collection_templates: str = "kb_templates"

    # rag
    rag_hybrid_top_k: int = 60
    kb_bm25_path: str = ""  # 空则自动推导为 OSS_BUCKET_DIR 上级的 kb_bm25.pkl
    rag_rerank_top_k: int = 5
    rag_query_variants: int = 3
    rag_query_expansion_timeout: float = 15.0
    rag_per_doc_quota: int = 3  # 分层配额：每个文档最多 N 个 chunk 进入 rerank
    rag_evidence_rerank_enabled: bool = True
    rag_evidence_rerank_docs: int = 30  # cross-encoder 后复核的最大文档数
    rag_evidence_rerank_timeout: float = 20.0
    rag_context_max_chars: int = 7000

    # langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # 本地文件存储（原始合同与解析文本）
    upload_dir: str = "/data/uploads"
    oss_bucket_dir: str = "/data/parsed"

    # 阿里云 OSS（STORAGE_BACKEND=oss 时启用）
    storage_backend: str = "local"
    oss_endpoint: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket_name: str = ""
    oss_prefix: str = "contract-review"

    # frontend / cas
    frontend_url: str = "http://localhost:5173"
    cas_server_url: str = ""

    # 文档解析引擎（有序回退链）
    doc_parser_engines: str = "pdfplumber,pymupdf,pypdf,docx,libreoffice,ocr"
    ocr_lang: str = "chi_sim"
    ocr_base_url: str = ""
    ocr_api_key: str = ""
    ocr_model: str = "qwen3.5-ocr"
    ocr_max_pages: int = 10
    # 兼容旧配置名
    deepseek_ocr_api_key: str = ""
    deepseek_ocr_model: str = "deepseek-ocr"

    # 中间件 / 缓存 / 限流
    auth_middleware_enabled: bool = True
    request_log_enabled: bool = True
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 120
    chat_cache_ttl: int = 1800

    # Agent 工具调用（Tool Calling）
    agent_tool_calling_enabled: bool = True
    agent_max_tool_iterations: int = 3  # 工具循环轮次上限（防死循环）
    agent_review_max_tokens: int = 4096
    agent_evidence_audit_enabled: bool = True
    agent_evidence_audit_timeout: float = 90.0
    tool_result_max_chars: int = 8000   # 单条工具结果截断长度

    # 流式 / 首 Token 工程
    metrics_enabled: bool = True
    metrics_window_size: int = 200      # 滑动窗口样本数
    llm_prompt_cache: bool = False      # 仅 SiliconFlow 等支持 cache_prompt 的供应商可开启
    llm_brief_disable_thinking: bool | None = None  # None仅官网自动处理；兼容中转可显式开启
    llm_brief_reasoning_effort: str | None = None  # 仅在当前供应商验证后显式配置
    llm_http_trust_env: bool = True  # 含系统代理；本地代理故障时可显式关闭
    max_concurrent_llm: int = 4         # LLM 并发上限（应用层信号量，防突发打满供应商）
    chat_stream_timeout: float = 30.0   # 聊天流式超时（秒）
    review_stream_timeout: float = 120.0  # 审阅流式超时（秒）

    # MCP
    mcp_enabled: bool = False
    mcp_server_urls: str = ""

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{quote(self.redis_password, safe='')}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url or self.siliconflow_base_url

    @property
    def effective_llm_api_key(self) -> str:
        return self.llm_api_key or self.siliconflow_api_key

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.effective_llm_base_url

    @property
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.effective_llm_api_key

    @property
    def effective_rerank_url(self) -> str:
        if self.rerank_url:
            return self.rerank_url
        return f"{self.effective_llm_base_url.rstrip('/')}/rerank"

    @property
    def effective_rerank_api_key(self) -> str:
        return self.rerank_api_key or self.effective_llm_api_key

    @property
    def effective_ocr_base_url(self) -> str:
        return self.ocr_base_url or self.effective_embedding_base_url

    @property
    def effective_ocr_api_key(self) -> str:
        return self.ocr_api_key or self.embedding_api_key or self.deepseek_ocr_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
