# kfb_legnotice_selenium_paging.py
import os
import sys
import json
import time
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException

# ==================================================
# 프로젝트 루트 등록
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920x1080")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

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
# CLI 실행
# ==================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=str)
    parser.add_argument("--end-date", type=str)
    args = parser.parse_args()
    scrape_all(start_date=args.start_date, end_date=args.end_date)
