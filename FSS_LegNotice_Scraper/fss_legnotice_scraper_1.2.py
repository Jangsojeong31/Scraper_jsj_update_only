# fss_legnotice_scraper.py
import os
import sys
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

# ==================================================
# 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.common_logger import get_logger
from common.common_http import check_url_status
from common.constants import URLStatus, LegalDocProvided

ORG_NAME = LegalDocProvided.FSS
logger = get_logger("fss_legnotice")

# ==================================================
# URL / 설정
# ==================================================
BASE_URL = "https://www.fss.or.kr"
LIST_URL = "https://www.fss.or.kr/fss/job/lrgRegItnPrvntc/list.do?menuNo=200489"

OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

JSON_OUTPUT_TEMPLATE = os.path.join(OUTPUT_DIR, "fss_legnotice_{timestamp}.json")

# ==================================================
# 상세 페이지 파싱
# ==================================================
def parse_detail(detail_url: str) -> str:
    resp = check_url_status(detail_url)
    if resp["status"] != URLStatus.OK:
        logger.warning(f"[CHECK] 상세 접근 실패 → {detail_url}")
        return ""

    soup = BeautifulSoup(resp["text"], "html.parser")
    box = soup.select_one("div.box")
    if not box:
        logger.warning(f"[SCRAPE] 상세 본문 없음 → {detail_url}")
        return ""
    return box.get_text("\n", strip=True)

# ==================================================
# 날짜 문자열 → datetime.date
# ==================================================
def parse_date_safe(date_str: str):
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except Exception:
        logger.warning(f"[SCRAPE] 날짜 변환 실패: {date_str}")
        return None

# ==================================================
# 목록 페이지 파싱 (단일 페이지)
# ==================================================
def parse_list_page(resp_text):
    soup = BeautifulSoup(resp_text, "html.parser")
    rows = soup.select("table tbody tr")
    results = []

    for idx, row in enumerate(rows, start=1):
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        title = cols[1].get_text(strip=True)
        date_str = cols[2].get_text(strip=True)
        link = cols[1].select_one("a")
        if not link:
            continue
        detail_url = urljoin(BASE_URL, link.get("href"))
        results.append({
            "title": title,
            "date": date_str,
            "detail_url": detail_url
        })
    return results

# ==================================================
# 전체 페이지 반복 + 날짜 필터링
# ==================================================
def scrape_all(start_date=None, end_date=None):
    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    logger.info(f"[SCRAPE] FSS 규정예고 스크래핑 시작 (기간: {start_dt} ~ {end_dt})")

    all_results = []
    page_index = 1

    while True:
        payload_url = f"{LIST_URL}&pageIndex={page_index}"
        resp = check_url_status(payload_url)
        if resp["status"] != URLStatus.OK:
            logger.warning(f"[CHECK] 목록 페이지 접근 실패 → {payload_url}")
            break

        page_items = parse_list_page(resp["text"])
        if not page_items:
            logger.info(f"[SCRAPE] 페이지 {page_index} 목록 없음 → 종료")
            break

        logger.info(f"[SCRAPE] 페이지 {page_index} 목록 수: {len(page_items)}")

        for idx, item in enumerate(page_items, start=1):
            logger.info(f"[SCRAPE] [{idx}/{len(page_items)}] 처리 중: {item['title']}")

            date_obj = parse_date_safe(item["date"])
            if not date_obj or not (start_dt <= date_obj <= end_dt):
                logger.info(f"[SCRAPE] 날짜 범위 외 공고 스킵: {item['title']} ({item['date']})")
                continue

            content = parse_detail(item["detail_url"])

            all_results.append({
                "org_name": ORG_NAME,
                "title": item["title"],
                "date": item["date"],
                "content": content,
                "detail_url": item["detail_url"]
            })

            time.sleep(0.3)

        # 다음 페이지 존재 여부 체크
        soup = BeautifulSoup(resp["text"], "html.parser")
        next_page = soup.select_one(f"div.paging a.next")
        if next_page:
            page_index += 1
        else:
            logger.info(f"[SCRAPE] 마지막 페이지 도달: {page_index}")
            break

    # JSON 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = JSON_OUTPUT_TEMPLATE.format(timestamp=timestamp)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f"[SCRAPE] 총 {len(all_results)}건 저장 완료: {output_path}")

# ==================================================
# 실행
# ==================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    args = parser.parse_args()
    scrape_all(start_date=args.start_date, end_date=args.end_date)
