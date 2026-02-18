from dataclasses import dataclass
from typing import Optional
from .health_error_type import HealthErrorType


# @dataclass
# class HealthCheckError(Exception):
#     error_type: HealthErrorType
#     message: str
#     detail: Optional[str] = None

#     def to_dict(self) -> dict:
#         return {
#             "error_type": self.error_type.name,
#             "error_type_desc": self.error_type.value,
#             "error_message": self.message,
#             "detail": self.detail,
#         }

@dataclass
class HealthCheckError(Exception):
    error_type: HealthErrorType
    message: str
    target: Optional[str] = None   # ✅ 추가
    detail: Optional[str] = None

    def __str__(self):
        return f"[{self.error_type.name}] {self.message}"