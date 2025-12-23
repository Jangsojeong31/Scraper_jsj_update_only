# krx_legnotice_scraper.py
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

# ==================================================
# main
# ==================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KRX 규정 제·개정 예고 크롤러")
    parser.add_argument("--keyword", type=str, default=None, help="검색어 예: --keyword '코넥스'")
    parser.add_argument("--start_date", type=str, default=None, help="시작일 YYYY-MM-DD")
    parser.add_argument("--end_date", type=str, default=None, help="종료일 YYYY-MM-DD")
    args = parser.parse_args()

    scrape_all(keyword=args.keyword, start_date=args.start_date, end_date=args.end_date)
