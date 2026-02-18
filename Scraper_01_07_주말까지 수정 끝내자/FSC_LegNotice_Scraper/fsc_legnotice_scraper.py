# fsc_legnotice_scraper_pages.py
# 금융위원회-입법예고
# https://www.fsc.go.kr/po040301

import os
import sys
import json
import time
import argparse
import re
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

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

WAIT_TIMEOUT = 10
HEADLESS = True
JSON_OUTPUT_TEMPLATE = os.path.join(OUTPUT_JSON_DIR, "fsc_legnotice_{timestamp}.json")

# ==================================================
# Chrome Driver 생성
# ==================================================
def create_driver():
    chrome_options = Options()
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# ==================================================
# 상세 페이지 추출
# ==================================================
def extract_detail(driver, url):
    logger.info(f"[CHECK] {url}")
    detail_check = check_url_status(url)
    if detail_check["status"] != URLStatus.OK:
        logger.warning(f"[REQ] 상세 URL 접근 실패: {url}")
        return ""

    driver.get(url)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    try:
        cont = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.board-view-wrap div.body div.cont"))
        )
        logger.info("[REQ] 200 OK")
        return cont.text.strip()
    except TimeoutException:
        logger.warning(f"[REQ] 상세 본문 없음: {url}")
        return ""

# ==================================================
# 날짜 문자열 → datetime.date 변환
# ==================================================
def parse_date_safe(date_str: str):
    clean_str = re.sub(r"[./]", "-", date_str)
    try:
        return datetime.strptime(clean_str, "%Y-%m-%d").date()
    except Exception:
        return None

# ==================================================
# 목록 페이지에서 항목 수집
# ==================================================
def extract_list(driver):
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.board-wrap form#searchFrm")))
    except TimeoutException:
        logger.info("[SCRAPE] 목록 페이지 없음")
        return []

    items = driver.find_elements(By.CSS_SELECTOR, "div.board-wrap li")
    result = []
    for item in items:
        try:
            a = item.find_element(By.CSS_SELECTOR, "a")
            title = a.text.strip()
            link = a.get_attribute("href")
            date_el = item.find_element(By.CSS_SELECTOR, "div.day")
            date = date_el.text.strip()
            result.append({"org_name": ORG_NAME, "title": title, "date": date, "detail_url": link})
        except Exception as e:
            logger.warning(f"[SCRAPE] 목록 파싱 오류: {e}")
    return result

# ==================================================
# 전체 실행 (다중 페이지 지원)
# ==================================================
def scrape_all(start_date=None, end_date=None):
    driver = create_driver()
    os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)

    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    try:
        logger.info(f"[SCRAPE] FSC 입법예고 스크래핑 시작 (기간: {start_dt} ~ {end_dt})")

        if check_url_status(BASE_URL)["status"] != URLStatus.OK:
            logger.error(f"[CHECK] 목록 URL 접근 실패: {BASE_URL}")
            return

        driver.get(BASE_URL)
        all_results = []
        page_number = 1

        while True:
            logger.info(f"[SCRAPE] 페이지 {page_number} 처리 중")
            list_data = extract_list(driver)
            if not list_data:
                logger.info("[SCRAPE] 현재 페이지 목록 없음 → 종료")
                break

            logger.info(f"[SCRAPE] 현재 페이지 목록 수: {len(list_data)}")

            for idx, item in enumerate(list_data, start=1):
                logger.info(f"[SCRAPE] [{idx}/{len(list_data)}] 처리 중: {item['title']}")
                detail_text = extract_detail(driver, item["detail_url"])

                date_obj = parse_date_safe(item["date"])
                if not date_obj or not (start_dt <= date_obj <= end_dt):
                    logger.info(f"[SCRAPE] 날짜 범위 외 공고 스킵: {item['title']} ({item['date']})")
                    continue

                all_results.append({
                    "org_name": ORG_NAME,
                    "title": item["title"],
                    "date": item["date"],
                    "content": detail_text,
                    "detail_url": item["detail_url"]
                })
                time.sleep(0.3)

            # 다음 페이지 이동
            try:
                next_page_btn = driver.find_element(By.LINK_TEXT, str(page_number + 1))
                driver.execute_script("arguments[0].click();", next_page_btn)
                WebDriverWait(driver, WAIT_TIMEOUT).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.board-wrap li"))
                )
                page_number += 1
            except NoSuchElementException:
                logger.info("[SCRAPE] 마지막 페이지 도달")
                break

        # JSON 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = JSON_OUTPUT_TEMPLATE.format(timestamp=timestamp)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        logger.info(f"[SCRAPE] 총 {len(all_results)}건 저장 완료: {output_path}")

    except Exception as e:
        logger.exception(f"[SCRAPE] 치명적 오류 발생: {e}")

    finally:
        driver.quit()
        logger.info("[SCRAPE] 드라이버 종료")

# ==================================================
# CLI
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, help="YYYY-MM-DD")
    args = parser.parse_args()
    scrape_all(start_date=args.start_date, end_date=args.end_date)
