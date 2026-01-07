# bok_legnotice_scraper_v2.py
# BOK 규정예고 / Selenium 기반 스크래퍼
# 데이터 있음 / 없음 완전 분기 처리 버전

import os
import sys
import json
import argparse
from time import time
from datetime import datetime, timedelta
from urllib.parse import urljoin
from queue import Queue
from threading import Thread

from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

# ==================================================
# 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ==================================================
# 공통 모듈
# ==================================================
from common.common_logger import get_logger
from common.common_http import check_url_status
from common.constants import URLStatus, LegalDocProvided
from common.base_scraper import BaseScraper

from common.health_schema import base_health_output
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_mapper import apply_health_error, map_url_status_to_health_error

# ==================================================
# 설정
# ==================================================
logger = get_logger("bok_legnotice")
ORG_NAME = LegalDocProvided.BOK

BASE_URL = "https://www.bok.or.kr"
LIST_URL = "https://www.bok.or.kr/portal/singl/law/listBbs.do?bbsSe=rule&menuNo=200203"
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

POOL_SIZE = int(os.getenv("BOK_DRIVER_POOL_SIZE", "3"))

# ==================================================
# WebDriver 생성
# ==================================================
def create_driver():
    scraper = BaseScraper()
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    return scraper._create_webdriver(options)

# ==================================================
# 날짜 처리
# ==================================================
def resolve_search_dates(start_date=None, end_date=None):
    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    return start_dt, end_dt

# ==================================================
# 검색 적용 (데이터 있음/없음 분기)
# ==================================================
def apply_date_search(driver, start_date=None, end_date=None):
    wait = WebDriverWait(driver, 30)
    sdate, edate = resolve_search_dates(start_date, end_date)

    logger.info(f"[SCRAPE] 검색 날짜 설정: {sdate} ~ {edate}")

    wait.until(EC.presence_of_element_located((By.ID, "sdate")))

    driver.execute_script(
        "document.getElementById('sdate').value = arguments[0];",
        sdate.strftime("%Y-%m-%d"),
    )
    driver.execute_script(
        "document.getElementById('edate').value = arguments[0];",
        edate.strftime("%Y-%m-%d"),
    )
    driver.execute_script("document.getElementById('pageIndex').value = '1';")
    driver.execute_script("document.getElementById('schFrom').submit();")

    # ✅ 결과 있음 OR 결과 없음 → 검색 완료
    def search_finished(d):
        if d.find_elements(By.CSS_SELECTOR, "div.bdLine.type2.type3 ul > li"):
            return True
        if d.find_elements(By.CSS_SELECTOR, "div.bdLine.type2 .i-no-data"):
            return True
        return False

    wait.until(search_finished)

# ==================================================
# 목록 파싱
# ==================================================
def parse_list(driver):
    rows = driver.find_elements(By.CSS_SELECTOR, "div.bdLine.type2.type3 ul > li")

    if not rows:
        return []

    items = []
    for row in rows:
        try:
            title = row.find_element(By.CSS_SELECTOR, ".titlesub").text.strip()
            date = row.find_element(By.CSS_SELECTOR, ".date").text.strip()
            a = row.find_element(By.TAG_NAME, "a")

            items.append({
                "org_name": ORG_NAME,
                "title": title,
                "date": date,
                "detail_url": urljoin(BASE_URL, a.get_attribute("href")),
            })
        except Exception:
            continue

    return items

# ==================================================
# 상세 페이지 워커
# ==================================================
def scrape_detail_worker(queue, results, driver_pool, start_dt, end_dt):
    while True:
        try:
            item = queue.get(block=False)
        except Exception:
            break

        driver = driver_pool.get()
        try:
            driver.get(item["detail_url"])

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.dbdata"))
            )

            dbdata_div = driver.find_element(By.CSS_SELECTOR, "div.dbdata")
            paragraphs = dbdata_div.find_elements(By.XPATH, ".//p|.//div")
            item["content"] = "\n".join(p.text.strip() for p in paragraphs if p.text.strip())

            item_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
            if start_dt <= item_date <= end_dt:
                results.append(item)

        except Exception as e:
            item["content"] = ""
            results.append(item)
            logger.warning(f"[SCRAPE] 상세 실패: {item['title']} / {e}")

        finally:
            driver_pool.put(driver)
            queue.task_done()

# ==================================================
# 메인 스크래핑
# ==================================================
def scrape_all(start_date=None, end_date=None):
    main_driver = create_driver()
    driver_pool = None
    all_results = []

    start_dt, end_dt = resolve_search_dates(start_date, end_date)

    try:
        logger.info(f"[SCRAPE] BOK 규정예고 시작 ({start_dt} ~ {end_dt})")

        if check_url_status(LIST_URL)["status"] != URLStatus.OK:
            raise RuntimeError("LIST_URL 접근 실패")

        main_driver.get(LIST_URL)
        apply_date_search(main_driver, start_date, end_date)

        driver_pool = Queue()
        for _ in range(POOL_SIZE):
            driver_pool.put(create_driver())

        page_number = 1
        while True:
            items = parse_list(main_driver)
            logger.info(f"[SCRAPE] 페이지 {page_number} / 목록 {len(items)}건")

            if not items:
                break

            queue = Queue()
            for item in items:
                queue.put(item)

            threads = []
            for _ in range(POOL_SIZE):
                t = Thread(
                    target=scrape_detail_worker,
                    args=(queue, all_results, driver_pool, start_dt, end_dt),
                    daemon=True,
                )
                t.start()
                threads.append(t)

            for t in threads:
                t.join()

            try:
                next_page = main_driver.find_element(By.LINK_TEXT, str(page_number + 1))
                main_driver.execute_script("arguments[0].click();", next_page)

                WebDriverWait(main_driver, 20).until(
                    lambda d: (
                        d.find_elements(By.CSS_SELECTOR, "div.bdLine.type2.type3 ul > li")
                        or d.find_elements(By.CSS_SELECTOR, "div.bdLine.type2 .i-no-data")
                    )
                )

                page_number += 1
            except NoSuchElementException:
                break

        output_path = os.path.join(
            OUTPUT_DIR,
            f"bok_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        logger.info(f"[SCRAPE] 저장 완료: {len(all_results)}건")

    finally:
        if driver_pool:
            while not driver_pool.empty():
                try:
                    driver_pool.get().quit()
                except Exception:
                    pass

        try:
            main_driver.quit()
        except Exception:
            pass

        logger.info("[SCRAPE] 드라이버 종료")

# ==================================================
# Health Check
# ==================================================
from common.common_http import check_url_status
from common.health_mapper import map_url_status_to_health_error
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error

from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType

# ==================================================
# Health Check
# ==================================================
def bok_legnotice_health_check() -> dict:
    """
    BOK 규정예고 Health Check
    - common_http 결과를 그대로 사용
    - NetworkState 재판별 금지
    """

    start_ts = time()

    result = base_health_output(
        auth_src="한국은행-규정예고",
        scraper_id="BOK_LEGNOTICE",
        target_url=LIST_URL,
    )

    driver = None

    try:
        # ==================================================
        # HTTP / Network 체크
        # ==================================================
        # def check_url_status(
        #     url: str,
        #     timeout: int = REQUEST_TIMEOUT,
        #     use_selenium: bool = False,
        #     allow_fallback: bool = True           
        http_result = check_url_status(LIST_URL,allow_fallback=True,)
        url_status = http_result["status"]

        result["checks"]["http"] = {
            "ok": url_status == URLStatus.OK,
            "status_code": http_result["http_code"],
            "engine": http_result["engine"],
            "verify_ssl": http_result.get("verify_ssl", True),
        } 

        if url_status != URLStatus.OK:
            raise HealthCheckError(
                error_type=map_url_status_to_health_error(http_result["status"]),
                message=http_result["error"] or http_result["status"].name,
                target=LIST_URL,
            )  

        # ==================================================
        # 2️⃣ 목록 접근
        # ==================================================
        driver = create_driver()
        driver.get(LIST_URL)

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.bdLine.type2.type3 ul li")
            )
        )

        items = parse_list(driver)

        if not items:
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA,
                "규정예고 목록이 비어 있음",
                "div.bdLine.type2.type3 ul > li",
            )

        result["checks"]["list"] = {
            "ok": True,
            "count": len(items),
        }

        # ==================================================
        # 3️⃣ 상세 페이지 접근
        # ==================================================
        first_item = items[0]
        detail_url = first_item.get("detail_url")

        if not detail_url:
            raise HealthCheckError(
                HealthErrorType.NO_DETAIL_URL,
                "상세 URL 누락",
                "a[href]",
            )

        driver.get(detail_url)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.dbdata"))
        )

        content = driver.find_element(By.CSS_SELECTOR, "div.dbdata").text.strip()

        if not content:
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY,
                "본문 비어 있음",
                "div.dbdata",
            )

        result["checks"]["detail"] = {
            "ok": True,
            "url": detail_url,
            "content_length": len(content),
        }

        result["ok"] = True
        result["status"] = "OK"

    except HealthCheckError as he:
        apply_health_error(result, he)

    except TimeoutException as e:
        apply_health_error(
            result,
            HealthCheckError(
                HealthErrorType.TIMEOUT,
                "페이지 로딩 Timeout",
                str(e),
            ),
        )

        return result   #여기서 끝
    # except Exception as e:
    #     # print(f"⚠ Exception 결과 {result}")
    #     # print(f"⚠ Exception 결과 {e}")
    #     apply_health_error(
    #         result,
    #         HealthCheckError(
    #             HealthErrorType.UNEXPECTED_ERROR,
    #             "UNKNOWN",
    #             str(e),
    #         ),
    #     )

    finally:
        result["elapsed_ms"] = int((time() - start_ts) * 1000)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return result

# ==================================================
# scheduler call
# ==================================================
def run():
    scrape_all()

# ==================================================
# CLI
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)

    parser.add_argument(
        "--check",
        action="store_true",
        help="한국은행-운영 및 법규→ 법규정보→ 규정 예고 Health Check 실행"
    )
    
    args = parser.parse_args()

    if args.check:
        health_result = bok_legnotice_health_check()
        print(json.dumps(health_result, ensure_ascii=False, indent=2))
        sys.exit(0)
        
    scrape_all(start_date=args.start_date, end_date=args.end_date)
