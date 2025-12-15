"""
OCR 추출 모듈
PDF 파일에서 OCR을 사용하여 텍스트 추출
"""
import os
import io
import sys
import platform

# OCR 라이브러리 import
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image, ImageEnhance
    PYTESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    ImageEnhance = None
    PYTESSERACT_AVAILABLE = False


class OCRExtractor:
    """OCR을 사용하여 PDF에서 텍스트 추출하는 클래스"""
    
    def __init__(self):
        self.ocr_initialized = False
        self.ocr_available = False
        self._initialize_ocr()
    
    def _initialize_ocr(self):
        """OCR 초기화 (Tesseract 경로 설정)"""
        if self.ocr_initialized:
            return
        self.ocr_initialized = True
        
        if not PYMUPDF_AVAILABLE or not PYTESSERACT_AVAILABLE:
            print("  ※ OCR 모듈(PyMuPDF, pytesseract, Pillow) 중 일부가 설치되어 있지 않아 OCR을 사용할 수 없습니다.")
            self.ocr_available = False
            return
        
        # Windows에서 Tesseract 경로 찾기
        tesseract_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Users\USER\AppData\Local\Tesseract-OCR\tesseract.exe',
            r'C:\Users\USER\AppData\Local\Programs\Tesseract-OCR\tesseract.exe',
        ]
        
        # 환경 변수에서 사용자 이름 가져오기
        username = os.environ.get('USERNAME', 'USER')
        if username != 'USER':
            tesseract_paths.insert(0, rf'C:\Users\{username}\AppData\Local\Tesseract-OCR\tesseract.exe')
            tesseract_paths.insert(1, rf'C:\Users\{username}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe')
        
        for path in tesseract_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                self.ocr_available = True
                print(f"  OCR 사용 준비 완료 (Tesseract 경로: {path})")
                return
        
        print("  ※ Tesseract 실행 파일을 찾을 수 없어 OCR을 사용할 수 없습니다.")
        self.ocr_available = False
    
    def extract_text(self, file_path, min_text_length=200):
        """
        OCR을 사용하여 PDF에서 텍스트 추출 (이미지 기반 PDF용)
        
        Args:
            file_path: PDF 파일 경로
            min_text_length: 최소 텍스트 길이 (이 값보다 짧으면 OCR 시도)
            
        Returns:
            추출된 텍스트 (실패 시 None)
        """
        if not self.ocr_available:
            return None
        
        try:
            print(f"  OCR 추출 시도 중...")
            doc = fitz.open(str(file_path))
            texts = []
            
            for page_num, page in enumerate(doc):
                # 페이지를 이미지로 변환 (400 DPI - 해상도 증가로 정확도 향상)
                mat = fitz.Matrix(400 / 72, 400 / 72)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert('L')
                
                # 이미지 전처리: 대비 향상 (보수적 접근)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.2)  # 대비 20% 증가
                
                # 여러 OCR 설정 시도 (더 다양한 PSM 모드 추가)
                configs = [
                    ('kor+eng', '--oem 3 --psm 6'),   # 단일 블록
                    ('kor+eng', '--oem 3 --psm 4'),   # 단일 컬럼
                    ('kor+eng', '--oem 3 --psm 11'),  # 희미한 텍스트
                    ('kor', '--oem 3 --psm 6'),
                    ('kor', '--oem 3 --psm 4'),
                    ('kor', '--oem 3 --psm 11'),
                ]
                
                best_text = ''
                best_score = 0
                
                for lang, cfg in configs:
                    try:
                        candidate = pytesseract.image_to_string(image, lang=lang, config=cfg)
                        if candidate:
                            # 결과 품질 평가: 한글 문자 비율과 길이를 고려
                            korean_chars = sum(1 for c in candidate if '\uAC00' <= c <= '\uD7A3')
                            total_chars = len(candidate.replace(' ', '').replace('\n', ''))
                            korean_ratio = korean_chars / total_chars if total_chars > 0 else 0
                            
                            # 점수: 길이 + 한글 비율 가중치
                            score = len(candidate) + (korean_ratio * 1000)
                            
                            if score > best_score:
                                best_text = candidate
                                best_score = score
                    except Exception:
                        continue
                
                if best_text:
                    texts.append(best_text)
                    print(f"    페이지 {page_num + 1}: {len(best_text)}자 추출")
            
            doc.close()
            
            full_text = '\n'.join(t.strip() for t in texts if t).strip()
            if full_text:
                print(f"  ✓ OCR로 {len(full_text)}자 추출 완료")
            return full_text if full_text else None
            
        except Exception as e:
            print(f"  ✗ OCR 처리 중 오류: {e}")
            return None
    
    def is_available(self):
        """OCR 사용 가능 여부 반환"""
        return self.ocr_available

