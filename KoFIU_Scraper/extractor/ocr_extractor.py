import os
from typing import Optional

import pytesseract
from pdf2image import convert_from_path

from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType


class OCRExtractor:
    """
    OCR 전용 Extractor
    - PDF → Image → OCR
    - 텍스트 추출 여부만 책임
    """

    DEFAULT_DPI = 300
    DEFAULT_LANG = "kor+eng"

    @classmethod
    def extract_text(
        cls,
        pdf_path: str,
        dpi: int = DEFAULT_DPI,
        lang: str = DEFAULT_LANG,
        max_pages: Optional[int] = None,
    ) -> str:
        """
        PDF 파일 OCR 수행

        :param pdf_path: PDF 파일 경로
        :param dpi: 변환 DPI
        :param lang: OCR 언어
        :param max_pages: OCR 수행 최대 페이지 수 (Health Check용 제한)
        :return: OCR 추출 텍스트
        """

        if not os.path.exists(pdf_path):
            raise HealthCheckError(
                HealthErrorType.OCR_FAIL,
                "PDF 파일이 존재하지 않음",
                pdf_path,
            )

        try:
            images = convert_from_path(
                pdf_path,
                dpi=dpi,
                first_page=1,
                last_page=max_pages,
            )
        except Exception as e:
            raise HealthCheckError(
                HealthErrorType.OCR_FAIL,
                "PDF → 이미지 변환 실패",
                str(e),
            )

        if not images:
            raise HealthCheckError(
                HealthErrorType.OCR_FAIL,
                "이미지 변환 결과 없음",
                pdf_path,
            )

        texts = []

        for idx, img in enumerate(images, start=1):
            try:
                text = pytesseract.image_to_string(img, lang=lang)
                if text:
                    texts.append(text.strip())
            except Exception as e:
                raise HealthCheckError(
                    HealthErrorType.OCR_FAIL,
                    f"OCR 처리 실패 (page={idx})",
                    str(e),
                )

        merged_text = "\n".join(texts).strip()

        if not merged_text:
            raise HealthCheckError(
                HealthErrorType.OCR_FAIL,
                "OCR 결과 텍스트 없음",
                pdf_path,
            )

        return merged_text
