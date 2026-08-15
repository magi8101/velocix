"""Application settings with pydantic-settings"""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration"""

    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=4, description="Number of workers")
    reload: bool = Field(default=False, description="Auto-reload on code changes")

    database_url: str = Field(default="", description="PostgreSQL connection string")
    db_pool_min: int = Field(default=10, description="Minimum pool connections")
    db_pool_max: int = Field(default=20, description="Maximum pool connections")
    db_health_check_interval: int = Field(
        default=30, description="Health check interval in seconds"
    )

    jwt_secret: str = Field(default="", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire: int = Field(
        default=3600, description="Access token expiration in seconds"
    )
    jwt_refresh_token_expire: int = Field(
        default=604800, description="Refresh token expiration in seconds"
    )

    cors_enabled: bool = Field(default=False, description="Enable CORS")
    cors_origins: list[str] = Field(default=["*"], description="Allowed origins")
    cors_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "PATCH"], description="Allowed methods"
    )
    cors_headers: list[str] = Field(default=["*"], description="Allowed headers")
    cors_credentials: bool = Field(default=False, description="Allow credentials")

    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window: int = Field(default=60, description="Time window in seconds")
    rate_limit_burst: int = Field(default=0, description="Burst size (0 = same as requests)")

    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")

    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    def get_db_pool_config(self) -> dict[str, int]:
        """Get database pool configuration"""
        return {
            "min_size": self.db_pool_min,
            "max_size": self.db_pool_max,
            "health_check_interval": self.db_health_check_interval,
        }

    def get_cors_config(self) -> dict[str, Any]:
        """Get CORS configuration"""
        return {
            "allow_origins": self.cors_origins,
            "allow_methods": self.cors_methods,
            "allow_headers": self.cors_headers,
            "allow_credentials": self.cors_credentials,
        }

    def get_rate_limit_config(self) -> dict[str, int]:
        """Get rate limit configuration"""
        burst = self.rate_limit_burst if self.rate_limit_burst > 0 else self.rate_limit_requests
        return {"rate": self.rate_limit_requests, "per": self.rate_limit_window, "burst": burst}
