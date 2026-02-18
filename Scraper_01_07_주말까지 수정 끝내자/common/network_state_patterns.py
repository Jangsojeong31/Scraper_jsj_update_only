# network_state_patterns.py
# 공통 패턴 테이블 (Selenium / Requests 공용)

from common.constants import NetworkState


NETWORK_STATE_PATTERNS = {

    NetworkState.INTERNET_DISCONNECTED: [
        "err_internet_disconnected",
        "internet disconnected",
        "network disconnected",
    ],

    NetworkState.DNS_FAIL: [
        "getaddrinfo failed",
        "name resolution failed",
        "dns resolution failed",
    ],

    NetworkState.NETWORK_UNREACHABLE: [
        "network is unreachable",
        "no route to host",
        "connection refused",
        "failed to establish a new connection",
    ],

    NetworkState.ACCESS_BLOCKED: [
        "access_blocked",
        "blocked by policy",
        "security policy",
        "corporate policy",
        "보안 정책",
        "접근이 차단",
    ],

    NetworkState.TIMEOUT: [
        "timed out",
        "timeout",
        "read timeout",
    ],
}
