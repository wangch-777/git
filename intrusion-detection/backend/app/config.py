"""应用配置。默认值面向本地单机部署，可用环境变量覆盖。"""
import os
from pathlib import Path

# intrusion-detection/backend/app/config.py -> 项目根为 parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings:
    def __init__(self) -> None:
        self.project_root = PROJECT_ROOT
        self.data_raw = PROJECT_ROOT / "data" / "raw"
        self.data_processed = PROJECT_ROOT / "data" / "processed"
        self.artifacts = PROJECT_ROOT / "artifacts"
        self.configs = PROJECT_ROOT / "configs"

        default_db = f"sqlite:///{(PROJECT_ROOT / 'ids.sqlite3').as_posix()}"
        self.sqlite_url = os.getenv("IDS_DB_URL", default_db)
        self.worker_poll_interval = float(
            os.getenv("IDS_WORKER_POLL_INTERVAL", "2.0")
        )

        for d in (self.data_raw, self.data_processed, self.artifacts):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()