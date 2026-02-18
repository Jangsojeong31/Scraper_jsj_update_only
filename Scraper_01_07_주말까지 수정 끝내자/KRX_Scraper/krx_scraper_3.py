from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import csv
import os

class KrxPageCrawler:
    BASE_URL = "https://rule.krx.co.kr/out/index.do"

    def __init__(self, delay=1.0):
        self.delay = delay
        self.driver = self._init_driver()

        # 프로젝트 기준 경로 자동 탐지
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        CSV_PATH = os.path.join(BASE_DIR, "input", "list.csv")

        self.filter_list = self._load_csv(CSV_PATH)

        self.OUTPUT_FILE = "filtered_data.csv"
        self.csv_file = open(self.OUTPUT_FILE, "w", encoding="utf-8", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(["번호", "규정번호", "규정명", "제·개정", "제·개정일", "시행일", "상세내용"])

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--lang=ko-KR")
        service = Service()
        return webdriver.Chrome(service=service, options=chrome_options)

    def _load_csv(self, file_path):
        filter_items = set()
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                filter_items.add(row[-1])
        print(f"CSV에서 {len(filter_items)}개의 필터 키워드 로드 완료")
        return filter_items

    def crawl(self):
        driver = self.driver
        wait = WebDriverWait(driver, 10)

        driver.get(self.BASE_URL)

        # 최근개정 규정 버튼 클릭
        wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "moreBtn"))).click()
        time.sleep(1)

        # iframe 진입
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe")))

        print("iframe 내부 진입")

        for keyword in self.filter_list:
            print(f"\n▶ 검색어: {keyword}")

            # 검색어 입력
            search_input = wait.until(EC.presence_of_element_located((By.ID, "Schtxt")))
            search_input.clear()
            search_input.send_keys(keyword)

            driver.find_element(By.ID, "searchBtn").click()
            time.sleep(1.5)

            # 검색 결과 row 로딩 대기
            rows = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".x-grid3-row"))
            )

            for idx, row_el in enumerate(rows):
                # row 텍스트 추출
                cells = row_el.find_elements(By.CSS_SELECTOR, ".x-grid3-cell-inner")
                texts = [c.text.strip() for c in cells]

                print(f" - [{idx}] {texts}")

                # row 클릭
                driver.execute_script("arguments[0].scrollIntoView(true);", row_el)
                row_el.click()
                time.sleep(0.5)

                # 팝업 기다리고 텍스트 수집
                try:
                    popup = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#jo"))
                    )
                    content = popup.text.strip()[:200]  # 너무 길면 200자만
                except:
                    content = "상세 내용 없음"

                # CSV 저장
                self.csv_writer.writerow(texts + [content])

        # 종료
        self.csv_file.close()
        driver.quit()
        print("\n🔥 크롤링 완료 →", os.path.abspath(self.OUTPUT_FILE))


if __name__ == "__main__":
    crawler = KrxPageCrawler(delay=1.0)
    crawler.crawl()
