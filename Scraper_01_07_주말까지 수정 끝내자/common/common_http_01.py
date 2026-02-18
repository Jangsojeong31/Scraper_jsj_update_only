# common_http.py
# [ common_http ]
# Network / HTTP / Selenium 상태 판단
# → URLStatus 반환

# [ health_check (moleg_health_check) ]
# URLStatus → HealthErrorType 매핑
# → HealthCheckError raise

import time
import requests
from typing import List, Dict, Optional

from selenium.webdriver.chrome.options import Options

from common.constants import (
    URLStatus,
    HTTP_STATUS_MESSAGE,
    NetworkState,
)
from common.network_state_detector import detect_network_state

from common.common_logger import get_logger
from common.base_scraper import BaseScraper


# ==================================================
# Logger
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
# NetworkState → URLStatus 매핑
# ==================================================
NETWORKSTATE_TO_URLSTATUS = {
    NetworkState.OK: URLStatus.OK,

    NetworkState.INTERNET_DISCONNECTED: URLStatus.NETWORK_DOWN,
    NetworkState.DNS_ERROR: URLStatus.DNS_FAIL,

    NetworkState.ACCESS_BLOCKED: URLStatus.ACCESS_BLOCKED,

    NetworkState.TIMEOUT: URLStatus.RETRY,

    NetworkState.SSL_ERROR: URLStatus.FAIL,
    NetworkState.UNKNOWN: URLStatus.FAIL,
}


def _map_network_state(state: NetworkState) -> URLStatus:
    return NETWORKSTATE_TO_URLSTATUS.get(state, URLStatus.FAIL)


# ==================================================
# Public API
# ==================================================
def check_url_status(
    url: str,
    timeout: int = REQUEST_TIMEOUT,
    use_selenium: bool = False,
    allow_fallback: bool = True
) -> dict:
    logger.info(url, extra={"tag": "CHECK"})

    if use_selenium:
        logger.info("Selenium forced", extra={"tag": "SEL"})
        return _selenium_fetch(url)

    result = _requests_fetch(url, timeout)

    if allow_fallback and result["status"] in (
        URLStatus.ACCESS_BLOCKED,
        URLStatus.HTTP_ERROR,
        URLStatus.FAIL,   # ⚠ SSL 포함됨
    ):
        logger.warning(
            f"Selenium fallback ({result['status'].name})",
            extra={"tag": "FALLBACK"}
        )
        return _selenium_fetch(url)

    return result


def check_url_status_bulk(
    urls: List[str],
    timeout: int = REQUEST_TIMEOUT,
    allow_fallback: bool = True,
    sleep: float = 0.3,
) -> Dict[str, dict]:

    results: Dict[str, dict] = {}

    logger.info(f"Bulk start: {len(urls)} urls", extra={"tag": "BULK"})

    for idx, url in enumerate(urls, start=1):
        logger.info(f"[{idx}/{len(urls)}] {url}", extra={"tag": "BULK"})

        result = check_url_status(
            url,
            timeout=timeout,
            allow_fallback=allow_fallback
        )
        results[url] = result
        time.sleep(sleep)

    logger.info("Bulk end", extra={"tag": "BULK"})
    return results


# ==================================================
# requests 기반 fetch
# ==================================================
def _requests_fetch(url: str, timeout: int) -> dict:
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

        # HTTP 오류 → NetworkState 추정
        state = detect_network_state(message=str(code))

        return _fail_result(
            status=_map_network_state(state),
            http_code=code,
            url=url,
            elapsed=elapsed,
            engine="requests",
            error=state.name
        )

    except requests.exceptions.Timeout as e:
        state = detect_network_state(exception=e, message=str(e))
        return _fail_result(
            status=_map_network_state(state),
            http_code=None,
            url=url,
            elapsed=None,
            engine="requests",
            error=state.name
        )

    except requests.exceptions.RequestException as e:
        state = detect_network_state(exception=e, message=str(e))
        return _fail_result(
            status=_map_network_state(state),
            http_code=None,
            url=url,
            elapsed=None,
            engine="requests",
            error=state.name
        )


# ==================================================
# Selenium 기반 fetch
# ==================================================
def _selenium_fetch(url: str) -> dict:
    start = time.time()
    logger.info("start", extra={"tag": "SEL"})

    scraper = BaseScraper()

    options = Options()
    options.add_argument('--headless')
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--log-level=3")

    driver = scraper._create_webdriver(options)

    try:
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        driver.get(url)
        time.sleep(1)

        return _ok_result(
            text=driver.page_source,
            final_url=driver.current_url,
            elapsed=round(time.time() - start, 3),
            engine="selenium",
            http_code=200
        )

    except Exception as e:
        state = detect_network_state(exception=e, message=str(e))

        logger.error(
            f"{state.name}: {str(e)}",
            extra={"tag": "SEL"}
        )

        # ✅ 여기서 끝. raise 금지.
        return _fail_result(
            status=_map_network_state(state),
            http_code=None,
            url=url,
            elapsed=None,
            engine="selenium",
            error=state.name
        )

    finally:
        try:
            driver.quit()
        except Exception:
            pass


# def _selenium_fetch(url: str) -> dict:
#     print(f"⚠ : _selenium_fetch ")
#     start = time.time()
#     logger.info("start", extra={"tag": "SEL"})

#     scraper = BaseScraper()

#     options = Options()
#     options.add_argument("--disable-gpu")
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")
#     options.add_argument("--disable-extensions")
#     options.add_argument("--log-level=3")

#     driver = scraper._create_webdriver(options)

#     try:
#         driver.set_page_load_timeout(SELENIUM_TIMEOUT)
#         driver.get(url)
#         time.sleep(1)

#         elapsed = round(time.time() - start, 3)
#         logger.info("success", extra={"tag": "SEL"})

#         return _ok_result(
#             text=driver.page_source,
#             final_url=driver.current_url,
#             elapsed=elapsed,
#             engine="selenium",
#             http_code=200
#         )

#     except Exception as e:
#         state = detect_network_state(exception=e, message=str(e))

#         logger.error(
#             f"{state.name}: {str(e)}",
#             extra={"tag": "SEL"}
#         )

#         return _fail_result(
#             status=_map_network_state(state),
#             http_code=None,
#             url=url,
#             elapsed=None,
#             engine="selenium",
#             error=state.name
#         )

#     finally:
#         try:
#             driver.quit()
#         except Exception:
#             pass

# ==================================================
# Result helpers
# ==================================================
def _http_message(code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    return HTTP_STATUS_MESSAGE.get(code, "Unknown Status")


def _ok_result(text, final_url, elapsed, engine, http_code) -> dict:
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
) -> dict:
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
