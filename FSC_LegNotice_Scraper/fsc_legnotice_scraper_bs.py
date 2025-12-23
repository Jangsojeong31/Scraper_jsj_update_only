# fsc_legnotice_scraper_bs.py
# 금융위원회-입법예고 (BeautifulSoup 버전)
# https://www.fsc.go.kr/po040301

import os
import sys
import json
import time
import argparse
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
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

ORG_NAME = LegalDocProvided.FSC
logger = get_logger("fsc_legnotice")

# ==================================================
# 설정
# ==================================================
BASE_URL = "https://www.fsc.go.kr/po040301"
OUTPUT_BASE_DIR = os.path.join(CURRENT_DIR, "output")
OUTPUT_JSON_DIR = os.path.join(OUTPUT_BASE_DIR, "json")
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)

JSON_OUTPUT_TEMPLATE = os.path.join(
    OUTPUT_JSON_DIR, "fsc_legnotice_{timestamp}.json"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# ==================================================
# 유틸: 날짜 파싱
# ==================================================
def parse_date_safe(date_str: str):
    if not date_str:
        return None
    clean_str = re.sub(r"[./]", "-", date_str)
    try:
        return datetime.strptime(clean_str, "%Y-%m-%d").date()
    except Exception:
        return None

# ==================================================
# 유틸: tag 추출 ([ ], ( ))
# ==================================================
def extract_tags(text: str):
    if not text:
        return []

    tags = []
    tags += re.findall(r"\[([^\]]+)\]", text)
    tags += re.findall(r"\(([^\)]+)\)", text)

    return [t.strip() for t in tags if t.strip()]

# ==================================================
# 상세 페이지 추출
# ==================================================
def extract_detail(detail_url: str) -> str:
    logger.info(f"[DETAIL] {detail_url}")

    check = check_url_status(detail_url)
    if check["status"] != URLStatus.OK:
        logger.warning("[DETAIL] 접근 실패")
        return ""

    resp = requests.get(detail_url, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    cont = soup.select_one("div.board-view-wrap div.body div.cont")

    if not cont:
        logger.warning("[DETAIL] 본문 없음")
        return ""

    return cont.get_text("\n", strip=True)

# ==================================================
# 목록 페이지 파싱
# ==================================================
def extract_list(page_index: int):
    params = {"pageIndex": page_index}
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("div.board-wrap li")

    results = []
    for li in items:
        try:
            a = li.select_one("a")
            if not a:
                continue

            title = a.get_text(strip=True)
            link = urljoin(BASE_URL, a["href"])

            date_el = li.select_one("div.day")
            date = date_el.get_text(strip=True) if date_el else ""

            results.append({
                "org_name": ORG_NAME,
                "title": title,
                "date": date,
                "detail_url": link
            })
        except Exception as e:
            logger.warning(f"[LIST] 파싱 오류: {e}")

    return results

# ==================================================
# 전체 스크래핑
# ==================================================
def scrape_all(start_date=None, end_date=None):
    today = datetime.today().date()
    start_dt = (
        datetime.strptime(start_date, "%Y-%m-%d").date()
        if start_date else today - timedelta(days=30)
    )
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        if end_date else today
    )

    logger.info(f"[SCRAPE] FSC 입법예고 시작 ({start_dt} ~ {end_dt})")

    if check_url_status(BASE_URL)["status"] != URLStatus.OK:
        logger.error("[SCRAPE] 목록 URL 접근 실패")
        return

    all_results = []
    page_index = 1

    while True:
        logger.info(f"[SCRAPE] 페이지 {page_index}")
        list_data = extract_list(page_index)

        if not list_data:
            logger.info("[SCRAPE] 더 이상 목록 없음")
            break

        page_min_date = None

        for idx, item in enumerate(list_data, start=1):
            logger.info(f"[SCRAPE] [{idx}/{len(list_data)}] {item['title']}")

            date_obj = parse_date_safe(item["date"])
            if not date_obj:
                continue

            if page_min_date is None or date_obj < page_min_date:
                page_min_date = date_obj

            if not (start_dt <= date_obj <= end_dt):
                logger.info("[SCRAPE] 날짜 범위 외 → 스킵")
                continue

            content = extract_detail(item["detail_url"])

            all_results.append({
                "org_name": ORG_NAME,
                "title": item["title"],
                "date": item["date"],
                "content": content,
                "detail_url": item["detail_url"]
            })

            time.sleep(0.2)

        if page_min_date and page_min_date < start_dt:
            logger.info("[SCRAPE] 날짜 범위 종료 → 스크래핑 중단")
            break

        page_index += 1
        time.sleep(0.5)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = JSON_OUTPUT_TEMPLATE.format(timestamp=timestamp)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    logger.info(f"[SCRAPE] 총 {len(all_results)}건 저장 완료")
    logger.info(f"[SCRAPE] 저장 위치: {output_path}")

# ==================================================
# CLI
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="YYYY-MM-DD")
    args = parser.parse_args()

    scrape_all(start_date=args.start_date, end_date=args.end_date)
