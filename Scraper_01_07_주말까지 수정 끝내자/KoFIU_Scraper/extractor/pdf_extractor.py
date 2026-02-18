import os
from typing import Optional

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from common.health_exception import HealthCheckError
from common.health_error_type import HealthErrorType


class PDFExtractor:
    """
    PDF 텍스트 추출 전용 Extractor
    - pdfplumber 기반
    - OCR 판단 전 1차 텍스트 추출
    """

    MIN_TEXT_LENGTH = 50  # Health Check 기준 최소 본문 길이

    @classmethod
    def extract_text(
        cls,
        pdf_path: str,
        max_pages: Optional[int] = None,
    ) -> str:
        """
        PDF 텍스트 추출

        :param pdf_path: PDF 파일 경로
        :param max_pages: 최대 처리 페이지 수 (Health Check용)
        :return: 추출된 텍스트
        """

        if not os.path.exists(pdf_path):
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY,
                "PDF 파일이 존재하지 않음",
                pdf_path,
            )

        texts = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                if not pdf.pages:
                    raise HealthCheckError(
                        HealthErrorType.CONTENT_EMPTY,
                        "PDF 페이지 없음",
                        pdf_path,
                    )

                pages = (
                    pdf.pages[:max_pages]
                    if max_pages
                    else pdf.pages
                )

                for idx, page in enumerate(pages, start=1):
                    try:
                        text = page.extract_text()
                        if text:
                            texts.append(text.strip())
                    except Exception as e:
                        raise HealthCheckError(
                            HealthErrorType.PARSE_ERROR,
                            f"PDF 페이지 파싱 실패 (page={idx})",
                            str(e),
                        )

        except PdfminerException as e:
            # HTML, 잘못된 응답, 다운로드 실패 PDF 등
            raise HealthCheckError(
                HealthErrorType.PARSE_ERROR,
                "PDF 파싱 실패 (PDF 구조 오류)",
                str(e),
            )

        except Exception as e:
            raise HealthCheckError(
                HealthErrorType.UNEXPECTED_ERROR,
                "PDF 처리 중 알 수 없는 오류",
                str(e),
            )

        merged_text = "\n".join(texts).strip()

        # 텍스트 거의 없는 경우 → OCR 대상
        if len(merged_text) < cls.MIN_TEXT_LENGTH:
            raise HealthCheckError(
                HealthErrorType.CONTENT_EMPTY,
                "PDF 텍스트 추출 실패 (OCR 필요)",
                pdf_path,
            )

        return merged_text
