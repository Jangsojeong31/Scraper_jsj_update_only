# kfb_legnotice_scraper_v2.py
# 은행연합회-공시·자료실→ 법규·규제→규제운영→ 자율규제 제정∙개정예고

import os
import sys
import json
import time
import re

# ==================================================
# 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
#from webdriver_manager.chrome import ChromeDriverManager
from common.base_scraper import BaseScraper


from common.common_logger import get_logger

ORG_NAME = "KFB"
logger = get_logger("KFB")

# ==================================================
# URL / 설정
# ==================================================
LIST_URL = "https://www.kfb.or.kr/publicdata/reform_notice.php"
DETAIL_URL_TEMPLATE = "https://www.kfb.or.kr/publicdata/reform_notice_view.php?idx={idx}"

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
    options.add_argument("--window-size=1920x1080")
#    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return scraper._create_webdriver(options)
# ==================================================
# 의견청취기간 날짜 정제
# ==================================================
def parse_opinion_period(text):
    text = text.replace(" ", "")
    match = re.split(r"[~\-]", text)
    if len(match) >= 2:
        try:
            start_date = datetime.strptime(match[0], "%Y.%m.%d.").date()
            end_date = datetime.strptime(match[1], "%Y.%m.%d.").date()
            return start_date, end_date
        except:
            return None, None
    elif len(match) == 1:
        try:
            start_date = datetime.strptime(match[0], "%Y.%m.%d.").date()
            return start_date, start_date
        except:
            return None, None
    return None, None

# ==================================================
# 상세 페이지 파싱
# ==================================================
def parse_detail_page(html, detail_url):
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("li.title_result")
    title = title_el.get_text(strip=True) if title_el else None

    content_el = soup.select_one("li.txt")
    content = content_el.get_text("\n", strip=True) if content_el else None

    # 의견청취기간
    period_el = soup.select_one("span.type02")
    period_text = period_el.get_text(strip=True) if period_el else ""
    start_date, end_date = parse_opinion_period(period_text)

    return {
        "org_name": ORG_NAME,
        "title": title,
        "start_date": start_date.strftime("%Y-%m-%d") if start_date else None,
        "end_date": end_date.strftime("%Y-%m-%d") if end_date else None,
        "content": content,
        "detail_url": detail_url
    }

# ==================================================
# 목록 페이지 tr 추출
# ==================================================
def parse_list_rows(driver):
    """
    현재 페이지(driver.page_source)에서 목록 테이블의 tr(row) 리스트를 반환.
    헤더 row는 제외됨.
    """
    soup = BeautifulSoup(driver.page_source, "html.parser")
    rows = soup.select(".panListArea table tr")[1:]  # 헤더 제외
    return rows

# ==================================================
# 다음 페이지 이동
# ==================================================
def go_to_next_page(driver, current_page):
    """
    현재 페이지에서 다음 페이지로 이동 시도.
    이동 성공 시 True, 마지막 페이지면 False 반환.
    """
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    # '다음' 버튼 우선
    next_page = soup.select_one(".pageArea a[title='다음']")
    if next_page and "javascript:pageRun(" in next_page.get("href", ""):
        driver.execute_script(next_page.get("href"))
        time.sleep(1)
        return True
    
    # 숫자 페이지 클릭
    page_links = soup.select(".pageArea a")
    for a in page_links:
        if a.get_text(strip=True) == str(current_page + 1):
            driver.execute_script(a.get("href"))
            time.sleep(1)
            return True

    return False  # 더 이상 페이지 없음

# ==================================================
# 전체 페이지 반복 스크래핑
# ==================================================
def scrape_all(start_date=None, end_date=None):
    logger.info("KFB 규정 예고 스크래핑 시작")

    today = datetime.today().date()
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else today - timedelta(days=30)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today

    driver = create_driver()
    driver.get(LIST_URL)
    time.sleep(2)

    results = []
    page = 1

    while True:
        logger.info(f"[SCRAPE] 페이지 {page} 처리")

        rows = parse_list_rows(driver)
        if not rows:
            logger.info("더 이상 목록 없음 → 종료")
            break

        for idx, row in enumerate(rows, start=1):
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            # 상세 페이지 링크
            link = cols[2].find("a")
            if not link:
                continue
            href = link.get("href", "")
            notice_idx = href.replace("Javascript:readRun(", "").replace(");", "")
            detail_url = DETAIL_URL_TEMPLATE.format(idx=notice_idx)

            # 의견청취기간
            period_text = cols[3].get_text(strip=True)
            start_date_item, end_date_item = parse_opinion_period(period_text)

            logger.info(f"[start_date_item] : {start_date_item} 처리")
            logger.info(f"[end_date_item] : {end_date_item} 처리")

            # 날짜 범위 체크
            if not start_date_item:
                continue
            if start_dt <= start_date_item <= end_dt or (end_date_item and start_dt <= end_date_item <= end_dt):
                logger.info(f"[{idx}] 수집: {detail_url}")
                driver.get(detail_url)
                time.sleep(1)
                data = parse_detail_page(driver.page_source, detail_url)
                results.append(data)
                driver.back()
                time.sleep(1)
            else:
                logger.info(f"[{idx}] 날짜 범위 외 스킵: {cols[2].get_text(strip=True)} ({period_text})")

        # 다음 페이지 이동
        if not go_to_next_page(driver, page):
            logger.info("마지막 페이지 도달 → 종료")
            break
        page += 1

    # JSON 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"kfb_legnotice_{timestamp}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    driver.quit()
    logger.info(f"JSON 저장 완료: {output_file}")

# ==================================================
# Health Check (KFB 자율규제 제정·개정예고)
# ==================================================
from common.common_http import check_url_status
from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType
from common.health_schema import base_health_output
from common.health_mapper import apply_health_error
from common.constants import URLStatus
from common.url_health_mapper import map_urlstatus_to_health_error

def kfb_legnotice_health_check() -> dict:
    start_time = time.perf_counter()

    result = base_health_output(
        auth_src="은행연합회 > 법규·규제 > 규제운영 > 자율규제 제정·개정예고",
        scraper_id="KFB_LEGNOTICE",
        target_url=LIST_URL,
    )   

    driver = create_driver()

    try:

        # ======================================================
        # 0️⃣ HTTP 접근성 사전 체크
        # ======================================================
        http_result = check_url_status(LIST_URL,
                                       use_selenium=True,      # 핵심
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
                LIST_URL,
            )
                
        # 1️⃣ 목록 페이지
        driver.get(LIST_URL)
        time.sleep(2)

        t0 = time.time()
        rows = parse_list_rows(driver)
        if not rows:
            raise HealthCheckError(
                HealthErrorType.NO_LIST_DATA,
                "목록 데이터 없음",
                target="table.panListArea tr"
            )

        cols = rows[0].find_all("td")
        if len(cols) < 4:
            raise HealthCheckError(
                HealthErrorType.PARSE_ERROR,
                "목록 컬럼 파싱 실패",
                target="table.panListArea td"
            )

        result["checks"]["list"] = {
            "success": True,
            "url": LIST_URL,
            "elapsed": round(time.time() - t0, 3),
        }

        link = cols[2].find("a")
        if not link:
            raise HealthCheckError(
                HealthErrorType.NO_DETAIL_URL,
                "상세 링크 없음",
                target="cols[2] > a"
            )

        notice_idx = link.get("href", "").replace("Javascript:readRun(", "").replace(");", "")
        detail_url = DETAIL_URL_TEMPLATE.format(idx=notice_idx)

        # 2️⃣ 상세 페이지
        driver.get(detail_url)
        time.sleep(1)

        detail = parse_detail_page(driver.page_source, detail_url)
        if not detail.get("content"):
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY,
                "상세 본문 비어 있음",
                target=detail_url
            )


        result["checks"]["detail"] = {
            "success": True,
            "url": detail_url,
            "content_length": len(detail.get("content")),
            "elapsed": round(time.time() - t0, 3),
        }

        # ==================================================
        # FINISH
        # ==================================================
        result["ok"] = True
        result["status"] = "OK"

        return result

    except HealthCheckError as e:
        apply_health_error(result, e)
        return result

    except Exception as e:
        apply_health_error(
            result,
            HealthCheckError(
                HealthErrorType.UNKNOWN,
                str(e)
            )
        )
        return result

    finally:
        result["elapsed"] = round(time.perf_counter() - start_time, 3)
        driver.quit()

# ==================================================
# scheduler call
# ==================================================
def run():
    scrape_all()
    
# ==================================================
# CLI 실행
# ==================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    parser.add_argument(
            "--check",
            action="store_true",
            help="Health Check 실행"
        )
    
    args = parser.parse_args()

    if args.check:
        health_result = kfb_legnotice_health_check()
        print(json.dumps(health_result, ensure_ascii=False, indent=2))
        sys.exit(0)

    scrape_all(start_date=args.start_date, end_date=args.end_date)
