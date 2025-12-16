"""
OCR 추출 모듈 (v3 - 하이브리드)
v1과 v2의 장점을 결합한 하이브리드 버전
- 표 형식: v2 방식 (고해상도 + 강한 전처리)
- 문단 형식: v1 방식 (적당한 해상도 + 최소 전처리)
"""
import os
import io
import sys
import platform
import re

# OCR 라이브러리 import
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    import numpy as np
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
    np = None
    IMAGE_OPS_AVAILABLE = False
    PYTESSERACT_AVAILABLE = False


class OCRExtractor:
    """하이브리드 OCR 추출 클래스"""
    
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
                print(f"  ✓ OCR 사용 준비 완료 (Tesseract 경로: {path})")
                return
        
        print("  ※ Tesseract 실행 파일을 찾을 수 없어 OCR을 사용할 수 없습니다.")
        self.ocr_available = False
    
    def _extract_v1_style(self, image, page_num):
        """
        v1 방식: 문단 형식에 적합
        - 300 DPI (이미 변환된 이미지 사용)
        - 최소 전처리
        - PSM 6, 4만 사용
        - 가장 긴 텍스트 선택
        """
        configs = [
            ('kor+eng', '--oem 3 --psm 6'),  # 단일 블록
            ('kor+eng', '--oem 3 --psm 4'),  # 단일 열
            ('kor', '--oem 3 --psm 6'),
            ('kor', '--oem 3 --psm 4')
        ]
        
        best_text = ''
        for lang, cfg in configs:
            try:
                candidate = pytesseract.image_to_string(image, lang=lang, config=cfg)
                if candidate and len(candidate) > len(best_text):
                    best_text = candidate
            except Exception:
                continue
        
        return best_text
    
    def _extract_v2_style(self, image, page_num):
        """
        v2 방식: 표 형식에 적합
        - 500 DPI (이미 변환된 이미지 사용)
        - 강한 전처리
        - 다양한 PSM 모드
        - 품질 점수 기반 선택
        """
        # 이미지 전처리 개선
        # 1. 선명도 향상
        image = image.filter(ImageFilter.SHARPEN)
        
        # 2. 대비 향상
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)
        
        # 3. 밝기 조정
        brightness_enhancer = ImageEnhance.Brightness(image)
        image = brightness_enhancer.enhance(1.1)
        
        # 4. 선명도 추가 향상
        sharpness_enhancer = ImageEnhance.Sharpness(image)
        image = sharpness_enhancer.enhance(1.3)
        
        configs = [
            ('kor+eng', '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789가-힣a-zA-Z.,()[]{}·ㆍ-| '),
            ('kor', '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789가-힣.,()[]{}·ㆍ-| '),
            ('kor+eng', '--oem 3 --psm 4'),
            ('kor', '--oem 3 --psm 4'),
            ('kor+eng', '--oem 3 --psm 11'),
            ('kor', '--oem 3 --psm 11'),
            ('kor+eng', '--oem 3 --psm 3'),
            ('kor', '--oem 3 --psm 3'),
        ]
        
        best_text = ''
        best_score = 0
        
        for lang, cfg in configs:
            try:
                candidate = pytesseract.image_to_string(image, lang=lang, config=cfg)
                if candidate:
                    korean_chars = sum(1 for c in candidate if '\uAC00' <= c <= '\uD7A3')
                    total_chars = len(candidate.replace(' ', '').replace('\n', ''))
                    korean_ratio = korean_chars / total_chars if total_chars > 0 else 0
                    score = len(candidate) + (korean_ratio * 1000)
                    
                    if score > best_score:
                        best_text = candidate
                        best_score = score
            except Exception:
                continue
        
        return best_text
    
    def _detect_table_structure(self, text):
        """
        텍스트에서 표 형식 감지
        
        Returns:
            bool: 표 형식일 가능성
        """
        if not text:
            return False
        
        lines = text.split('\n')
        
        # 먼저 문단 형식 패턴 확인 (우선순위 높음)
        # "4. 제재대상사실", "4. 조치대상사실" 등은 명확한 문단 형식
        for line in lines[:30]:
            stripped = line.strip()
            # 4번 항목 패턴 감지
            if re.search(r'4\s*[\.。]\s*(?:제\s*재\s*대\s*상\s*사\s*실|조\s*치\s*대\s*상\s*사\s*실|제\s*재\s*조\s*치\s*사\s*유|제\s*재\s*대\s*상)', stripped):
                return False  # 문단 형식으로 명확히 판단
        
        # 표 형식 감지 지표
        table_indicators = 0
        
        # 1. "제재대상 제재내용" 같은 헤더 패턴 (한 줄에 같이 있어야 함)
        for line in lines[:20]:  # 처음 20줄만 확인
            stripped = line.strip()
            # "제재대상"과 "제재내용"이 같은 줄에 있고, "제재대상사실"이 아닌 경우
            if '제재대상' in stripped and '제재내용' in stripped:
                # "제재대상사실"은 제외 (문단 형식)
                if '제재대상사실' not in stripped and '대상사실' not in stripped:
                    table_indicators += 4  # 가중치 높게
                    break
        
        # 2. 표 구조 패턴: 짧은 줄이 연속으로 나오되, 명확한 행 패턴
        short_lines = 0
        consecutive_short = 0
        max_consecutive = 0
        
        for line in lines[:50]:
            stripped = line.strip()
            if stripped and len(stripped) < 40:  # 짧은 줄
                short_lines += 1
                consecutive_short += 1
                max_consecutive = max(max_consecutive, consecutive_short)
            else:
                consecutive_short = 0
        
        # 연속된 짧은 줄이 5개 이상이면 표 형식 가능성 높음
        if max_consecutive >= 5:
            table_indicators += 3
        
        # 3. 명확한 표 구분자 패턴 (탭, 파이프 등)
        separator_lines = 0
        for line in lines[:30]:
            if '\t' in line:  # 탭은 표의 강한 신호
                separator_lines += 2
            elif '|' in line and line.count('|') >= 2:  # 파이프 2개 이상
                separator_lines += 1
        
        if separator_lines >= 2:
            table_indicators += 2
        
        # 4. 3번 항목 패턴 ("3. 제재조치내용" 다음에 표가 나오는 경우)
        found_section3 = False
        for i, line in enumerate(lines[:30]):
            stripped = line.strip()
            if re.search(r'3\s*[\.。]\s*(?:제\s*재\s*조\s*치\s*내\s*용|조\s*치\s*내\s*용)', stripped):
                found_section3 = True
                # 3번 항목 다음 10줄 이내에 표 헤더가 있는지 확인
                for j in range(i+1, min(i+11, len(lines))):
                    if '제재대상' in lines[j] and '제재내용' in lines[j]:
                        if '제재대상사실' not in lines[j]:
                            table_indicators += 3
                            break
                break
        
        # 더 엄격한 기준: 명확한 표만 감지
        return table_indicators >= 5
    
    def extract_text(self, file_path, mode='auto'):
        """
        하이브리드 OCR 추출
        
        Args:
            file_path: PDF 파일 경로
            mode: 'auto', 'v1', 'v2', 'hybrid'
                - 'auto': 페이지별로 자동 감지 (기본값)
                - 'v1': v1 방식만 사용
                - 'v2': v2 방식만 사용
                - 'hybrid': 두 방식 모두 시도 후 최선의 결과 선택
        
        Returns:
            추출된 텍스트 (실패 시 None)
        """
        if not self.ocr_available:
            return None
        
        try:
            print(f"  OCR 추출 시도 중 (모드: {mode})...")
            doc = fitz.open(str(file_path))
            texts = []
            
            print(f"  PDF 페이지 수: {len(doc)}")
            
            for page_num, page in enumerate(doc, 1):
                print(f"  페이지 {page_num}/{len(doc)} 처리 중...")
                
                # 두 가지 해상도로 이미지 생성
                # v1용: 300 DPI
                mat_v1 = fitz.Matrix(300 / 72, 300 / 72)
                pix_v1 = page.get_pixmap(matrix=mat_v1)
                img_data_v1 = pix_v1.tobytes("png")
                image_v1 = Image.open(io.BytesIO(img_data_v1)).convert('L')
                
                # v2용: 500 DPI
                mat_v2 = fitz.Matrix(500 / 72, 500 / 72)
                pix_v2 = page.get_pixmap(matrix=mat_v2)
                img_data_v2 = pix_v2.tobytes("png")
                image_v2 = Image.open(io.BytesIO(img_data_v2)).convert('L')
                
                result_text = None
                result_method = None
                
                if mode == 'v1':
                    # v1 방식만
                    result_text = self._extract_v1_style(image_v1, page_num)
                    result_method = 'v1'
                    
                elif mode == 'v2':
                    # v2 방식만
                    result_text = self._extract_v2_style(image_v2, page_num)
                    result_method = 'v2'
                    
                elif mode == 'hybrid':
                    # 두 방식 모두 시도
                    text_v1 = self._extract_v1_style(image_v1, page_num)
                    text_v2 = self._extract_v2_style(image_v2, page_num)
                    
                    # 결과 비교
                    if not text_v2:
                        result_text = text_v1
                        result_method = 'v1 (v2 실패)'
                    elif not text_v1:
                        result_text = text_v2
                        result_method = 'v2 (v1 실패)'
                    else:
                        # 표 형식 감지
                        is_table_v1 = self._detect_table_structure(text_v1)
                        is_table_v2 = self._detect_table_structure(text_v2)
                        
                        # 둘 다 표 형식이면 v2 선택, 둘 다 문단이면 v1 선택
                        if is_table_v2 and not is_table_v1:
                            result_text = text_v2
                            result_method = 'v2 (표 감지)'
                        elif is_table_v1 and not is_table_v2:
                            result_text = text_v1
                            result_method = 'v1 (문단 감지)'
                        else:
                            # 길이와 품질 비교
                            # v1이 훨씬 길면 v1 선택 (문단)
                            if len(text_v1) > len(text_v2) * 1.3:
                                result_text = text_v1
                                result_method = 'v1 (더 긴 텍스트)'
                            # v2가 표 형식이면 v2 선택
                            elif is_table_v2:
                                result_text = text_v2
                                result_method = 'v2 (표 형식)'
                            else:
                                # 기본적으로 v1 선택 (문단에 유리)
                                result_text = text_v1
                                result_method = 'v1 (기본)'
                
                else:  # mode == 'auto'
                    # 먼저 v1로 추출 (기본적으로 v1 사용)
                    text_v1 = self._extract_v1_style(image_v1, page_num)
                    
                    if text_v1:
                        # 4번 항목 패턴 확인 (명시적으로 문단 형식)
                        is_section4 = False
                        for line in text_v1.split('\n')[:30]:
                            if re.search(r'4\s*[\.。]\s*(?:제\s*재\s*대\s*상\s*사\s*실|조\s*치\s*대\s*상\s*사\s*실)', line):
                                is_section4 = True
                                break
                        
                        if is_section4:
                            # 4번 항목은 항상 v1 사용
                            result_text = text_v1
                            result_method = 'v1 (4번 항목 - 문단 형식)'
                        else:
                            # 표 형식 감지
                            is_table = self._detect_table_structure(text_v1)
                            
                            if is_table:
                                # 명확한 표 형식이면 v2도 시도
                                print(f"    표 형식 감지 → v2 방식도 시도")
                                text_v2 = self._extract_v2_style(image_v2, page_num)
                                
                                if text_v2:
                                    # v2 결과가 더 나은지 확인
                                    is_table_v2 = self._detect_table_structure(text_v2)
                                    # v2가 명확한 표이고 길이가 비슷하면 v2 선택
                                    if is_table_v2 and len(text_v2) >= len(text_v1) * 0.8:
                                        result_text = text_v2
                                        result_method = 'v2 (표 형식)'
                                    else:
                                        result_text = text_v1
                                        result_method = 'v1 (표 감지 후 v1 유지)'
                                else:
                                    result_text = text_v1
                                    result_method = 'v1 (v2 실패)'
                            else:
                                result_text = text_v1
                                result_method = 'v1 (문단 형식)'
                    else:
                        # v1 실패 시 v2 시도
                        result_text = self._extract_v2_style(image_v2, page_num)
                        result_method = 'v2 (v1 실패)'
                
                if result_text:
                    texts.append(result_text)
                    print(f"    → {len(result_text)}자 추출됨 ({result_method})")
                else:
                    print(f"    → 추출 실패")
            
            doc.close()
            
            full_text = '\n'.join(t.strip() for t in texts if t).strip()
            if full_text:
                print(f"  ✓ OCR로 {len(full_text)}자 추출 완료")
            return full_text if full_text else None
            
        except Exception as e:
            print(f"  ✗ OCR 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def is_available(self):
        """OCR 사용 가능 여부 반환"""
        return self.ocr_available
