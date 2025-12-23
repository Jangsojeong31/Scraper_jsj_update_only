# common_http.py

import os
import time
import requests
from typing import List, Dict, Optional
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from common.constants import (
    URLStatus,
    HTTP_STATUS_MESSAGE,
)

# ✅ 공통 로거 사용
from common.common_logger import get_logger


# ==================================================
# Logger (공통)
# ==================================================
logger = get_logger(
    name="common_http",
    log_file="common_http.log"
)

# ==================================================
# 기본 설정
# ==================================================
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BnkScraper/1.0)"
}

REQUEST_TIMEOUT = 10
SELENIUM_TIMEOUT = 12


# ==================================================
# Public API
# ==================================================
def check_url_status(
    url: str,
    timeout: int = REQUEST_TIMEOUT,
    use_selenium: bool = False,
    allow_fallback: bool = True
):
    """
    단일 URL 상태 체크
    """
    logger.info(url, extra={"tag": "CHECK"})

    if use_selenium:
        logger.info("Selenium forced", extra={"tag": "SEL"})
        return _selenium_fetch(url)

    result = _requests_fetch(url, timeout)

    if allow_fallback and result["status"] in (
        URLStatus.BLOCKED,
        URLStatus.RETRY,
        URLStatus.RATE_LIMIT,
    ):
        logger.warning(
            f"Selenium fallback ({result['http_code']} {result['http_message']})",
            extra={"tag": "FALLBACK"}
        )
        return _selenium_fetch(url)

    return result


def check_url_status_bulk(
    urls: List[str],
    timeout: int = REQUEST_TIMEOUT,
    allow_fallback: bool = True,
    sleep: float = 0.3,
):
    """
    멀티 URL 상태 사전 점검
    """
    results: Dict[str, dict] = {}

    logger.info(f"Bulk start: {len(urls)} urls", extra={"tag": "BULK"})

    for idx, url in enumerate(urls, start=1):
        logger.info(f"[{idx}/{len(urls)}] {url}", extra={"tag": "BULK"})

        result = _requests_fetch(url, timeout)

        if allow_fallback and result["status"] in (
            URLStatus.BLOCKED,
            URLStatus.RETRY,
            URLStatus.RATE_LIMIT,
        ):
            logger.warning(
                f"Selenium fallback ({result['http_code']} {result['http_message']})",
                extra={"tag": "FALLBACK"}
            )
            result = _selenium_fetch(url)

        results[url] = result
        time.sleep(sleep)

    logger.info("Bulk end", extra={"tag": "BULK"})
    return results


# ==================================================
# requests 기반 fetch
# ==================================================
def _requests_fetch(url: str, timeout: int):
    start = time.time()

    try:
        r = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            allow_redirects=True
        )

        elapsed = round(time.time() - start, 3)
        code = r.status_code

        logger.info(
            f"{code} {HTTP_STATUS_MESSAGE.get(code)}",
            extra={"tag": "REQ"}
        )

        if code == 200:
            return _ok_result(
                text=r.text,
                final_url=r.url,
                elapsed=elapsed,
                engine="requests",
                http_code=code
            )

        if code == 404:
            return _fail_result(URLStatus.NOT_FOUND, code, url, elapsed)

        if code in (401, 403):
            return _fail_result(URLStatus.BLOCKED, code, url, elapsed)

        if code == 429:
            return _fail_result(URLStatus.RATE_LIMIT, code, url, elapsed)

        if 500 <= code < 600:
            return _fail_result(URLStatus.RETRY, code, url, elapsed)

        return _fail_result(URLStatus.RETRY, code, url, elapsed)

    except requests.Timeout:
        logger.error("requests timeout", extra={"tag": "REQ"})
        return _fail_result(
            status=URLStatus.RETRY,
            http_code=None,
            url=url,
            elapsed=None,
            error="timeout"
        )

    except requests.RequestException as e:
        logger.error(str(e), extra={"tag": "REQ"})
        return _fail_result(
            status=URLStatus.FAIL,
            http_code=None,
            url=url,
            elapsed=None,
            error=str(e)
        )


# ==================================================
# Selenium 기반 fetch
# ==================================================
def _selenium_fetch(url: str):
    start = time.time()
    logger.info("start", extra={"tag": "SEL"})

    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--log-level=3")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    try:
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        driver.get(url)
        time.sleep(1)

        elapsed = round(time.time() - start, 3)
        logger.info("success", extra={"tag": "SEL"})

        return _ok_result(
            text=driver.page_source,
            final_url=driver.current_url,
            elapsed=elapsed,
            engine="selenium",
            http_code=200
        )

    except Exception as e:
        logger.error(str(e), extra={"tag": "SEL"})
        return _fail_result(
            status=URLStatus.FAIL,
            http_code=None,
            url=url,
            elapsed=None,
            engine="selenium",
            error=str(e)
        )

    finally:
        driver.quit()


# ==================================================
# Result helpers
# ==================================================
def _http_message(code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    return HTTP_STATUS_MESSAGE.get(code, "Unknown Status")


def _ok_result(text, final_url, elapsed, engine, http_code):
    return {
        "status": URLStatus.OK,
        "http_code": http_code,
        "http_message": _http_message(http_code),
        "text": text,
        "final_url": final_url,
        "engine": engine,
        "elapsed": elapsed,
        "error": None,
    }


def _fail_result(
    status: URLStatus,
    http_code,
    url,
    elapsed,
    engine="requests",
    error=None
):
    return {
        "status": status,
        "http_code": http_code,
        "http_message": _http_message(http_code),
        "text": None,
        "final_url": url,
        "engine": engine,
        "elapsed": elapsed,
        "error": error,
    }
