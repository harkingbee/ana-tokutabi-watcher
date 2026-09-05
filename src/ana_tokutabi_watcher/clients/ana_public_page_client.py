from __future__ import annotations

import hashlib
import re

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ana_tokutabi_watcher.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "ana-tokutabi-watcher/0.1 (+https://github.com/ana-tokutabi-watcher)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "ja,en;q=0.9",
}


class FetchError(RuntimeError):
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError, FetchError)),
    reraise=True,
)
def _fetch_with_retry(url: str, timeout: float = 30.0) -> str:
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        if resp.status_code in (429, 403) or resp.status_code >= 500:
            raise FetchError(f"retryable status {resp.status_code} for {url}")
        resp.raise_for_status()
        # 文字化け対策
        resp.encoding = resp.encoding or "utf-8"
        return resp.text


def fetch_campaign_page(
    url: str = "https://www.ana.co.jp/ja/jp/guide/amc/award/domestic/toku-tabi/",
    timeout: float = 30.0,
) -> tuple[str, str]:
    """公開ページを取得し、(html, hash)を返す。"""
    html = _fetch_with_retry(url, timeout=timeout)
    h = hashlib.sha256(html.encode("utf-8")).hexdigest()
    # HTML全文をログに出さない。診断用に要約のみ
    headings = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", html, flags=re.DOTALL | re.IGNORECASE)
    clean_headings = [re.sub(r"<[^>]+>", "", h).strip()[:80] for h in headings[:10]]
    logger.info(
        "campaign_page_fetched",
        extra={
            "url": url,
            "hash_prefix": h[:12],
            "html_len": len(html),
            "headings": clean_headings,
        },
    )
    # 上記は structlog では extra不要だが互換のため
    try:
        logger.info(
            "campaign_page_fetched_summary",
            url=url,
            hash_prefix=h[:12],
            html_len=len(html),
            headings=clean_headings,
        )
    except TypeError:
        pass
    return html, h
