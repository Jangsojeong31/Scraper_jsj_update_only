# fss_legnotice_selenium_full.py
import os
import sys
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
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
from common.constants import LegalDocProvided

ORG_NAME = LegalDocProvided.FSS
logger = get_logger("fss_legnotice_selenium")

# ==================================================
# URL / 설정
# ==================================================
BASE_URL = "https://www.fss.or.kr"
LIST_URL = "https://www.fss.or.kr/fss/job/lrgRegItnPrvntc/list.do?menuNo=200489"

OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)
JSON_OUTPUT_TEMPLATE = os.path.join(OUTPUT_DIR, "fss_legnotice_{timestamp}.json")

HEADLESS = True
WAIT_TIMEOUT = 10
MAX_WORKERS = 5  # 동시 상세 페이지 수집 스레드 수

# ==================================================
# Selenium 드라이버 생성
# ==================================================
def create_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-logging")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

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
# 상세 페이지 수집
# ==================================================
def parse_detail(detail_url: str):
    try:
        driver = create_driver(headless=HEADLESS)
        driver.get(detail_url)
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        cont = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.box")))
        text = cont.text.strip()
        return text
    except TimeoutException:
        logger.warning(f"[SCRAPE] 상세 본문 없음 → {detail_url}")
        return ""
    finally:
        driver.quit()

# ==================================================
# 목록 페이지 파싱
# ==================================================
def parse_list_page(driver):
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    results = []

    for idx, row in enumerate(rows, start=1):
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) < 3:
            continue
        title = cols[1].text.strip()
        date_str = cols[2].text.strip()
        link_el = cols[1].find_element(By.TAG_NAME, "a")
        detail_url = urljoin(BASE_URL, link_el.get_attribute("href")) if link_el else None
        if detail_url:
            results.append({
                "title": title,
                "date": date_str,
                "detail_url": detail_url
            })
    return results

# ==================================================
# 전체 페이지 반복 + 상세 본문 수집
# ==================================================
def scrape_all(start_date=None, end_date=None):
    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    logger.info(f"[SCRAPE] FSS 규정예고 스크래핑 시작 (기간: {start_dt} ~ {end_dt})")

    driver = create_driver(headless=HEADLESS)
    driver.get(LIST_URL)
    all_results = []

    while True:
        page_items = parse_list_page(driver)
        if not page_items:
            logger.info("[SCRAPE] 목록 없음 → 종료")
            break

        logger.info(f"[SCRAPE] 페이지 목록 수: {len(page_items)}")

        # 날짜 필터링
        filtered_items = []
        for item in page_items:
            date_obj = parse_date_safe(item["date"])
            if date_obj and start_dt <= date_obj <= end_dt:
                filtered_items.append(item)
            else:
                logger.info(f"[SCRAPE] 날짜 범위 외 스킵: {item['title']} ({item['date']})")

        # 상세 페이지 동시 수집
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_item = {executor.submit(parse_detail, item["detail_url"]): item for item in filtered_items}
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    content = future.result()
                except Exception as e:
                    logger.warning(f"[SCRAPE] 상세 수집 오류: {item['title']} → {e}")
                    content = ""
                all_results.append({
                    "org_name": ORG_NAME,
                    "title": item["title"],
                    "date": item["date"],
                    "content": content,
                    "detail_url": item["detail_url"]
                })

        # 다음 페이지 버튼 클릭
        try:
            next_btn = driver.find_element(By.CSS_SELECTOR, "div.pagination-set li.i.next a")
            if "disabled" in next_btn.get_attribute("class"):
                logger.info("[SCRAPE] 마지막 페이지 도달")
                break
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(1)
        except NoSuchElementException:
            logger.info("[SCRAPE] 다음 페이지 버튼 없음 → 종료")
            break

    driver.quit()

    # JSON 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = JSON_OUTPUT_TEMPLATE.format(timestamp=timestamp)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f"[SCRAPE] 총 {len(all_results)}건 저장 완료: {output_path}")

# ==================================================
# CLI 실행
# ==================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    args = parser.parse_args()
    scrape_all(start_date=args.start_date, end_date=args.end_date)
