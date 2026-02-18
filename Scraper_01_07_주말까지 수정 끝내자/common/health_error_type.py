# common/health_error_type.py
from enum import Enum, auto


class HealthErrorType(str, Enum):
    """
    Health Check Error Type (운영/감사 표준)

    - OK / SKIPPED / ERROR 상태를 명확히 구분
    - Lock / Chrome Profile / Scheduler 충돌까지 커버
    """

    # ==================================================
    # ✅ 정상 / 통제 상태
    # ==================================================
    OK = "OK"
    SKIPPED = "SKIPPED"  # 의도적 미실행 (Lock, 중복 방지 등)

    AUTH_ERROR = "AUTH_ERROR"
    
    # ==================================================
    # LOCK / 실행 제어 계층
    # ==================================================
    LOCK_ACTIVE = "LOCK_ACTIVE"                     # 스크래퍼 Lock 존재 (정상 통제)
    CHROME_PROFILE_LOCK = "CHROME_PROFILE_LOCK"     # Chrome 프로파일 사용 중
    SCHEDULER_LOCK_ACTIVE = "SCHEDULER_LOCK_ACTIVE" # Scheduler 중복 실행 방지
    STALE_LOCK_RECOVERED = "STALE_LOCK_RECOVERED"   # Stale lock 자동 복구 후 실행
    LOCK_RELEASE_FAILED = "LOCK_RELEASE_FAILED"     # Lock 해제 실패

    # ==================================================
    # HTTP / 네트워크
    # ==================================================
    HTTP_ERROR = "HTTP_ERROR"           # HTTP 접근 실패
    HTTP_403_FORBIDDEN = "HTTP_403"     # 접근 차단
    HTTP_404_NOT_FOUND = "HTTP_404"     # 페이지 없음
    HTTP_5XX_SERVER_ERROR = "HTTP_5XX"  # 서버 오류
    HTTP_429_RATE_LIMIT = "HTTP_429"
    SSL_ERROR = "SSL_ERROR"             # 인증서 문제
    TIMEOUT = "TIMEOUT"                 # 응답 지연

    # ==================================================
    # 📄 목록 / 상세 구조
    # ==================================================
    NO_LIST_DATA = "NO_LIST_DATA"       # 목록 비어 있음
    NO_DETAIL_URL = "NO_DETAIL_URL"     # 상세 링크 누락
    TAG_MISMATCH = "TAG_MISMATCH"       # HTML 구조 변경
    CONTENT_EMPTY = "CONTENT_EMPTY"     # 본문 비어 있음

    # ==================================================
    # 📎 파일 / 다운로드
    # ==================================================
    FILE_DOWNLOAD_FAILED = "FILE_DOWNLOAD_FAILED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_SIZE_ZERO = "FILE_SIZE_ZERO"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"

    # ==================================================
    # 📑 PDF / OCR
    # ==================================================
    PDF_PARSE_ERROR = "PDF_PARSE_ERROR"
    OCR_REQUIRED = "OCR_REQUIRED"
    OCR_FAILED = "OCR_FAILED"

    # ==================================================
    # 🤖 Selenium / Browser
    # ==================================================
    SELENIUM_INIT_FAILED = "SELENIUM_INIT_FAILED"
    SELENIUM_CRASHED = "SELENIUM_CRASHED"
    DRIVER_VERSION_MISMATCH = "DRIVER_VERSION_MISMATCH"
    BROWSER_UNRESPONSIVE = "BROWSER_UNRESPONSIVE"

    # ==================================================
    # 데이터 처리
    # ==================================================
    PARSE_ERROR = "PARSE_ERROR"
    DATA_VALIDATION_FAILED = "DATA_VALIDATION_FAILED"
    ENCODING_ERROR = "ENCODING_ERROR"

    # ==================================================
    # 실행 제어 / 스케줄
    # ==================================================
    MISFIRE = "MISFIRE"                 # 스케줄 미스파이어
    MAX_INSTANCE_REACHED = "MAX_INSTANCE_REACHED"

    # ==================================================
    # 시스템 / 예외
    # ==================================================
    PERMISSION_DENIED = "PERMISSION_DENIED"
    DISK_FULL = "DISK_FULL"
    MEMORY_ERROR = "MEMORY_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"

    # ==================================================
    # 네트워크 / 연결
    # ==================================================
    NETWORK_DOWN = "NETWORK_DOWN"
    NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"  # 인터넷 연결 자체 불가
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"  # DNS 조회 실패
    
    # ==============================
    # 네트워크 / 보안 차단
    # ==============================
    NETWORK_ACCESS_BLOCKED = "NETWORK_ACCESS_BLOCKED"   
    INTERNET_DISCONNECTED = "INTERNET_DISCONNECTED"

    REMOTE_SERVER_DOWN = "REMOTE_SERVER_DOWN"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN_NETWORK_ERROR = "UNKNOWN_NETWORK_ERROR"
    NETWORK_DISCONNECTED  = "NETWORK_DISCONNECTED"
    ACCESS_BLOCKED   = "ACCESS_BLOCKED"
    DNS_ERROR = "DNS_ERROR"

    RENDERER_TIMEOUT = "RENDERER_TIMEOUT"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    DNS_FAIL = "DNS_FAIL"
    UNKNOWN = "UNKNOWN"

    # ==================================================
    # PDF / 파일 처리
    # ==================================================
    PDF_PARSE_FAIL = "pdf_parse_fail"
    FILE_DOWNLOAD_FAIL = "file_download_fail"

    # ==================================================
    # OCR
    # ==================================================
    OCR_FAIL = "ocr_fail"                      # OCR 전체 실패 (치명)
    PARTIAL_OCR_FAIL = "partial_ocr_fail"      # OCR 일부 페이지 실패 (경고)
    OCR_NOT_REQUIRED = "ocr_not_required"      # PDF 텍스트 충분
    OCR_SKIPPED_LIMIT = "ocr_skipped_limit"    # OCR 페이지 제한으로 중단

    # ==================================================
    # Selenium
    # ==================================================
    SELENIUM_ERROR = "selenium_error"
    DRIVER_ERROR = "DRIVER_ERROR"