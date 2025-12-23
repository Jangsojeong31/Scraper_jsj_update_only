import os
import sys
import json
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# ==================================================
# 🔑 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.common_logger import get_logger
from common.common_http import check_url_status
from common.constants import URLStatus, LegalDocProvided

ORG_NAME = LegalDocProvided.FSS
# ==================================================
# 로거
# ==================================================
logger = get_logger("fss_legnotice")

# ==================================================
# URL / 설정
# ==================================================
BASE_URL = "https://www.fss.or.kr"
LIST_URL = "https://www.fss.or.kr/fss/job/lrgRegItnPrvntc/list.do?menuNo=200489"

OUTPUT_BASE_DIR = os.path.join(CURRENT_DIR, "output")
OUTPUT_JSON_DIR = os.path.join(OUTPUT_BASE_DIR, "json")
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)

JSON_OUTPUT = os.path.join(OUTPUT_JSON_DIR, "fss_legnotice_results.json")

# ==================================================
# 상세 페이지 파싱 (FULL TEXT)
# ==================================================
def parse_detail(detail_url: str) -> str:
    resp = check_url_status(detail_url)

    if resp["status"] != URLStatus.OK:
        logger.warning(f"상세 접근 실패 → {detail_url}")
        return ""

    soup = BeautifulSoup(resp["text"], "html.parser")

    box = soup.select_one("div.box")
    if not box:
        logger.warning("본문 box 없음")
        return ""

    return box.get_text("\n", strip=True)

# ==================================================
# 목록 페이지 파싱
# ==================================================
def parse_list():
    resp = check_url_status(LIST_URL)

    if resp["status"] != URLStatus.OK:
        raise RuntimeError(f"목록 URL 접근 실패: {resp}")

    soup = BeautifulSoup(resp["text"], "html.parser")

    rows = soup.select("table tbody tr")
    logger.info(f"총 {len(rows)}건 발견")

    results = []

    for idx, row in enumerate(rows, start=1):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        title = cols[1].get_text(strip=True)
        date = cols[2].get_text(strip=True)

        link = cols[1].select_one("a")
        if not link:
            continue

        detail_url = urljoin(BASE_URL, link.get("href"))

        logger.info(f"[{idx}/{len(rows)}] {title}")

        detail_full = parse_detail(detail_url)

        results.append({
            "org_name": ORG_NAME,
            "title": title,
            "date": date,
            "content": detail_full,
            "detail_url": detail_url
        })

        time.sleep(0.5)  # polite delay

    return results

# ==================================================
# 실행
# ==================================================
def scrape_all():
    logger.info("FSS 규정 개정예고 스크래핑 시작 (check_url_status 통합)")

    data = parse_list()

    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON 저장 완료: {JSON_OUTPUT}")

# ==================================================
# main
# ==================================================
if __name__ == "__main__":
    scrape_all()
