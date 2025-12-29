# kofia_legnotice_scraper_v2.py
# 금융투자협회-법규정보시스템 → 규정 제∙개정 예고
# LIST_URL = "https://law.kofia.or.kr/service/revisionNotice/revisionNoticeListframe.do"
# DETAIL_BASE_URL = "https://law.kofia.or.kr/service/revisionNotice/revisionNoticeViewframe.do"

import os
import sys
import json
import time
from datetime import datetime, timedelta

# 프로젝트 루트 sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
#from webdriver_manager.chrome import ChromeDriverManager

from common.common_logger import get_logger
from common.common_http import check_url_status
from common.constants import CHROME_OPTIONS, LegalDocProvided
from common.base_scraper import BaseScraper

ORG_NAME = LegalDocProvided.KOFIA
logger = get_logger("KOFIA")

# URL / OUTPUT
LIST_URL = "https://law.kofia.or.kr/service/revisionNotice/revisionNoticeListframe.do"
DETAIL_BASE_URL = "https://law.kofia.or.kr/service/revisionNotice/revisionNoticeViewframe.do"
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================================================
# WebDriver 생성
# ==================================================
def create_driver():
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
# 날짜 문자열 -> date
# ==================================================
def parse_date(text):
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except:
        return None

# ==================================================
# 상세 페이지 파싱
# ==================================================
def parse_detail_page(driver):
    try:
        title = driver.find_element(By.XPATH, "//th[normalize-space()='규정명']/following-sibling::td//p").text.strip()
    except:
        title = None
    try:
        start_date = parse_date(driver.find_element(By.XPATH, "//th[normalize-space()='예고시작일']/following-sibling::td//p").text)
    except:
        start_date = None
    try:
        end_date = parse_date(driver.find_element(By.XPATH, "//th[normalize-space()='예고종료일']/following-sibling::td//p").text)
    except:
        end_date = None
    try:
        content = driver.find_element(By.CSS_SELECTOR, "div.storyIn").text.strip()
    except:
        content = None
    return title, start_date, end_date, content

# ==================================================
# 페이지 내 목록 처리 함수
# ==================================================
def process_rows(driver, wait, start_dt, end_dt):
    rows = driver.find_elements(By.CSS_SELECTOR, "table.brdComList tbody tr")
    logger.info(f"[SCRAPE] 현재 페이지 목록 수: {len(rows)}")
    results = []

    for idx, row in enumerate(rows, start=1):
        try:
            link = row.find_element(By.CSS_SELECTOR, "td:nth-child(2) a")
        except:
            continue

        # 예고 시작/종료일 추출
        start_text = row.find_element(By.CSS_SELECTOR, "td:nth-child(4)").text.strip()
        end_text = row.find_element(By.CSS_SELECTOR, "td:nth-child(5)").text.strip()
        start_date_item = parse_date(start_text)
        end_date_item = parse_date(end_text)

        # 날짜 범위 체크
        if not start_date_item:
            continue
        if not (start_dt <= start_date_item <= end_dt or (end_date_item and start_dt <= end_date_item <= end_dt)):
            logger.info(f"[{idx}] 날짜 범위 외 스킵: {link.text.strip()} ({start_text}~{end_text})")
            continue

        # 상세 페이지 이동
        logger.info(f"[{idx}] 처리 중: {link.text.strip()}")
        driver.execute_script("arguments[0].click();", link)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.storyIn")))

        title, start_d, end_d, content = parse_detail_page(driver)
        results.append({
            "org_name": ORG_NAME,
            "title": title,
            "start_date": start_d.isoformat() if start_d else None,
            "end_date": end_d.isoformat() if end_d else None,
            "content": content,
            "detail_url": DETAIL_BASE_URL
        })

        driver.back()
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.brdComList")))

    return results

# ==================================================
# 전체 스크래핑
# ==================================================
def scrape_all(start_date=None, end_date=None):

    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    logger.info(f"[GENERAL] [SCRAPE] KOFIA 규정 제·개정 예고 스크래핑 시작 (기간: {start_dt} ~ {end_dt})")

    driver = create_driver()
    wait = WebDriverWait(driver, 20)

    logger.info(f"[CHECK] {LIST_URL}")
    driver.get(LIST_URL)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.brdComList")))

    results = []
    page = 1

    while True:
        logger.info(f"[GENERAL] [SCRAPE] 페이지 {page} 처리")
        page_results = process_rows(driver, wait, start_dt, end_dt)
        if not page_results:
            logger.info("마지막 페이지 도달 또는 목록 없음 → 종료")
            break
        results.extend(page_results)

        # 다음 페이지 클릭
        try:
            next_page_link = driver.find_element(By.XPATH, f"//a[text()='{page + 1}']")
            driver.execute_script("arguments[0].click();", next_page_link)
            time.sleep(1)
            page += 1
        except:
            logger.info("마지막 페이지 도달 → 종료")
            break

    # JSON 저장
    output_file = os.path.join(OUTPUT_DIR, f"kofia_legnotice.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    driver.quit()
    logger.info(f"JSON 저장 완료: {output_file}")

# -------------------------------------------------
# Health Check 모드
# -------------------------------------------------
from common.common_http import check_url_status
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error
from common.constants import URLStatus
from common.url_health_mapper import map_urlstatus_to_health_error

# -------------------------------------------------
# Health Check 모드 (수정본)
# -------------------------------------------------
def kofia_legnotice_health_check() -> dict:
    """
    KOFIA 규정 제·개정 예고 Health Check (v2)
    - 명시적 HealthErrorType raise 패턴 적용
    """

    start_time = time.perf_counter()
    
    # 1. 표준 출력 스키마 초기화
    result = base_health_output(
        auth_src="금융투자협회 > 법규정보시스템 > 규정 제·개정 예고",
        scraper_id="KOFIA_LEGNOTICE",
        target_url=LIST_URL,
    )

    driver = None
    try:

        # ======================================================
        # HTTP 접근성 사전 체크
        # ======================================================
        http_result = check_url_status(
            LIST_URL,
            use_selenium=True,
            allow_fallback=False,
        )

        result["checks"]["http"] = {
            "ok": http_result["status"] == URLStatus.OK,
            "status": http_result["status"].name,
            "status_code": http_result["http_code"],
        }

        if http_result["status"] != URLStatus.OK:
            raise HealthCheckError(
                map_urlstatus_to_health_error(http_result["status"]),
                "목록 페이지 HTTP 접근 실패",
                target=LIST_URL,
            )
                
        # ---------------------------------
        # 1️⃣ 목록 페이지 체크
        # ---------------------------------
        t0 = time.perf_counter()
        
        try:
            driver = create_driver()
            wait = WebDriverWait(driver, 20)
            logger.info(f"[HEALTH] KOFIA 목록 접근: {LIST_URL}")
            driver.get(LIST_URL)
        except Exception as e:
            raise HealthCheckError(
                HealthErrorType.DRIVER_ERROR, 
                f"드라이버 생성 또는 페이지 로드 실패: {str(e)}", 
                LIST_URL
            )

        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.brdComList")))
        except:
            raise HealthCheckError(
                HealthErrorType.TIMEOUT, 
                "목록 테이블 로딩 시간 초과", 
                "table.brdComList"
            )

        rows = driver.find_elements(By.CSS_SELECTOR, "table.brdComList tbody tr")
        if not rows:
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA, 
                "목록 데이터가 비어 있음", 
                "table.brdComList tbody tr"
            )

        row = rows[0]
        try:
            link = row.find_element(By.CSS_SELECTOR, "td:nth-child(2) a")
            title = link.text.strip()
        except:
            raise HealthCheckError(
                HealthErrorType.TAG_MISMATCH, 
                "목록 내 제목/링크 태그 구조 변경됨", 
                "td:nth-child(2) a"
            )

        result["checks"]["list"] = {
            "status": "OK",
            "success": True,
            "message": f"목록 1건 추출 성공 ({title})",
            "elapsed": round(time.perf_counter() - t0, 3),
        }

        # ---------------------------------
        # 2️⃣ 상세 페이지 체크
        # ---------------------------------
        t1 = time.perf_counter()

        logger.info(f"[HEALTH] 상세 접근: {title}")
        driver.execute_script("arguments[0].click();", link)

        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.storyIn")))
        except:
            raise HealthCheckError(
                HealthErrorType.TIMEOUT, 
                "상세 페이지 본문 로딩 실패", 
                "div.storyIn"
            )

        _, _, _, content = parse_detail_page(driver)
        if not content:
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY, 
                "상세 페이지 본문 내용이 비어 있음", 
                "div.storyIn.text"
            )

        result["checks"]["detail"] = {
            "url": driver.current_url,
            "status": "OK",
            "success": True,
            "message": "상세 페이지 접근 및 본문 영역 확인",
            "elapsed": round(time.perf_counter() - t1, 3),
        }

        # 전체 성공 시 상태 업데이트
        result["ok"] = True
        result["status"] = "OK"

    except HealthCheckError as he:
        # 명시적으로 발생시킨 에러 처리
        logger.error(f"[HEALTH] [{he.error_type}] {he.message}")
        result["ok"] = False
        result["status"] = "FAIL"
        result["error"] = {
            "type": he.error_type,
            "message": he.message,
            "target": he.target
        }
    except Exception as e:
        # 예상치 못한 일반 예외 처리
        logger.exception("[HEALTH] 알 수 없는 오류 발생")
        result["ok"] = False
        result["status"] = "FAIL"
        result["error"] = {
            "type": HealthErrorType.UNEXPECTED_ERROR,
            "message": str(e),
            "target": "kofia_legnotice_health_check_unknown"
        }

    finally:
        result["elapsed_ms"] = int((time.perf_counter() - start_time) * 1000)
        if driver:
            driver.quit()
        return result
    
# ==================================================
# scheduler call
# ==================================================
def run():
    scrape_all()
    
# ==================================================
# main
# ==================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    parser.add_argument("--check", action="store_true", help="Health Check 실행")

    args = parser.parse_args()

    if args.check:
        result = kofia_legnotice_health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    scrape_all(start_date=args.start_date, end_date=args.end_date)
