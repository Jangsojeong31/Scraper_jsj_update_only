# crefia_legnotice_scraper.py
# 여신금융협회-정보센터→ 자율규제 제·개정 공고

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
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

# ==================================================
# 설정
# ==================================================
logger = get_logger("crefia_legnotice")
ORG_NAME = LegalDocProvided.CREFIA

BASE_LIST_URL = "https://www.crefia.or.kr/portal/board/boardDataList.do?boardid=bbs057"
LIST_URL = "https://www.crefia.or.kr/portal/board/boardDataList.do?boardid=bbs057"
OUTPUT_BASE_DIR = os.path.join(CURRENT_DIR, "output")
OUTPUT_JSON_DIR = os.path.join(OUTPUT_BASE_DIR, "json")
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)

HEADLESS = True
WAIT_TIMEOUT = 12
PAGE_LOAD_STRATEGY = "eager"

# ==================================================
# 드라이버 생성
# ==================================================
def create_driver(headless=True):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--remote-allow-origins=*")

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.images": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.capabilities["pageLoadStrategy"] = PAGE_LOAD_STRATEGY
    return driver

# ==================================================
# content 정제
# ==================================================
def clean_content_text(text: str) -> str:
    if not text:
        return None
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"제\s*\n\s*(\d+)\s*\n\s*자", r"제\1자", text)
    return text.strip()

# ==================================================
# 상세 파싱
# ==================================================
def parse_detail_html(html, current_url):
    soup = BeautifulSoup(html, "lxml")
    title = soup.select_one("div.title")
    date = soup.select_one("div.date")
    content_div = soup.select_one("div.cont_area")
    raw_content = content_div.get_text(separator="\n", strip=True) if content_div else None
    content = clean_content_text(raw_content)
    return {
        "org_name": ORG_NAME,
        "title": title.get_text(strip=True) if title else None,
        "date": date.get_text(strip=True) if date else None,
        "content": content,
        "detail_url": current_url
    }

# ==================================================
# 목록 로딩 대기
# ==================================================
def wait_for_list(driver, wait):
    for _ in range(3):
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.list_view_wrap")))
            # 목록이 비어 있는 경우 체크
            rows = driver.find_elements(By.CSS_SELECTOR, "div.list_view_head_wrap")
            if not rows:
                logger.info("[SCRAPE] 목록 없음")
                return False
            return True
        except:
            time.sleep(1)
    return False

# ==================================================
# 전체 크롤링
# ==================================================
def scrape_all(start_date=None, end_date=None):
    driver = create_driver(HEADLESS)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    results = []

    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    try:
        logger.info(f"[SCRAPE] CREFIA 공고 스크래핑 시작 (기간: {start_dt} ~ {end_dt})")

        if check_url_status(BASE_LIST_URL)["status"] != URLStatus.OK:
            logger.error(f"[CHECK] 목록 URL 접근 실패: {BASE_LIST_URL}")
            return

        driver.get(BASE_LIST_URL)
        if not wait_for_list(driver, wait):
            rows = driver.find_elements(By.CSS_SELECTOR, "div.list_view_head_wrap")
            if not rows:
                logger.info("[SCRAPE] 목록 페이지에 공고 없음")
                return
            else:
                logger.error("[CHECK] 목록 페이지 로딩 실패")
                return

        page = 1
        while True:
            logger.info(f"[SCRAPE] 페이지 {page} 처리 중")
            rows = driver.find_elements(By.CSS_SELECTOR, "div.list_view_head_wrap")
            if not rows:
                logger.info("[SCRAPE] 해당 페이지 공고 없음")
                break

            for idx, row in enumerate(rows, 1):
                try:
                    title = row.find_element(By.CSS_SELECTOR, "div.title h5").text.strip()
                    date_str = row.find_element(By.CSS_SELECTOR, "div.date").text.strip()
                    date_obj = datetime.strptime(date_str, "%Y.%m.%d").date()
                    detail_link = row.find_element(By.TAG_NAME, "a").get_attribute("href")
                except Exception as e:
                    logger.warning(f"[SCRAPE] 목록 파싱 실패: {e}")
                    continue

                logger.info(f"[CHECK] {detail_link}")
                driver.get(detail_link)
                time.sleep(0.5)
                logger.info("[REQ] 200 OK")

                detail_html = driver.page_source
                detail = parse_detail_html(detail_html, detail_link)

                # 날짜 필터링
                if not (start_dt <= date_obj <= end_dt):
                    logger.info(f"[SCRAPE] 날짜 범위 외 공고 스킵: {title} ({date_str})")
                    continue

                results.append(detail)
                logger.info(f"[SCRAPE] [{idx}/{len(rows)}] 상세 페이지 수집 완료: {title}")

            # 다음 페이지 이동
            try:
                next_page_btn = driver.find_element(By.LINK_TEXT, str(page + 1))
                driver.execute_script("arguments[0].click();", next_page_btn)
                wait_for_list(driver, wait)
                page += 1
            except NoSuchElementException:
                logger.info("[SCRAPE] 마지막 페이지 도달")
                break

        # JSON 저장
        output_path = os.path.join(
            OUTPUT_JSON_DIR, f"crefia_legnotice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info(f"[SCRAPE] 총 {len(results)}건 저장 완료: {output_path}")

    finally:
        driver.quit()
        logger.info("[SCRAPE] 드라이버 종료")

# ==================================================
# CLI
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    args = parser.parse_args()
    scrape_all(start_date=args.start_date, end_date=args.end_date)
