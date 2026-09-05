from __future__ import annotations

from ana_tokutabi_watcher.logging_config import get_logger

logger = get_logger(__name__)


class BrowserAvailabilityClient:
    """Playwright等を使う将来用のスタブ。規約上デフォルト無効。"""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def check(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self.enabled:
            logger.warning("browser_availability_disabled_fallback_to_safe")
            return None
        # CAPTCHA/bot検知が出たら即停止してsafeへフォールバックする設計
        raise NotImplementedError(
            "browser_public_only は現在無効です。safe_link_only を使用してください。"
        )
