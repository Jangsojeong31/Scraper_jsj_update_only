# Collect_Health_Checker/health_error_type.py

# 공통 기본 매핑 테이블
# URLStatus	HealthErrorType	의미	Alert 기준
# OK	-	정상	❌
# NOT_FOUND	NO_LIST_DATA	목록/페이지 소멸	🔶 연속
# BLOCKED	ACCESS_BLOCKED	IP/봇 차단	🔴 즉시
# RATE_LIMIT	RATE_LIMITED	호출 제한	🔶 연속
# RETRY	HTTP_ERROR	일시 장애	🔶 연속
# FAIL	HTTP_ERROR	네트워크/드라이버 오류	🔴 연속
# TIMEOUT	TIMEOUT	응답 지연	🔶 연속
from enum import Enum


class HealthErrorType(str, Enum):
    HTTP_ERROR = "HTTP 요청 실패"
    NO_LIST_DATA = "목록 데이터 없음"
    NO_DETAIL_URL = "상세 페이지 링크 누락"
    TAG_MISMATCH = "HTML 태그 구조 불일치"
    CONTENT_EMPTY = "본문 내용 비어 있음"
    FILE_DOWNLOAD_FAIL = "첨부파일 다운로드 실패"
    OCR_FAIL = "PDF/OCR 파싱 실패"
    TIMEOUT = "페이지 로딩 시간 초과"
    PARSE_ERROR = "HTML 파싱 오류"
    DRIVER_ERROR = "웹드라이버 오류"
    AUTH_ERROR = "접근 권한 오류"
    ACCESS_BLOCKED = "IP/봇 차단"
    RATE_LIMITED = "호출 제한"
    UNEXPECTED_ERROR = "알 수 없는 오류"
    UNKNOWN = "알 수 없는 오류"
    UNKNOWN_ERROR = "알 수 없는 오류"