from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitorConfig(BaseModel):
    origins: list[str] = Field(default_factory=lambda: ["ITM", "KIX", "UKB"])
    trip_type: Literal["one_way", "round_trip"] = "one_way"
    departure_time_start: str = "06:00"
    departure_time_end: str = "21:00"
    destination_allowlist: list[str] = Field(default_factory=list)
    destination_blocklist: list[str] = Field(default_factory=list)
    max_notifications_per_run: int = 20
    resend_after_hours: int = 24
    dry_run: bool = False


class WeeklyRouteFetchSchedule(BaseModel):
    day_of_week: str = "wed"
    hour: int = 0
    minute: int = 0
    retries: list[str] = Field(default_factory=lambda: ["00:01", "00:05", "00:15"])


class AvailabilityCheckSchedule(BaseModel):
    enabled_during_booking_window_only: bool = True
    minute: int = 0


class ScheduleConfig(BaseModel):
    weekly_route_fetch: WeeklyRouteFetchSchedule = Field(default_factory=WeeklyRouteFetchSchedule)
    availability_check: AvailabilityCheckSchedule = Field(default_factory=AvailabilityCheckSchedule)


class RateLimitConfig(BaseModel):
    min_seconds_between_requests: int = 10
    max_requests_per_run: int = 30
    retry_max_attempts: int = 3


class DiscordConfig(BaseModel):
    enabled: bool = True
    username: str = "ANAトクたび監視"
    webhook_url_env: str = "DISCORD_WEBHOOK_URL"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "json"


class AppConfig(BaseModel):
    timezone: str = "Asia/Tokyo"
    campaign_url: str = "https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/"
    availability_mode: Literal["safe_link_only", "browser_public_only", "custom_api"] = "safe_link_only"
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_webhook_url: str = Field(default="", alias="DISCORD_WEBHOOK_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    database_url: str = Field(default="sqlite:///./data/ana_tokutabi.db", alias="DATABASE_URL")


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """YAML設定ファイルを読み込む。存在しなければデフォルトを返す。"""
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path))
    else:
        candidates.extend(
            [
                Path("config.yaml"),
                Path("config.yml"),
                Path("config.example.yaml"),
            ]
        )
    for p in candidates:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return AppConfig.model_validate(data)
    return AppConfig()


def get_discord_webhook_url(config: AppConfig) -> str:
    env = EnvSettings()  # type: ignore[call-arg]
    # 環境変数名はconfigで可変
    key = config.discord.webhook_url_env
    if key == "DISCORD_WEBHOOK_URL":
        return env.discord_webhook_url
    return os.getenv(key, "")


def get_database_url() -> str:
    env = EnvSettings()  # type: ignore[call-arg]
    return env.database_url


def get_log_level(config: AppConfig) -> str:
    env = EnvSettings()  # type: ignore[call-arg]
    # 環境変数が設定されていればそちらを優先
    if os.getenv("LOG_LEVEL"):
        return env.log_level
    return config.logging.level


def get_log_format(config: AppConfig) -> str:
    env = EnvSettings()  # type: ignore[call-arg]
    if os.getenv("LOG_FORMAT"):
        return env.log_format
    return config.logging.format
