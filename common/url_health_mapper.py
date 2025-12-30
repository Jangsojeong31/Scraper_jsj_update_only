# common/url_health_mapper.py

# 단계	실패 조건	raise
# 목록	items 없음	NO_LIST_DATA
# 상세 URL	URL 없음	NO_DETAIL_URL
# 상세 접근	HTTP 오류	HTTP_ERROR
# 첨부파일	URL 있으나 접근 실패	FILE_DOWNLOAD_FAILED
# PDF/OCR	파싱 불가	CONTENT_EMPTY

from common.constants import URLStatus
from common.health_error_type import HealthErrorType

def map_urlstatus_to_health_error(url_status: URLStatus) -> HealthErrorType:

    """
    URL 접근 결과(URLStatus)를 HealthErrorType으로 변환
    - 정상(OK)인 경우 None 반환
    """
    if url_status == URLStatus.OK:
        return None
        
    mapping = {
        URLStatus.NOT_FOUND: HealthErrorType.NO_LIST_DATA,
        URLStatus.BLOCKED: HealthErrorType.ACCESS_BLOCKED,
        URLStatus.RATE_LIMIT: HealthErrorType.RATE_LIMITED,
        URLStatus.RETRY: HealthErrorType.HTTP_ERROR,
        URLStatus.FAIL: HealthErrorType.HTTP_ERROR,
        URLStatus.TIMEOUT: HealthErrorType.TIMEOUT,
    }
    return mapping.get(url_status, HealthErrorType.UNKNOWN)

