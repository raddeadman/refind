from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All secrets and connection details come from .env (§4.2)."""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_db: str = "refind"
    mongo_test_db: str = "refind_test"
    # Database that holds the refindApp/refindAdmin accounts (setup_db.py).
    mongo_auth_db: str = "refind"
    mongo_root_user: str = "root"
    mongo_root_password: str = "change-me-root"
    mongo_app_password: str = "change-me-app"
    mongo_admin_password: str = "change-me-admin"
    mongo_reports_password: str = "change-me-reports"
    mongo_backup_password: str = "change-me-backup"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    allowed_email_domains: list[str] = ["university.edu"]
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    enable_scheduler: bool = True
    cors_origins: list[str] = ["http://localhost:5173"]
    # The SPA; in development Vite also proxies /api, so OAuth redirects
    # and the session cookie all stay on this one origin.
    frontend_url: str = "http://localhost:5173"
    email_from: str = "ReFind <no-reply@refind.local>"
    # Google sign-in is switched off until both are set.
    google_client_id: str | None = None
    google_client_secret: str | None = None

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    def email_domain_allowed(self, email: str) -> bool:
        domain = email.rsplit("@", 1)[-1].lower()
        return any(domain == d or domain.endswith("." + d) for d in self.allowed_email_domains)

    def mongo_uri(self, user: str, password: str, auth_db: str) -> str:
        # directConnection: the single replica-set member advertises
        # localhost:27017, which works from the host and from scripts.
        return (
            f"mongodb://{quote_plus(user)}:{quote_plus(password)}"
            f"@{self.mongo_host}:{self.mongo_port}/"
            f"?authSource={auth_db}&directConnection=true"
        )

    @property
    def app_uri(self) -> str:
        """refindApp: readWrite on refind (used by the API)."""
        return self.mongo_uri("refindApp", self.mongo_app_password, self.mongo_auth_db)

    @property
    def admin_uri(self) -> str:
        """refindAdmin: dbAdmin on refind (set-up script only)."""
        return self.mongo_uri("refindAdmin", self.mongo_admin_password, self.mongo_auth_db)

    @property
    def root_uri(self) -> str:
        return self.mongo_uri(self.mongo_root_user, self.mongo_root_password, "admin")


@lru_cache
def get_settings() -> Settings:
    return Settings()
