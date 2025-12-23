import os
import sys
import json
import time

# ==================================================
# 🔑 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from common.common_logger import get_logger

# ==================================================
# 로거
# ==================================================
logger = get_logger("fss_legnotice_selenium")

# ==================================================
# Selenium
# ==================================================
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from common.constants import URLStatus, LegalDocProvided
ORG_NAME = LegalDocProvided.FSS

# ==================================================
# URL / 설정
# ==================================================
LIST_URL = "https://www.fss.or.kr/fss/job/lrgRegItnPrvntc/list.do?menuNo=200489"

WAIT_TIMEOUT = 12
HEADLESS = True

OUTPUT_BASE_DIR = os.path.join(CURRENT_DIR, "output")
OUTPUT_JSON_DIR = os.path.join(OUTPUT_BASE_DIR, "json")
os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)

JSON_OUTPUT = os.path.join(OUTPUT_JSON_DIR, "fss_legnotice_results.json")

# ==================================================
# Chrome Driver
# ==================================================
def create_driver():
    options = Options()

    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--log-level=3")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

# ==================================================
# 상세 페이지 본문 추출 (FULL TEXT ONLY)
# ==================================================
def parse_detail_full(driver):
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    try:
        box = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.box"))
        )
        return box.text.strip()

    except TimeoutException:
        logger.warning("상세 본문 로딩 실패")
        return ""

# ==================================================
# 전체 실행
# ==================================================
def scrape_all():
    logger.info("FSS 규정 개정예고 (Selenium) 스크래핑 시작")

    driver = create_driver()
    wait = WebDriverWait(driver, WAIT_TIMEOUT)

    driver.get(LIST_URL)

    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))
    except TimeoutException:
        logger.error("목록 로딩 실패")
        driver.quit()
        return

    results = []

    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    total = len(rows)
    logger.info(f"총 {total}건 발견")

    for idx in range(total):
        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        row = rows[idx]

        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) < 3:
            continue

        title = cols[1].text.strip()
        date = cols[2].text.strip()

        link_el = cols[1].find_element(By.TAG_NAME, "a")

        logger.info(f"[{idx+1}/{total}] {title}")

        driver.execute_script("arguments[0].click();", link_el)
        time.sleep(1)

        detail_url = driver.current_url
        detail_full = parse_detail_full(driver)

        results.append({
            "org_name": ORG_NAME,
            "title": title,
            "date": date,
            "content": detail_full,
            "detail_url": detail_url
        })

        # 목록 복귀 (URL 재접근)
        driver.get(LIST_URL)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr")))

    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON 저장 완료: {JSON_OUTPUT}")
    driver.quit()

# ==================================================
# main
# ==================================================
if __name__ == "__main__":
    scrape_all()
