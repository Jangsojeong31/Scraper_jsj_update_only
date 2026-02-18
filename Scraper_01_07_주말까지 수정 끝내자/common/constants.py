# 공통 상태 상수 (constants.py)
# common/constants.py
# 디렉토리 구조 (권장)
#common/
# ├─ constants.py
# ├─ health_policy.py
# ├─ health_utils.py
# ├─ dom_snapshot.py
# ├─ selector_diff.py
# ├─ selector_scoring.py
# ├─ selector_autofix.py
#contracts/
# └─ bok_legnotice.json
#BOK_LegNotice_Scraper 
# └─ bok_legnotice_scraper_v2.py

# 각 HealthErrorType 의미 정리 (권장 정의)
# 타입	의미	발생 예
# HTTP_ERROR	HTTP 상태코드 오류	403, 404, 500
# NO_LIST_DATA	목록 페이지에 데이터 없음	<tr> 0건
# NO_DETAIL_URL	상세 페이지 링크 없음	<a href> 없음
# STRUCTURE_CHANGED	HTML 구조 변경	table → div
# TAG_MISMATCH	예상 태그 불일치	td 대신 span
# CONTENT_EMPTY	내용이 비어 있음	본문 텍스트 없음
# TIMEOUT	요청/렌더링 시간 초과	Selenium TimeoutException
# PARSE_ERROR	파싱 중 예외	AttributeError, IndexError
# EXCEPTION	그 외 예외	알 수 없는 오류

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

from enum import Enum, auto

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
    KOFIU = "KOFIU" #"금융정보분석원"

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

    HTTP_ERROR = "http_error"
    NETWORK_TIMEOUT = "network_timeout"   # 
    NETWORK_DOWN = "network_down"   # 인터넷 끊김
    # 정책 / 보안    
    ACCESS_BLOCKED = "access_blocked"  # 사내 보안 차단

    # 물리적 / 로컬 네트워크
    INTERNET_DISCONNECTED = "INTERNET_DISCONNECTED"     # 인터넷 단절
    NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"       # 라우팅 불가
    DNS_FAIL = "DNS_FAIL"                   # DNS 실패

    # 서버 / 원격
    REMOTE_SERVER_DOWN = "REMOTE_SERVER_DOWN"         # 서버 5xx
    RATE_LIMITED = "RATE_LIMITED"              # 429

    SSL_ERROR = "SSL_ERROR"
    DNS_ERROR = "DNS_ERROR"
    
    # Fallback
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    UNKNOWN = "UNKNOWN"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

class NetworkState(Enum):
    OK = auto()

    # 물리적 / 로컬 네트워크
    INTERNET_DISCONNECTED = "INTERNET_DISCONNECTED"     # 인터넷 단절
    NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"        # 라우팅 불가
    DNS_FAIL = "DNS_FAIL"                 # DNS 실패

    # 정책 / 보안
    ACCESS_BLOCKED = "ACCESS_BLOCKED"            # 사내 보안 차단

    # 서버 / 원격
    REMOTE_SERVER_DOWN = "REMOTE_SERVER_DOWN"         # 서버 5xx
    RATE_LIMITED = "RATE_LIMITED"              # 429

    SSL_ERROR = "SSL_ERROR"
    DNS_ERROR = "DNS_ERROR"
    
    # 기타
    TIMEOUT = "TIMEOUT"
    # Fallback
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
    UNKNOWN = "UNKNOWN"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

class HealthActionType:
    RETRY = "RETRY"
    ALERT = "ALERT"
    DEV = "DEV"
 