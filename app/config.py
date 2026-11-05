import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "SIP Discovery Engine"
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    RUNTIME_DIR: Path = BASE_DIR / "runtime"
    
    # Secrets & Model configs
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY") or None
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    MOCK_LLM: bool = os.getenv("MOCK_LLM", "false").lower() in ("true", "1", "yes")

    @property
    def is_ai_available(self) -> bool:
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip()) or self.MOCK_LLM

settings = Settings()

