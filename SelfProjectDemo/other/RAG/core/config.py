"""全局配置：读取 .env，定义路径与默认参数。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploaded"
PARSED_DIR = DATA_DIR / "parsed"
VECTOR_DIR = DATA_DIR / "vectorstore"

for _d in (UPLOAD_DIR, PARSED_DIR, VECTOR_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    """轻量 .env 解析，避免额外依赖 python-dotenv。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:  # 环境变量优先
            os.environ[key] = value


_load_dotenv()


class Settings:
    """应用设置（全部可通过 .env 覆盖）。"""

    API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "zai-org/GLM-5.3-Flash")
    BASE_URL: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

    TOP_K: int = int(os.getenv("TOP_K", "4"))
    SCORE_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", "0.35"))

    # 固定长度分块默认参数
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "80"))

    UPLOAD_DIR = UPLOAD_DIR
    PARSED_DIR = PARSED_DIR
    VECTOR_DIR = VECTOR_DIR

    SUPPORTED_EXT = {".pdf", ".docx", ".txt", ".md", ".markdown"}


settings = Settings()
