# bok_legnotice_scraper_selenium_driverpool.py
# 한국은행 규정예고 스크래퍼
# 페이지네이션 반복 + 상세 페이지 병렬 크롤링 + 드라이버 풀 사용 (메모리 최적화)

import os
import sys
import json
import argparse
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
from queue import Queue
from threading import Thread

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# ==================================================
# 프로젝트 루트 경로 등록
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
logger = get_logger("bok_search")
ORG_NAME = LegalDocProvided.BOK
POOL_SIZE = 3  # 재사용할 드라이버 수

BASE_URL = "https://www.bok.or.kr"
LIST_URL = "https://www.bok.or.kr/portal/singl/law/listBbs.do?bbsSe=rule&menuNo=200203"

OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================================================
# 드라이버 생성
# ==================================================
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# ==================================================
# 날짜 처리
# ==================================================
def resolve_search_dates(start_date=None, end_date=None):
    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    return start_dt, end_dt

# ==================================================
# 검색 적용 (폼 submit)
# ==================================================
def apply_date_search(driver, start_date=None, end_date=None):
    wait = WebDriverWait(driver, 20)
    sdate, edate = resolve_search_dates(start_date, end_date)
    logger.info(f"[SCRAPE] 검색 날짜 설정: {sdate} ~ {edate}")

    sdate_input = wait.until(EC.presence_of_element_located((By.ID, "sdate")))
    driver.execute_script("arguments[0].value = arguments[1];", sdate_input, sdate.strftime("%Y-%m-%d"))

    edate_input = wait.until(EC.presence_of_element_located((By.ID, "edate")))
    driver.execute_script("arguments[0].value = arguments[1];", edate_input, edate.strftime("%Y-%m-%d"))

    page_index_input = driver.find_element(By.ID, "pageIndex")
    driver.execute_script("arguments[0].value = '1';", page_index_input)

    search_form = driver.find_element(By.ID, "schFrom")
    driver.execute_script("arguments[0].submit();", search_form)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.bdLine.type2.type3 ul li")))

# ==================================================
# 목록 파싱
# ==================================================
def parse_list(driver):
    items = []
    rows = driver.find_elements(By.CSS_SELECTOR, "div.bdLine.type2.type3 ul > li")
    for row in rows:
        try:
            title = row.find_element(By.CSS_SELECTOR, ".titlesub").text.strip()
            date = row.find_element(By.CSS_SELECTOR, ".date").text.strip()
            a = row.find_element(By.TAG_NAME, "a")
            items.append({
                "org_name": ORG_NAME,
                "title": title,
                "date": date,
                "detail_url": urljoin(BASE_URL, a.get_attribute("href"))
            })
        except Exception:
            continue
    logger.info(f"[SCRAPE] 목록 수집: {len(items)}건")
    return items

# ==================================================
# 상세 페이지 크롤링 (공유 드라이버)
# ==================================================
def scrape_detail_worker(queue, results, driver_pool, start_dt, end_dt):
    while True:
        try:
            item = queue.get(block=False)
        except:
            break
        driver = driver_pool.get()
        try:
            logger.info(f"[CHECK] {item['detail_url']}")
            driver.get(item["detail_url"])
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.dbdata"))
            )
            logger.info("[REQ] 200 OK")

            dbdata_div = driver.find_element(By.CSS_SELECTOR, "div.dbdata")
            exclude_divs = dbdata_div.find_elements(By.CSS_SELECTOR, "#hwpEditorBoardContent")
            for ex in exclude_divs:
                driver.execute_script("arguments[0].parentNode.removeChild(arguments[0]);", ex)
            paragraphs = dbdata_div.find_elements(By.XPATH, ".//p|.//div")
            content = "\n".join([p.text.strip() for p in paragraphs if p.text.strip()])
            item["content"] = content

            # 날짜 필터링
            item_date = datetime.strptime(item["date"], "%Y.%m.%d").date()
            if not (start_dt <= item_date <= end_dt):
                logger.info(f"[SCRAPE] [{item['title']}] 날짜 범위 외 공고 스킵: {item['date']}")
            else:
                results.append(item)
                logger.info(f"[SCRAPE] [{item['title']}] 상세 수집 완료")

        except Exception as e:
            item["content"] = ""
            results.append(item)
            logger.warning(f"[SCRAPE] 상세 페이지 크롤 실패: {item['title']} / {e}")
        finally:
            driver_pool.put(driver)
            queue.task_done()

# ==================================================
# 메인 스크래핑
# ==================================================
def scrape_all(start_date=None, end_date=None):
    main_driver = create_driver()
    all_results = []
    start_dt, end_dt = resolve_search_dates(start_date, end_date)

    try:
        logger.info(f"[SCRAPE] BOK 검색 스크래핑 시작 (기간: {start_dt} ~ {end_dt})")

        if check_url_status(LIST_URL)["status"] != URLStatus.OK:
            raise RuntimeError("LIST_URL 접근 실패")

        main_driver.get(LIST_URL)
        WebDriverWait(main_driver, 20).until(EC.presence_of_element_located((By.ID, "sdate")))
        apply_date_search(main_driver, start_date, end_date)

        # 드라이버 풀 생성
        driver_pool = Queue()
        for _ in range(POOL_SIZE):
            driver_pool.put(create_driver())

        page_number = 1
        while True:
            logger.info(f"[SCRAPE] 현재 페이지: {page_number}")
            results = parse_list(main_driver)
            if not results:
                logger.info("[SCRAPE] 검색 결과 없음 또는 마지막 페이지 → 종료")
                break

            # 큐에 항목 넣고 스레드 시작
            queue = Queue()
            for item in results:
                queue.put(item)

            threads = []
            for _ in range(POOL_SIZE):
                t = Thread(target=scrape_detail_worker, args=(queue, all_results, driver_pool, start_dt, end_dt))
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            # 다음 페이지 이동
            try:
                next_page = main_driver.find_element(By.LINK_TEXT, str(page_number + 1))
                main_driver.execute_script("arguments[0].click();", next_page)
                WebDriverWait(main_driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.bdLine.type2.type3 ul li"))
                )
                page_number += 1
            except NoSuchElementException:
                logger.info("[SCRAPE] 마지막 페이지 도달")
                break

        # JSON 저장
        output_path = os.path.join(
            OUTPUT_DIR, f"bok_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        logger.info(f"[SCRAPE] 총 {len(all_results)}건 저장 완료: {output_path}")

    finally:
        # 드라이버 풀 종료
        while not driver_pool.empty():
            driver_pool.get().quit()
        main_driver.quit()
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
