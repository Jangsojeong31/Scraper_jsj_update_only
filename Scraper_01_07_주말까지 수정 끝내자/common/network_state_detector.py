# network_state_detector.py
# 공통 NetworkState Detector (핵심 엔진)

from typing import Optional
from common.constants import NetworkState
from common.network_state_patterns import NETWORK_STATE_PATTERNS

from selenium.common.exceptions import WebDriverException, TimeoutException
from requests.exceptions import (
    ConnectionError,
    Timeout,
    SSLError,
)

from common.constants import NetworkState

SECURITY_BLOCK_PATTERNS = [
    "ACCESS_BLOCKED",
    "차단된 페이지",
    "보안 정책",
    "ERR_BLOCKED_BY_ADMINISTRATOR",
    "ERR_CONNECTION_RESET",
]

# def detect_network_state(
#     *,
#     exception: Exception | None = None,
#     message: str | None = None,
# ) -> NetworkState:
#     text = (message or "").upper()

#     # Selenium – 인터넷 단절
#     if isinstance(exception, WebDriverException):
#         if "ERR_INTERNET_DISCONNECTED" in str(exception):
#             return NetworkState.INTERNET_DISCONNECTED

#     # Requests – 인터넷 단절
#     if isinstance(exception, ConnectionError):
#         return NetworkState.INTERNET_DISCONNECTED

#     # Timeout
#     if isinstance(exception, (Timeout, TimeoutException)):
#         return NetworkState.TIMEOUT

#     # SSL
#     if isinstance(exception, SSLError):
#         return NetworkState.SSL_ERROR

#     # 사내 보안 차단
#     for pattern in SECURITY_BLOCK_PATTERNS:
#         if pattern in text:
#             return NetworkState.ACCESS_BLOCKED

#     return NetworkState.UNKNOWN

# common/network_state_detector.py

def detect_network_state(*, exception=None, message: str = "") -> NetworkState:
    """
    Selenium / Requests 공통 네트워크 상태 판별기
    - keyword-only 인자 사용 (시그니처 고정)
    """

    msg = (message or "").lower()

    if exception:
        msg += " " + str(exception).lower()

    if "err_internet_disconnected" in msg:
        return NetworkState.INTERNET_DISCONNECTED

    if "getaddrinfo failed" in msg or "name resolution" in msg:
        return NetworkState.DNS_ERROR

    if "access denied" in msg or "blocked" in msg or "forbidden" in msg:
        return NetworkState.ACCESS_BLOCKED

    if "ssl" in msg:
        return NetworkState.SSL_ERROR

    if "timeout" in msg:
        return NetworkState.TIMEOUT

    return NetworkState.UNKNOWN
