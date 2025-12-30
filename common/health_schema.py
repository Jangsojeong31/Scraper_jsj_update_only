from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

@dataclass
class HealthCheckResult:
    auth_src: str
    scraper_id: str
    target_url: str

    ok: bool
    status: str

    error_type: Optional[str] = None
    error_message: Optional[str] = None

    checked_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    elapsed_ms: Optional[int] = None

    checks: Dict[str, Any] = field(default_factory=dict)
    sample: Dict[str, Any] = field(default_factory=dict)

    def fail(self, error_type: str, message: str):
        self.ok = False
        self.status = "FAIL"
        self.error_type = error_type
        self.error_message = message

    def warn(self, error_type: str, message: str):
        self.ok = False
        self.status = "WARN"
        self.error_type = error_type
        self.error_message = message

    def success(self):
        self.ok = True
        self.status = "OK"

    def to_dict(self):
        return {
            "auth_src": self.auth_src,
            "scraper_id": self.scraper_id,
            "target_url": self.target_url,
            "ok": self.ok,
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "checked_at": self.checked_at,
            "elapsed_ms": self.elapsed_ms,
            "checks": self.checks,
            "sample": self.sample,
        }

# common/health_schema.py
def now_kst_iso() -> str:
    return datetime.now(timezone(timedelta(hours=9))).isoformat()


def base_health_output(
    *,
    auth_src: str,
    scraper_id: str,
    target_url: str,
) -> Dict:
    return {
        "auth_src": auth_src,
        "scraper_id": scraper_id,
        "target_url": target_url,

        "ok": False,
        "status": "FAIL",
        "error_type": None,
        "error_message": None,

        "checked_at": now_kst_iso(),
        "elapsed_ms": None,

        "checks": {},
    }
