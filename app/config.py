from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 720
    data_dir: str = "data"
    max_upload_mb: int = 50

    @property
    def uploads_dir(self) -> Path:
        return BASE_DIR / self.data_dir / "uploads"

    @property
    def results_dir(self) -> Path:
        return BASE_DIR / self.data_dir / "results"

    @property
    def db_path(self) -> Path:
        return BASE_DIR / self.data_dir / "app.db"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
