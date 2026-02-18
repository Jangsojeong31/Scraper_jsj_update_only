# common/health_mapper.py

from common.constants import URLStatus
from common.health_error_type import HealthErrorType
from common.health_exception import HealthCheckError

def apply_health_error(result: dict, err: HealthCheckError):

     # ==============================
    # 0. 방어 로직 (필수)
    # ==============================
    if err is None or err.error_type is None:
        return

    #정상 무데이터는 ERROR 아님
    if err.error_type == HealthErrorType.NO_LIST_DATA:
        result["ok"] = True
        result["status"] = "OK"
        result["error_type"] = err.error_type.name
        result["error_message"] = err.message
        return
        
    # 정상 무데이터는 ERROR 아님
    if err.error_type == HealthErrorType.CONTENT_EMPTY:
        result["ok"] = True
        result["status"] = "OK"
        result["error_type"] = err.error_type.name
        result["error_message"] = err.message
        return

    result["ok"] = False
    result["status"] = (

        "SKIPPED"
        if err.error_type == HealthErrorType.SKIPPED
        else "ERROR"
    )

    # 🔴 핵심 수정
    result["error_type"] = err.error_type.name
    result["error_message"] = err.message

    result.setdefault("checks", {})

    if err.target:
        result["checks"]["failed_target"] = err.target

def map_url_status_to_health_error(status: URLStatus) -> HealthErrorType:

    if status == URLStatus.OK:
        return None
    
    return {
        URLStatus.OK: HealthErrorType.OK,

        # HTTP
        URLStatus.NOT_FOUND: HealthErrorType.HTTP_404_NOT_FOUND,
        URLStatus.HTTP_ERROR: HealthErrorType.HTTP_ERROR,
        URLStatus.REMOTE_SERVER_DOWN: HealthErrorType.HTTP_5XX_SERVER_ERROR,
        URLStatus.RATE_LIMITED: HealthErrorType.HTTP_429_RATE_LIMIT,
        URLStatus.BLOCKED: HealthErrorType.HTTP_403_FORBIDDEN,

        # Network / Timeout
        URLStatus.TIMEOUT: HealthErrorType.TIMEOUT,
        URLStatus.NETWORK_TIMEOUT: HealthErrorType.NETWORK_TIMEOUT,
        URLStatus.RETRY: HealthErrorType.NETWORK_TIMEOUT,
        URLStatus.NETWORK_DOWN: HealthErrorType.NETWORK_DOWN,
        URLStatus.INTERNET_DISCONNECTED: HealthErrorType.INTERNET_DISCONNECTED,
        URLStatus.NETWORK_UNREACHABLE: HealthErrorType.NETWORK_UNREACHABLE,
        URLStatus.DNS_FAIL: HealthErrorType.DNS_RESOLUTION_FAILED,
        URLStatus.DNS_ERROR: HealthErrorType.DNS_ERROR,

        # Security
        URLStatus.ACCESS_BLOCKED: HealthErrorType.ACCESS_BLOCKED,

        # SSL
        URLStatus.SSL_ERROR: HealthErrorType.SSL_ERROR,

        # Selenium
        URLStatus.ERROR: HealthErrorType.SELENIUM_CRASHED,
        URLStatus.UNEXPECTED_ERROR: HealthErrorType.BROWSER_UNRESPONSIVE,

        # Fallback
        URLStatus.FAIL: HealthErrorType.UNEXPECTED_ERROR,
        URLStatus.UNKNOWN: HealthErrorType.UNKNOWN,
        URLStatus.UNKNOWN_ERROR: HealthErrorType.UNEXPECTED_ERROR,
    }.get(status, HealthErrorType.UNKNOWN)


URLSTATUS_TO_HEALTH_ERROR = {
    URLStatus.OK: None,

    URLStatus.NOT_FOUND: HealthErrorType.HTTP_404_NOT_FOUND,
    URLStatus.BLOCKED: HealthErrorType.HTTP_403_FORBIDDEN,
    URLStatus.RATE_LIMIT: HealthErrorType.HTTP_ERROR,
    URLStatus.RETRY: HealthErrorType.HTTP_5XX_SERVER_ERROR,

    URLStatus.TIMEOUT: HealthErrorType.TIMEOUT,
    URLStatus.SKIPPED: HealthErrorType.SKIPPED,

    URLStatus.FAIL: HealthErrorType.UNEXPECTED_ERROR,
    URLStatus.ERROR: HealthErrorType.UNEXPECTED_ERROR,

    URLStatus.ACCESS_BLOCKED: HealthErrorType.UNKNOWN_NETWORK_ERROR,
    URLStatus.ACCESS_BLOCKED: HealthErrorType.NETWORK_ACCESS_BLOCKED,
    URLStatus.ACCESS_BLOCKED: HealthErrorType.ACCESS_BLOCKED,

    URLStatus.NETWORK_DOWN: HealthErrorType.NETWORK_DOWN,
    URLStatus.NETWORK_DOWN: HealthErrorType.INTERNET_DISCONNECTED,
    URLStatus.NETWORK_DOWN: HealthErrorType.NETWORK_DOWN,
    URLStatus.NETWORK_DOWN: HealthErrorType.NETWORK_UNREACHABLE,

    URLStatus.RETRY: HealthErrorType.NETWORK_TIMEOUT,
        
    URLStatus.DNS_FAIL: HealthErrorType.DNS_RESOLUTION_FAILED,
    URLStatus.DNS_FAIL: HealthErrorType.DNS_FAIL,
    
    URLStatus.INTERNET_DISCONNECTED: HealthErrorType.INTERNET_DISCONNECTED,   

    URLStatus.FAIL: HealthErrorType.HTTP_ERROR,

    
}

def     map_url_status_to_health_error(url_status: URLStatus):
    """
    URLStatus → HealthErrorType 변환
    """
    return URLSTATUS_TO_HEALTH_ERROR.get(
        url_status,
        HealthErrorType.UNEXPECTED_ERROR
    )

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

        URLStatus.NOT_FOUND: HealthErrorType.HTTP_404_NOT_FOUND,
        URLStatus.BLOCKED: HealthErrorType.HTTP_403_FORBIDDEN,
        URLStatus.RATE_LIMIT: HealthErrorType.HTTP_ERROR,
        URLStatus.RETRY: HealthErrorType.HTTP_5XX_SERVER_ERROR,

        URLStatus.TIMEOUT: HealthErrorType.TIMEOUT,
        URLStatus.SKIPPED: HealthErrorType.SKIPPED,

        URLStatus.FAIL: HealthErrorType.UNEXPECTED_ERROR,
        URLStatus.ERROR: HealthErrorType.UNEXPECTED_ERROR,

        URLStatus.NETWORK_DOWN: HealthErrorType.NETWORK_UNREACHABLE,
        URLStatus.DNS_FAIL: HealthErrorType.DNS_RESOLUTION_FAILED,
        URLStatus.ACCESS_BLOCKED: HealthErrorType.NETWORK_ACCESS_BLOCKED, 
        URLStatus.INTERNET_DISCONNECTED: HealthErrorType.INTERNET_DISCONNECTED,                      

        URLStatus.REMOTE_SERVER_DOWN: HealthErrorType.HTTP_5XX_SERVER_ERROR,

    }
    return mapping.get(url_status, HealthErrorType.UNKNOWN)

from common.constants import NetworkState

NETWORKSTATE_TO_HEALTH = {
    NetworkState.INTERNET_DISCONNECTED: HealthErrorType.INTERNET_DISCONNECTED,
    NetworkState.NETWORK_UNREACHABLE: HealthErrorType.NETWORK_UNREACHABLE,
    NetworkState.DNS_FAIL: HealthErrorType.DNS_RESOLUTION_FAILED,
    NetworkState.ACCESS_BLOCKED: HealthErrorType.NETWORK_ACCESS_BLOCKED,
    NetworkState.REMOTE_SERVER_DOWN: HealthErrorType.REMOTE_SERVER_DOWN,
    NetworkState.RATE_LIMITED: HealthErrorType.RATE_LIMITED,
    NetworkState.TIMEOUT: HealthErrorType.TIMEOUT,
    NetworkState.UNKNOWN_ERROR: HealthErrorType.UNKNOWN_NETWORK_ERROR,
}


NETWORKSTATE_TO_HEALTH_ERROR = {
    NetworkState.OK: HealthErrorType.OK,
    NetworkState.INTERNET_DISCONNECTED: HealthErrorType.NETWORK_DISCONNECTED,
    NetworkState.INTERNET_DISCONNECTED: HealthErrorType.INTERNET_DISCONNECTED,
    NetworkState.NETWORK_UNREACHABLE: HealthErrorType.NETWORK_DOWN,
    NetworkState.NETWORK_UNREACHABLE: HealthErrorType.NETWORK_UNREACHABLE,
    NetworkState.DNS_FAIL: HealthErrorType.DNS_RESOLUTION_FAILED,
    NetworkState.ACCESS_BLOCKED: HealthErrorType.NETWORK_ACCESS_BLOCKED,
    NetworkState.RATE_LIMITED: HealthErrorType.HTTP_429_RATE_LIMIT,
    NetworkState.REMOTE_SERVER_DOWN: HealthErrorType.HTTP_5XX_SERVER_ERROR,
    NetworkState.TIMEOUT: HealthErrorType.TIMEOUT,
    NetworkState.SSL_ERROR: HealthErrorType.SSL_ERROR,
    NetworkState.DNS_ERROR: HealthErrorType.DNS_ERROR,
    NetworkState.UNKNOWN_ERROR: HealthErrorType.UNEXPECTED_ERROR,
    NetworkState.UNKNOWN: HealthErrorType.UNEXPECTED_ERROR,
}


def map_network_state_to_health_error(state: NetworkState) -> HealthErrorType:
    """
    NetworkState → HealthErrorType (운영 표준)
    """
    mapping = {
        NetworkState.INTERNET_DISCONNECTED: HealthErrorType.INTERNET_DISCONNECTED,
        NetworkState.DNS_ERROR: HealthErrorType.DNS_ERROR,
        NetworkState.ACCESS_BLOCKED: HealthErrorType.ACCESS_BLOCKED,
        NetworkState.SSL_ERROR: HealthErrorType.SSL_ERROR,
        NetworkState.TIMEOUT: HealthErrorType.TIMEOUT,
    }    
    #return NETWORKSTATE_TO_HEALTH_ERROR.get(state,HealthErrorType.UNEXPECTED_ERROR)
    return mapping.get(state, HealthErrorType.UNEXPECTED_ERROR)
