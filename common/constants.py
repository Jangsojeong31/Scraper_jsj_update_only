# 공통 상태 상수 (constants.py)
# common/constants.py

from typing import Dict

HTTP_STATUS_MESSAGE: Dict[int, str] = {
    # 1xx
    100: "Continue",
    101: "Switching Protocols",
    102: "Processing",

    # 2xx
    200: "OK",
    201: "Created",
    202: "Accepted",
    203: "Non-Authoritative Information",
    204: "No Content",
    205: "Reset Content",
    206: "Partial Content",
    207: "Multi-Status",

    # 3xx
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    304: "Not Modified",
    305: "Use Proxy",
    307: "Temporary Redirect",

    # 4xx
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    413: "Request Entity Too Large",
    414: "Request-URI Too Large",
    415: "Unsupported Media Type",
    416: "Range Not Satisfiable",
    422: "Unprocessable Entity",
    423: "Locked",
    424: "Failed Dependency",
    426: "Upgrade Required",
    428: "Precondition Required",
    429: "Too Many Requests",
    431: "Request Header Fields Too Large",
    444: "Connection Closed Without Response",
    451: "Unavailable For Legal Reasons",

    # 5xx
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
    505: "HTTP Version Not Supported",
    507: "Insufficient Storage",
}

from enum import Enum

# HTTP 상태
HTTP_OK = "OK"
HTTP_DELAY = "DELAY"
HTTP_FAIL = "FAIL"

# timeout (seconds)
DEFAULT_TIMEOUT = 10

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CHROME_OPTIONS = [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--window-size=1920x1080",
]

# =========================
# Retry 정책
# =========================
RETRY_COUNT = 3
RETRY_SLEEP = 2

class LegalDocProvided:
    LAW = "LAW" #"법제처"
    FSS = "FSS" #"금융감독원"
    FSC = "FSC" #"금융위원회"
    KFB = "KFB" #"은행연합회"
    KOFIA = "KOFIA" #"금융투자협회"
    CREFIA = "CREFIA" #"여신금융협회"
    FSB = "FSB" #"저축은행중앙회"
    KRX = "KRX" #"한국거래소"
    BOK = "BOK" #"한국은행"

#class URLStatus:
#    OK = "OK"
#    TIMEOUT = "TIMEOUT"
#    ERROR = "ERROR"
#    SKIPPED = "SKIPPED"

class URLStatus(Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    RATE_LIMIT = "rate_limit"
    RETRY = "retry"
    FAIL = "fail"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"    