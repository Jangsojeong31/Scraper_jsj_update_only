# Collect_Health_Checker/error_classifier.py

from common.health_error_type import HealthErrorType


def classify_health_error(result: dict) -> HealthErrorType:
    """
    Health Check 실패 결과를 HealthErrorType으로 자동 분류
    """
    error = (
        (result.get("error") or "")
        + " "
        + (result.get("traceback") or "")
    ).lower()

    if "timeout" in error:
        return HealthErrorType.TIMEOUT

    if "404" in error or "500" in error or "http" in error:
        return HealthErrorType.HTTP_ERROR

    if "no such element" in error or "unable to locate element" in error:
        return HealthErrorType.TAG_MISMATCH

    if "list is empty" in error or "no list" in error:
        return HealthErrorType.NO_LIST_DATA

    if "detail url" in error or "href" in error:
        return HealthErrorType.NO_DETAIL_URL

    if "download" in error:
        return HealthErrorType.FILE_DOWNLOAD_FAIL

    if "ocr" in error or "pdf" in error:
        return HealthErrorType.OCR_FAIL

    if "parse" in error or "beautifulsoup" in error:
        return HealthErrorType.PARSE_ERROR

    if "webdriver" in error or "driver" in error:
        return HealthErrorType.DRIVER_ERROR

    if "403" in error or "permission" in error:
        return HealthErrorType.AUTH_ERROR

    return HealthErrorType.UNKNOWN
