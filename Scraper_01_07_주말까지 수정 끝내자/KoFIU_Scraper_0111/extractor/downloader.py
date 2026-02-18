import os
import time
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException

from extractor.pdf_extractor import PDFExtractor
from extractor.ocr_extractor import OCRExtractor

class FileDownloader:

    @staticmethod
    def download(url: str, output_dir: str, parse_pdf: bool = True, parse_ocr: bool = True) -> dict:
        """
        파일 다운로드 + PDF/OCR 처리 통합
        - requests 먼저 시도, 실패 시 Selenium fallback
        - PDFExtractor -> OCRExtractor 순서로 본문 추출

        Args:
            url: PDF 파일 URL
            output_dir: 저장 폴더
            parse_pdf: PDF 텍스트 추출 여부
            parse_ocr: OCR fallback 수행 여부

        Returns:
            dict: {
                "download_ok": bool,
                "path": str | None,
                "text_extract_ok": bool,
                "ocr_available": bool,
                "reason": str | None,
                "message": str | None
            }
        """
        os.makedirs(output_dir, exist_ok=True)
        file_info = {
            "download_ok": False,
            "path": None,
            "text_extract_ok": False,
            "ocr_available": False,
            "reason": None,
            "message": None
        }

        filename = f"{int(time.time() * 1000)}.pdf"
        save_path = os.path.join(output_dir, filename)

        # 1. requests 시도
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").lower()
            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                file_info["download_ok"] = True
                file_info["path"] = save_path
            else:
                file_info["reason"] = "CONTENT_NOT_PDF"
                file_info["message"] = "PDF 파일이 아님, Selenium fallback 필요"
        except Exception as e:
            file_info["reason"] = "REQUEST_FAIL"
            file_info["message"] = str(e)

        # 2. Selenium fallback
        if not file_info["download_ok"]:
            try:
                options = Options()
                options.add_argument("--headless")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-dev-shm-usage")
                driver = webdriver.Chrome(options=options)
                driver.get(url)
                time.sleep(2)

                # <a> 링크 직접 다운로드
                link_elem = driver.find_element(By.TAG_NAME, "a")
                href = link_elem.get_attribute("href")
                if href:
                    resp = requests.get(href, timeout=20)
                    resp.raise_for_status()
                    with open(save_path, "wb") as f:
                        f.write(resp.content)
                    file_info["download_ok"] = True
                    file_info["path"] = save_path
                driver.quit()
            except Exception as e:
                file_info["reason"] = "SELENIUM_FAIL"
                file_info["message"] = str(e)

        # 3. PDFExtractor
        if file_info["download_ok"] and parse_pdf:
            try:
                text = PDFExtractor.extract_text(file_info["path"])
                if text.strip():
                    file_info["text_extract_ok"] = True
                else:
                    file_info["text_extract_ok"] = False
            except Exception as e:
                file_info["text_extract_ok"] = False

        # 4. OCR fallback
        if file_info["download_ok"] and parse_ocr and not file_info["text_extract_ok"]:
            try:
                ocr_text = OCRExtractor().extract_text(file_info["path"])
                if ocr_text.strip():
                    file_info["ocr_available"] = True
            except Exception as e:
                file_info["ocr_available"] = False

        return file_info
