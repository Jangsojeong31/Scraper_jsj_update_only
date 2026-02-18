# pdf_text_extractor.py
# PDF 텍스트 + OCR 통합 Extractor
# OCR 과다 실행 방지 (페이지 제한 유지)
# OCR 성공/시도 페이지 분리 집계
# PARTIAL_OCR_FAIL, OCR_SKIPPED_LIMIT, OCR_NOT_REQUIRED HealthErrorType 연동
# OCR 일부 실패는 예외 미발생 (WARN 처리용)
# OCR 전체 실패만 HealthCheckError 발생

import os
from typing import Optional, Tuple

# ======================================================
# PDF Text Extract
# ======================================================
import pdfplumber
from PyPDF2 import PdfReader

# ======================================================
# OCR 라이브러리 import
# ======================================================
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    try:
        from PIL import ImageOps
        IMAGE_OPS_AVAILABLE = True
    except ImportError:
        IMAGE_OPS_AVAILABLE = False
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None
    IMAGE_OPS_AVAILABLE = False
    PYTESSERACT_AVAILABLE = False


from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType


class PDFTextExtractor:
    """
    PDF 텍스트 추출 + OCR 통합 Extractor
    - OCR 과다 실행 방지
    - PARTIAL_OCR_FAIL / OCR_SKIPPED_LIMIT 표준 반영
    """

    DEFAULT_DPI = 300
    DEFAULT_LANG = "kor+eng"
    MIN_TEXT_LENGTH = 50

    @classmethod
    def extract_text(
        cls,
        pdf_path: str,
        ocr_lang: str = DEFAULT_LANG,
        ocr_dpi: int = DEFAULT_DPI,
        max_ocr_pages: int = 5,
    ) -> dict:

        if not os.path.exists(pdf_path):
            raise HealthCheckError(
                HealthErrorType.PDF_PARSE_FAIL,
                "PDF 파일이 존재하지 않음",
                pdf_path,
            )

        # ==================================================
        # 1️⃣ PDF 내장 텍스트 추출
        # ==================================================
        pdf_text = cls._extract_text_pdf(pdf_path)
        pdf_len = len(pdf_text.strip())

        if pdf_len >= cls.MIN_TEXT_LENGTH:
            return {
                "text": pdf_text.strip(),
                "source": "pdf",
                "pdf_text_length": pdf_len,
                "ocr_used": False,
                "ocr_pages": 0,
                "ocr_success_pages": 0,
                "ocr_error_type": HealthErrorType.OCR_NOT_REQUIRED.value,
            }

        # ==================================================
        # 2️⃣ OCR Fallback (LIMITED)
        # ==================================================
        ocr_text, attempted_pages, success_pages = cls._extract_text_ocr(
            pdf_path,
            dpi=ocr_dpi,
            lang=ocr_lang,
            max_pages=max_ocr_pages,
        )

        # ❌ OCR 전체 실패 → 치명
        if success_pages == 0:
            raise HealthCheckError(
                HealthErrorType.OCR_FAIL,
                "OCR 결과 없음",
                pdf_path,
            )

        # ==================================================
        # 3️⃣ OCR 상태 판정
        # ==================================================
        ocr_error_type: Optional[str] = None

        if success_pages < attempted_pages:
            ocr_error_type = HealthErrorType.PARTIAL_OCR_FAIL.value
        elif attempted_pages >= max_ocr_pages:
            ocr_error_type = HealthErrorType.OCR_SKIPPED_LIMIT.value

        return {
            "text": ocr_text.strip(),
            "source": "ocr",
            "pdf_text_length": pdf_len,
            "ocr_used": True,
            "ocr_pages": attempted_pages,
            "ocr_success_pages": success_pages,
            "ocr_error_type": ocr_error_type,
        }

    # ==================================================
    # PDF Text Extract
    # ==================================================
    @staticmethod
    def _extract_text_pdf(pdf_path: str) -> str:
        texts = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        texts.append(t)
        except Exception:
            pass

        if texts:
            return "\n".join(texts)

        try:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
        except Exception:
            pass

        return "\n".join(texts)

    # ==================================================
    # OCR Extract (LIMITED + PARTIAL FAIL SAFE)
    # ==================================================
    @staticmethod
    def _extract_text_ocr(
        pdf_path: str,
        dpi: int,
        lang: str,
        max_pages: int,
    ) -> Tuple[str, int, int]:
        """
        return:
            text,
            attempted_pages,
            success_pages
        """

        if not PYMUPDF_AVAILABLE or not PYTESSERACT_AVAILABLE:
            return "", 0, 0

        doc = fitz.open(pdf_path)
        texts = []
        success_pages = 0

        try:
            total_pages = doc.page_count
            limit = min(total_pages, max_pages)

            scale = dpi / 72
            matrix = fitz.Matrix(scale, scale)

            for page_index in range(limit):
                try:
                    page = doc.load_page(page_index)
                    pix = page.get_pixmap(matrix=matrix)

                    img = Image.frombytes(
                        "RGB",
                        (pix.width, pix.height),
                        pix.samples,
                    )

                    img = img.convert("L")
                    img = ImageEnhance.Contrast(img).enhance(1.5)
                    img = img.filter(ImageFilter.SHARPEN)

                    if IMAGE_OPS_AVAILABLE:
                        img = ImageOps.autocontrast(img)

                    t = pytesseract.image_to_string(img, lang=lang)
                    if t and t.strip():
                        texts.append(t.strip())
                        success_pages += 1

                except Exception:
                    # 페이지 단위 실패는 허용 (PARTIAL)
                    continue

        finally:
            doc.close()

        return "\n".join(texts), limit, success_pages
