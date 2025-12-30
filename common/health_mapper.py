# common/health_mapper.py

from common.health_exception import HealthCheckError


def apply_health_error(result: dict, err: HealthCheckError):
    result["ok"] = False
    result["status"] = "FAIL"
    result["error_type"] = err.error_type.name
    result["error_message"] = err.message

    if err.target:
        result["checks"]["failed_target"] = err.target
