"""Thin requests.Session wrapper: cookie auth, polite delay, retry on transient errors."""
from __future__ import annotations

import logging
import random
import time

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import BASE_URL, HTTP

log = logging.getLogger(__name__)

# Windows + Python often can't read the system trust store, so ssodam's chain
# fails verification even though the cert is fine. truststore patches Python's
# SSL to use Windows' own certificate store, which is what the browser uses.
try:
    import truststore
    truststore.inject_into_ssl()
    log.debug("truststore injected — using system CA bundle")
except ImportError:
    log.debug("truststore not installed; falling back to certifi bundle")


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": HTTP.user_agent,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Referer": BASE_URL,
    })
    if HTTP.cookie:
        s.headers["Cookie"] = HTTP.cookie
    else:
        log.warning("SSODAM_COOKIE is empty. Login-required pages will fail.")

    s.verify = HTTP.ssl_verify
    if not HTTP.ssl_verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        log.warning("SSL verification DISABLED (SSODAM_SSL_VERIFY=false).")

    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


class PoliteFetcher:
    """Sleeps between requests with a small jitter so we don't hammer the host."""

    def __init__(self, session: requests.Session | None = None, delay: float | None = None):
        self.session = session or build_session()
        self.delay = HTTP.request_delay if delay is None else delay
        self._last_request_at: float = 0.0

    def get(self, url: str, **kwargs) -> requests.Response:
        self._wait()
        log.debug("GET %s", url)
        resp = self.session.get(url, timeout=15, **kwargs)
        self._last_request_at = time.monotonic()
        resp.raise_for_status()
        # Korean pages are usually UTF-8 but requests sometimes guesses wrong.
        if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        return resp

    def _wait(self) -> None:
        if self._last_request_at == 0.0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = self.delay - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.4))
