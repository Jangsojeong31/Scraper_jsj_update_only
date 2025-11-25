import os
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import sys

# 현재 파일 기준으로 ../common 경로 추가
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(BASE_DIR)

# FileExtractor 불러오기 (프로젝트 구조 기준)
from common.file_extractor import FileExtractor

# ------------------------------
# 1. 기본 설정
# ------------------------------

URL = "https://www.crefia.or.kr/portal/infocenter/regulation/selfRegulation.xx"
download_dir = os.path.join(os.getcwd(), "downloads")
os.makedirs(download_dir, exist_ok=True)

chrome_options = Options()
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})

driver = webdriver.Chrome(options=chrome_options)
driver.get(URL)
time.sleep(2)


# ------------------------------
# 2. "선불카드 표준약관" 항목 클릭
# ------------------------------

target_title = "선불카드 표준약관"

elements = driver.find_elements(By.CSS_SELECTOR, "div.list_box ul li a")

target_elem = None
for el in elements:
    title_tag = el.find_element(By.TAG_NAME, "p")
    if title_tag.text.strip() == target_title:
        target_elem = el
        break

if target_elem is None:
    driver.quit()
    raise Exception("❌ '선불카드 표준약관' 항목을 찾지 못했습니다.")


# ------------------------------
# 3. 다운로드 감지 로직
# ------------------------------

before = set(os.listdir(download_dir))
print("📥 다운로드 시작...")

target_elem.click()

downloaded_file = None
timeout = 40
start_time = time.time()

while time.time() - start_time < timeout:
    after = set(os.listdir(download_dir))
    new_files = after - before

    if new_files:
        downloaded_file = list(new_files)[0]

        # .crdownload → 다운로드 중
        if not downloaded_file.endswith(".crdownload"):
            break

    time.sleep(1)

driver.quit()

if downloaded_file is None:
    raise Exception("❌ 다운로드 실패 또는 시간 초과!")

filepath = os.path.join(download_dir, downloaded_file)
print(f"✅ 다운로드 완료: {filepath}")


# ------------------------------
# 4. FileExtractor로 파일 내용 읽기
# ------------------------------

file_extractor = FileExtractor()

try:
    content = file_extractor.extract_hwp_content(filepath)
    content = content[:1000]  # 1000자 제한
except Exception as e:
    content = f"파일 읽기 실패: {str(e)}"

print("\n📄 파일 내용 일부:")
print(content)


# ------------------------------
# 5. JSON 저장
# ------------------------------

output = {
    "title": target_title,
    "file_name": downloaded_file,
    "content_1000": content
}

json_path = os.path.join(download_dir, "result.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n📌 JSON 저장 완료: {json_path}")
