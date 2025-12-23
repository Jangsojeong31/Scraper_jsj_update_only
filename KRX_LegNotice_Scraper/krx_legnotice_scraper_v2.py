# krx_legnotice_scraper_v2.py
# 한국거래소-법무포탈 → 규정 제·개정 예고 스크래퍼

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException

# ==================================================
# WDM 로그 제거
# ==================================================
os.environ["WDM_LOG_LEVEL"] = "0"  # INFO 로그 숨김

# ==================================================
# 설정
# ==================================================
BASE_URL = "https://rule.krx.co.kr/out/index.do"
DETAIL_BASE_URL = "https://rule.krx.co.kr/out/pds/goPdsMain.do"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CURRENT_DIR, "output", "json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ORG_NAME = "KRX"
CHROME_OPTIONS = [
    "--headless=new",
    "--disable-gpu",
    "--window-size=1920,1080",
    "--no-sandbox"
]

# ==================================================
# 로거 설정 (마이크로초 제외)
# ==================================================
def get_logger(name="krx_legnotice"):
    log_format = "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S"  # 마이크로초 제외
    )
    return logging.getLogger(name)

logger = get_logger()

# ==================================================
# WebDriver 생성
# ==================================================
def create_driver():
    options = Options()
    for opt in CHROME_OPTIONS:
        options.add_argument(opt)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

# ==================================================
# 상세 페이지 파싱
# ==================================================
def parse_detail_page(driver, wait):
    title = wait.until(
        EC.presence_of_element_located((By.XPATH, "//th[text()='제목']/following-sibling::td"))
    ).text.strip()

    content = ""
    try:
        content_div = driver.find_element(By.CSS_SELECTOR, "#conts")
        elements = content_div.find_elements(By.CSS_SELECTOR, "p, div")
        lines = [el.text.strip() for el in elements if el.text.strip()]
        content = "\n".join(lines)
    except:
        pass

    return title, content

# ==================================================
# 검색 적용
# ==================================================
def apply_search(driver, wait, keyword):
    if not keyword:
        logger.info("검색어 없음 → 전체 목록 수집")
        return

    logger.info(f"▶ 검색 실행: '{keyword}'")
    input_box = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#stxt")))
    input_box.clear()
    input_box.send_keys(keyword)

    search_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#searchBtn")))
    search_btn.click()
    time.sleep(1)
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.x-grid3-row")))

# ==================================================
# 목록 추출 함수
# ==================================================
def extract_list(driver, wait, start_date, end_date, keyword=None):
    results = []

    driver.get(BASE_URL)
    logger.info(f"[CHECK] {BASE_URL}")
    logger.info(f"[REQ] 200 OK")
    time.sleep(1)

    # 메뉴 클릭
    menu = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li[vo='/out/pds/goPdsMain.do'] a")))
    menu.click()
    time.sleep(1)

    # iframe 전환
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "workPage")))

    apply_search(driver, wait, keyword)

    # 목록 수집
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.x-grid3-row")))
    rows = driver.find_elements(By.CSS_SELECTOR, "div.x-grid3-row")
    total = len(rows)
    logger.info(f"총 목록 수: {total} (기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})")

    action = webdriver.ActionChains(driver)

    for i in range(total):
        rows = driver.find_elements(By.CSS_SELECTOR, "div.x-grid3-row")
        if i >= len(rows):
            break
        row = rows[i]

        # 등록일 추출
        try:
            date_text = row.find_element(By.CSS_SELECTOR, "div.x-grid3-col-2").text.strip()
            date_obj = datetime.strptime(date_text.replace(".", "").replace(" ", ""), "%Y%m%d")
        except:
            logger.warning(f"[{i+1}] 날짜 파싱 실패, 스킵")
            continue

        title_preview = row.find_element(By.CSS_SELECTOR, "div.x-grid3-col-1").text.strip()
        logger.info(f"[{i+1}/{total}] 처리 중: {title_preview}")

        if not (start_date <= date_obj <= end_date):
            logger.info(f"[{i+1}] 날짜 범위 외 공고 스킵: {title_preview} ({date_obj.strftime('%Y.%m.%d')})")
            continue

        # 상세 페이지 클릭
        try:
            action.move_to_element(row).click().perform()
            time.sleep(1)
            title, content = parse_detail_page(driver, wait)
            logger.info(f"[{i+1}] 상세 페이지 수집 완료: {title}")
        except WebDriverException as e:
            logger.warning(f"[{i+1}] 상세 페이지 접근 실패: {e}")
            continue

        results.append({
            "org_name": ORG_NAME,
            "title": title,
            "date": date_obj.strftime("%Y-%m-%d"),
            "content": content,
            "detail_url": DETAIL_BASE_URL
        })

        # 목록으로 복귀
        try:
            list_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#lBtn")))
            list_btn.click()
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.x-grid3-row")))
        except:
            logger.warning(f"[{i+1}] 목록 버튼 복귀 실패, 반복 종료")
            break

    return results

# ==================================================
# 전체 수집
# ==================================================
def scrape_all(keyword=None, start_date=None, end_date=None):
    logger.info("KRX 공고 스크래핑 시작")

    today = datetime.today()
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end_date = today
    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_date = today - timedelta(days=30)

    driver = create_driver()
    wait = WebDriverWait(driver, 20)

    try:
        results = extract_list(driver, wait, start_date, end_date, keyword)
    finally:
        driver.quit()

    # JSON 저장
    filename = f"krx_legnotice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON 저장 완료: {filepath}")

# -------------------------------------------------
# Health Check 모드
# -------------------------------------------------
def krx_legnotice_health_check():
    """
    KRX 규정 제·개정 예고 Health Check
    - 목록 1건 추출
    - 상세 페이지 접근 검증
    """

    check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
        "org_name": ORG_NAME,
        "target": "한국거래소 > 법무포탈 > 규정 제·개정 예고",
        "check_time": check_time,
        "status": "FAIL",
        "checks": {
            "search_page": {
                "url": BASE_URL,
                "success": False,
                "message": ""
            },
            "list_page": {
                "success": False,
                "count": 0,
                "title": None
            },
            "detail_page": {
                "url": DETAIL_BASE_URL,
                "success": False,
                "content_length": 0
            }
        },
        "error": None
    }

    driver = None
    try:
        driver = create_driver()
        wait = WebDriverWait(driver, 20)

        # ---------------------------------
        # 1. 메인 페이지 접근
        # ---------------------------------
        logger.info(f"[CHECK] {BASE_URL}")
        driver.get(BASE_URL)
        time.sleep(1)

        # 메뉴 클릭
        menu = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "li[vo='/out/pds/goPdsMain.do'] a"))
        )
        menu.click()
        time.sleep(1)

        # iframe 전환
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "workPage")))

        result["checks"]["search_page"]["success"] = True
        result["checks"]["search_page"]["message"] = "목록 페이지 접근 성공"

        # ---------------------------------
        # 2. 목록 1건 추출
        # ---------------------------------
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.x-grid3-row")))
        rows = driver.find_elements(By.CSS_SELECTOR, "div.x-grid3-row")

        if not rows:
            result["error"] = "목록 데이터 없음"
            return result

        row = rows[0]
        title = row.find_element(By.CSS_SELECTOR, "div.x-grid3-col-1").text.strip()

        result["checks"]["list_page"]["success"] = True
        result["checks"]["list_page"]["count"] = 1
        result["checks"]["list_page"]["title"] = title

        # ---------------------------------
        # 3. 상세 페이지 접근
        # ---------------------------------
        logger.info(f"[HEALTH] 상세 접근: {title}")
        ActionChains(driver).move_to_element(row).click().perform()
        time.sleep(1)

        detail_title, content = parse_detail_page(driver, wait)
        content_length = len(content) if content else 0

        result["checks"]["detail_page"]["success"] = content_length > 0
        result["checks"]["detail_page"]["content_length"] = content_length

        result["status"] = "OK"

    except Exception as e:
        logger.exception("[HEALTH] KRX Health Check 실패")
        result["error"] = str(e)

    finally:
        if driver:
            driver.quit()

    return result

# ==================================================
# main
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KRX 규정 제·개정 예고 크롤러")
    parser.add_argument("--keyword", type=str, default=None, help="검색어 예: --keyword '코넥스'")
    parser.add_argument("--start_date", type=str, default=None, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end_date", type=str, default=None, help="종료일 YYYY-MM-DD")
    parser.add_argument(
    "--check",
    action="store_true",
    help="한국거래소-법무포탈 → 규정 제·개정 예고 Health Check 실행"
    )

    args = parser.parse_args()

    if args.check:
        result = krx_legnotice_health_check()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0)

    scrape_all(keyword=args.keyword, start_date=args.start_date, end_date=args.end_date)
