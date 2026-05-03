import os

from dotenv import load_dotenv

load_dotenv()


def _infer_llm_chat_path():
    explicit = os.getenv("LLM_CHAT_PATH", "").strip()
    if explicit:
        return explicit if explicit.startswith("/") else f"/{explicit}"
    base = os.getenv("LLM_API_BASE", "").lower()
    if any(x in base for x in ("siliconflow", "openai.com", "api.deepseek.com", "groq.com")):
        return "/chat/completions"
    return "/chat"


class Config:
    @staticmethod
    def _parse_cors_origins():
        raw = os.getenv("CORS_ORIGINS", "")
        if raw.strip():
            return [item.strip() for item in raw.split(",") if item.strip()]
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ]

    SECRET_KEY = os.getenv("SECRET_KEY", "")
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"

    LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.siliconflow.cn/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
    LLM_CHAT_TYPE = os.getenv("LLM_CHAT_TYPE", "business")
    LLM_CHAT_PATH = _infer_llm_chat_path()
    ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", LLM_MODEL)
    ORCHESTRATOR_ENABLED = os.getenv("ORCHESTRATOR_ENABLED", "false").lower() == "true"
    ORCHESTRATOR_API_BASE = os.getenv("ORCHESTRATOR_API_BASE", "")
    ORCHESTRATOR_API_KEY = os.getenv("ORCHESTRATOR_API_KEY", "")
    ORCHESTRATOR_CHAT_PATH = os.getenv("ORCHESTRATOR_CHAT_PATH", "/chat")
    ORCHESTRATOR_CHAT_TYPE = os.getenv("ORCHESTRATOR_CHAT_TYPE", "business")
    ORCHESTRATOR_TIMEOUT_SECONDS = float(os.getenv("ORCHESTRATOR_TIMEOUT_SECONDS", "10"))
    ORCHESTRATOR_CONFIDENCE_THRESHOLD = float(os.getenv("ORCHESTRATOR_CONFIDENCE_THRESHOLD", "0.6"))
    DEFAULT_SCENE_ID = os.getenv("DEFAULT_SCENE_ID", "zhimei")
    SESSION_STORE = os.getenv("SESSION_STORE", "memory")
    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    SESSION_PREFIX = os.getenv("SESSION_PREFIX", "zhimei:session:")
    SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "86400"))
    HISTORY_STORE = os.getenv("HISTORY_STORE", SESSION_STORE)
    HISTORY_KEY = os.getenv("HISTORY_KEY", "zhimei:history")
    HISTORY_MAX_ITEMS = int(os.getenv("HISTORY_MAX_ITEMS", "200"))
    EXTERNAL_USER_DEFAULT = os.getenv("EXTERNAL_USER_DEFAULT", "zhimei_dev_demo001")

    GAME_TOTAL_TIME = int(os.getenv("GAME_TOTAL_TIME", "46"))
    GAME_INITIAL_CREDIBILITY = int(os.getenv("GAME_INITIAL_CREDIBILITY", "100"))

    SSE_RETRY_TIMEOUT = int(os.getenv("SSE_RETRY_TIMEOUT", "30000"))

    CORS_ORIGINS = _parse_cors_origins()
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls):
        """启动时校验关键配置，失败则抛出异常阻止服务启动。"""
        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 16:
            raise ValueError(
                "SECRET_KEY 未设置或长度不足 16 位。"
                "请在 .env 文件中设置强密钥，例如：SECRET_KEY=your-256-bit-secret"
            )
        if cls.DEBUG and os.getenv("FLASK_ENV") == "production":
            import warnings
            warnings.warn("DEBUG=true 但 FLASK_ENV=production，建议关闭 DEBUG 模式", RuntimeWarning)
