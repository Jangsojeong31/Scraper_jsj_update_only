# common/common_logger.py
 
import logging
import os
from logging.handlers import TimedRotatingFileHandler

# =========================
# Tag 자동 주입 필터
# =========================
class TagFilter(logging.Filter):
    def __init__(self, default_tag="GENERAL"):
        super().__init__()
        self.default_tag = default_tag

    def filter(self, record):
        if not hasattr(record, "tag"):
            record.tag = self.default_tag
        return True


# =========================
# 날짜 + 크기 혼합 핸들러
# =========================
class TimedSizeRotatingHandler(TimedRotatingFileHandler):
    def __init__(self, *args, maxBytes=10 * 1024 * 1024, **kwargs):
        self.maxBytes = maxBytes
        super().__init__(*args, **kwargs)

    def shouldRollover(self, record):
        if self.stream is None:
            self.stream = self._open()

        # 날짜 롤링
        if super().shouldRollover(record):
            return 1

        # 크기 롤링
        if self.maxBytes > 0:
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() >= self.maxBytes:
                return 1

        return 0


# =========================
# 공통 Logger 팩토리
# =========================
def get_logger(
    name: str,
    log_file: str = None,
    log_dir: str = "logs",
    level=logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 30,
):
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger
    # =========================
    # logs 디렉터리
    # =========================
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    LOG_DIR = os.path.join(BASE_DIR, "logs")
    os.makedirs(LOG_DIR, exist_ok=True)

    # =========================
    # log_file 기본값 처리
    # =========================
    if not log_file:
        log_file = f"{name}.log"

    error_log_file = log_file.replace(".log", "_error.log")

    LOG_PATH = os.path.join(LOG_DIR, log_file)
    ERROR_LOG_PATH = os.path.join(
        LOG_DIR,
        log_file.replace(".log", "_error.log")
    )

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(tag)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    tag_filter = TagFilter()

    # =========================
    # 일반 로그
    # =========================
    normal_handler = TimedSizeRotatingHandler(
#        filename=os.path.join(log_dir, f"{name}.log"),
        filename=os.path.join(log_dir, log_file),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        maxBytes=max_bytes,
        encoding="utf-8",
    )
    normal_handler.setFormatter(formatter)
    normal_handler.addFilter(tag_filter)
    normal_handler.setLevel(logging.INFO)

    # =========================
    # ERROR 전용 로그
    # =========================
    error_handler = TimedSizeRotatingHandler(
#        filename=os.path.join(log_dir, f"{name}_error.log"),
        filename=os.path.join(log_dir, error_log_file),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        maxBytes=max_bytes,
        encoding="utf-8",
    )
    error_handler.setFormatter(formatter)
    error_handler.addFilter(tag_filter)
    error_handler.setLevel(logging.ERROR)

    # =========================
    # 콘솔
    # =========================
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(tag_filter)
    console_handler.setLevel(level)

    logger.addHandler(normal_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger
