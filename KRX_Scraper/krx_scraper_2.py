from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import csv
import os

class KrxPageCrawler:
    """
    KRX 규정 페이지 크롤러
    - '최근개정 규정' 목록에서 필터 CSV와 일치하는 규정만 추출
    - 상세 내용은 동적 div 팝업(Mjo)에서 가져옴
    - 결과를 CSV로 저장
    - 페이지 순회하며 규정 찾기
    """

    BASE_URL = "https://rule.krx.co.kr/out/index.do"

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.driver = self._init_driver()
        self.filter_list = self._load_csv("./input/list.csv")

        self.OUTPUT_FILE = "filtered_data.csv"
        self.csv_file = open(self.OUTPUT_FILE, "w", encoding="utf-8", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(["번호", "규정번호", "규정명", "제.개정", "제.개정일", "시행일", "상세내용"])

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--lang=ko-KR")
        service = Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver

    def _load_csv(self, file_path):
        filter_items = set()
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                filter_items.add(row[-1])
        print(f"CSV에서 {len(filter_items)}개의 필터 항목 로드 완료")
        return filter_items

    def crawl(self):
        self.driver.get(self.BASE_URL)
        wait = WebDriverWait(self.driver, 10)

        # "최근개정 규정" 페이지 진입
        more_btn = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "moreBtn")))
        more_btn.click()
        time.sleep(1)

        # iframe 진입
        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        self.driver.switch_to.frame(iframes[0])
        print("iframe 내부로 전환 완료")

        while True:
            # 페이지 소스 가져오기
            html = self.driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select(".x-grid3-row")

            for i, row in enumerate(rows):
                cells = row.select(".x-grid3-cell-inner")
                texts = [cell.get_text(strip=True) for cell in cells]
                target_value = texts[2]

                if target_value not in self.filter_list:
                    continue

                print(f"일치 항목: {texts}")
                rule_no = texts[1]

                # row 클릭할 때마다 새로 찾기
                row_element = self.driver.find_elements(By.CSS_SELECTOR, ".x-grid3-cell-inner")[i]
                row_element.click()
                time.sleep(0.5)

                # 상세 팝업 가져오기
                try:
                    popup_div = self.driver.find_element(By.CSS_SELECTOR, "div.Mjo#jo")
                    content = popup_div.text.strip()[:100]
                except Exception:
                    content = "상세 내용 없음"

                # iframe 재선택
                self.driver.switch_to.default_content()
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                self.driver.switch_to.frame(iframes[0])

                # CSV 저장
                self.csv_writer.writerow(texts + [content])
                print(f"상세 내용 추출 완료: {content}")

            # 다음 페이지 버튼
            page_buttons = self.driver.find_elements(By.CSS_SELECTOR, "ul.list_navi li")
            next_btn = None
            found_active = False
            for btn in page_buttons:
                cls = btn.get_attribute("class") or ""
                if "active" in cls:
                    found_active = True
                    continue
                if found_active:
                    next_btn = btn
                    break

            if not next_btn:
                print("다음 페이지 없음. 크롤링 종료")
                break

            print(f"다음 페이지 이동: {next_btn.text}")
            self.driver.execute_script("arguments[0].click();", next_btn)
            wait.until(EC.staleness_of(next_btn))
            time.sleep(0.5)

        self.csv_file.close()
        self.driver.quit()
        print(f"CSV 저장 완료: {os.path.abspath(self.OUTPUT_FILE)}")


if __name__ == "__main__":
    crawler = KrxPageCrawler(delay=1.0)
    crawler.crawl()
