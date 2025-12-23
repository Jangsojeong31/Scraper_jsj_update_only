# crefia_legnotice_scraper_v2.py
# 여신금융협회 > 정보센터 > 자율규제 제·개정 공고

import os
import sys
import json
import time
import argparse
import re
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
# from webdriver_manager.chrome import ChromeDriverManager
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
from common.base_scraper import BaseScraper
# ==================================================
# 설정
# ==================================================
logger = get_logger("crefia_legnotice_v2")
ORG_NAME = LegalDocProvided.CREFIA

BASE_LIST_URL = "https://www.crefia.or.kr/portal/board/boardDataList.do?boardid=bbs057"

HEADLESS = True
WAIT_TIMEOUT = 12
PAGE_LOAD_STRATEGY = "eager"

OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================================================
# 드라이버 생성
# ==================================================
def create_driver(headless=True):
    # chrome_options = Options()
    # if headless:
    #     chrome_options.add_argument("--headless=new")
    #     chrome_options.add_argument("--disable-gpu")

    # chrome_options.add_argument("--no-sandbox")
    # chrome_options.add_argument("--disable-dev-shm-usage")
    # chrome_options.add_argument("--disable-extensions")
    # chrome_options.add_argument("--remote-allow-origins=*")

    # prefs = {
    #     "profile.managed_default_content_settings.images": 2
    # }
    # chrome_options.add_experimental_option("prefs", prefs)

    # service = ChromeService(ChromeDriverManager().install())
    # driver = webdriver.Chrome(service=service, options=chrome_options)
    # driver.capabilities["pageLoadStrategy"] = PAGE_LOAD_STRATEGY
    # return driver

    """
    폐쇄망 환경 대응: BaseScraper의 _create_webdriver 사용
    - 환경변수 SELENIUM_DRIVER_PATH에 chromedriver 경로 설정 시 해당 경로 사용
    - 없으면 PATH에서 chromedriver 탐지
    - SeleniumManager 우회 (인터넷 연결 불필요)
    """    
    scraper = BaseScraper()
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
#    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return scraper._create_webdriver(options)

# ==================================================
# 목록 로딩 대기
# ==================================================
def wait_for_list(driver, wait):
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.list_table_wrap table tbody tr")
            )
        )
        return True
    except TimeoutException:
        logger.error("[CHECK] 목록 테이블 로딩 실패")
        return False

# ==================================================
# 본문 정제
# ==================================================
def clean_content_text(text: str) -> str | None:
    if not text:
        return None
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

# ==================================================
# 상세 파싱
# ==================================================
def parse_detail_html(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("div.title")
    date_el = soup.select_one("div.date")
    content_el = soup.select_one("div.cont_area")

    raw_content = content_el.get_text(separator="\n", strip=True) if content_el else None

    return {
        "org_name": ORG_NAME,
        "title": title_el.get_text(strip=True) if title_el else None,
        "date": date_el.get_text(strip=True) if date_el else None,
        "content": clean_content_text(raw_content),
        "detail_url": url,
    }

# ==================================================
# 전체 스크래핑
# ==================================================
def scrape_all(start_date=None, end_date=None):
    driver = create_driver(HEADLESS)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)
    results = []

    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    try:
        logger.info(f"[SCRAPE] CREFIA 자율규제 공고 시작 ({start_dt} ~ {end_dt})")

        if check_url_status(BASE_LIST_URL)["status"] != URLStatus.OK:
            logger.error("[CHECK] 목록 URL 접근 실패")
            return

        driver.get(BASE_LIST_URL)

        if not wait_for_list(driver, wait):
            return

        page = 1
        while True:
            logger.info(f"[SCRAPE] 페이지 {page}")

            rows = driver.find_elements(
                By.CSS_SELECTOR,
                "div.list_table_wrap table tbody tr"
            )

            if not rows:
                logger.info("[SCRAPE] 더 이상 목록 없음")
                break

            for idx, row in enumerate(rows, 1):
                try:
                    title = row.find_element(By.CSS_SELECTOR, "td.align_L a").text.strip()
                except:
                    continue

                logger.info(f"[CHECK] {title}")

                # 상세 이동 (onclick)
                driver.execute_script("arguments[0].click();", row)
                time.sleep(0.8)

                detail_url = driver.current_url
                detail_html = driver.page_source
                detail = parse_detail_html(detail_html, detail_url)

                # 날짜 필터 (date 형식이 없을 수도 있음 → 존재 시만 적용)
                if detail["date"]:
                    try:
                        date_obj = datetime.strptime(detail["date"], "%Y.%m.%d").date()
                        if not (start_dt <= date_obj <= end_dt):
                            driver.back()
                            wait_for_list(driver, wait)
                            continue
                    except:
                        pass

                results.append(detail)
                logger.info(f"[SCRAPE] [{idx}/{len(rows)}] 수집 완료")

                driver.back()
                wait_for_list(driver, wait)

            # 다음 페이지
            try:
                next_btn = driver.find_element(By.LINK_TEXT, str(page + 1))
                driver.execute_script("arguments[0].click();", next_btn)
                wait_for_list(driver, wait)
                page += 1
            except NoSuchElementException:
                logger.info("[SCRAPE] 마지막 페이지")
                break

        output_path = os.path.join(
            OUTPUT_DIR,
            f"crefia_legnotice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        logger.info(f"[SCRAPE] 총 {len(results)}건 저장 완료")

    finally:
        driver.quit()
        logger.info("[SCRAPE] 드라이버 종료")

# ==================================================
# Health Check
# ==================================================
def crefia_legnotice_health_check() -> dict:
    start_time = time.perf_counter()
    check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
        "org_name": ORG_NAME,
        "target": "여신금융협회 > 정보센터 > 자율규제 제·개정 공고",
        "check_time": check_time,
        "status": "FAIL",
        "checks": {
            "list_page": {
                "url": BASE_LIST_URL,
                "status": "FAIL",
                "message": "",
                "elapsed": None,
            },
            "detail_page": {
                "url": None,
                "status": "FAIL",
                "message": "",
                "elapsed": None,
            },
        },
        "error": None,
        "elapsed": None,
    }

    driver = create_driver(HEADLESS)
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    try:
        # ----------------------
        # 1. 목록 페이지 체크
        # ----------------------
        t0 = time.perf_counter()

        driver.get(BASE_LIST_URL)

        if not wait_for_list(driver, wait):
            raise RuntimeError("목록 페이지 로딩 실패")

        rows = driver.find_elements(
            By.CSS_SELECTOR,
            "div.list_table_wrap table tbody tr"
        )

        if not rows:
            raise RuntimeError("목록 없음")

        first_row = rows[0]
        title = first_row.find_element(By.CSS_SELECTOR, "td.align_L a").text.strip()

        result["checks"]["list_page"].update({
            "status": "OK",
            "message": f"목록 1건 추출 성공 ({title})",
            "elapsed": round(time.perf_counter() - t0, 3),
        })

        # ----------------------
        # 2. 상세 페이지 체크
        # ----------------------
        t1 = time.perf_counter()

        link = first_row.find_element(By.CSS_SELECTOR, "td.align_L a")
        driver.execute_script("arguments[0].click();", link)
        time.sleep(0.8)

        detail_url = driver.current_url
        detail_html = driver.page_source
        detail = parse_detail_html(detail_html, detail_url)

        if not detail.get("content"):
            raise RuntimeError("상세 페이지 본문 추출 실패")

        result["checks"]["detail_page"].update({
            "url": detail_url,
            "status": "OK",
            "message": "상세 페이지 접근 및 본문 영역 확인",
            "elapsed": round(time.perf_counter() - t1, 3),
        })

        result["status"] = "OK"
        return result

    except Exception as e:
        result["error"] = str(e)
        return result

    finally:
        result["elapsed"] = round(time.perf_counter() - start_time, 3)
        driver.quit()

# ==================================================
# CLI
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    parser.add_argument("--check", action="store_true", help="CREFIA 자율규제 제·개정 공고 Health Check 실행")

    args = parser.parse_args()

    if args.check:
        health_result = crefia_legnotice_health_check()
        print(json.dumps(health_result, ensure_ascii=False, indent=2))
        sys.exit(0)

    scrape_all(start_date=args.start_date, end_date=args.end_date)
