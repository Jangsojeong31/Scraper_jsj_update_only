"""
OCR 후처리 모듈
- OCR 추출된 텍스트의 후처리 함수들
"""
import re


def collapse_split_syllables(text: str) -> str:
    """
    OCR 오류로 인한 한글 음절 사이의 공백만 제거 (정상 띄어쓰기는 보존)
    
    예: "기 관 과 태 료" -> "기관과태료" (OCR 오류)
    예: "기관 과 태료" -> "기관 과 태료" (정상 띄어쓰기 보존)
    """
    if not text:
        return text
    
    split_syllable_pattern = re.compile(r'((?:[가-힣]\s){2,}[가-힣])')
    result = split_syllable_pattern.sub(lambda m: m.group(0).replace(' ', ''), text)
    return result


def clean_ocr_artifacts(text):
    """OCR 인공물 제거"""
    if not text:
        return text
    
    # 1. 특수문자 정규화
    text = text.replace('ㆍ', '·')
    text = text.replace('，', ',')
    text = text.replace('。', '.')
    text = text.replace('、', ',')
    
    # 2. "_ ｜ -" 패턴 제거
    text = re.sub(r'_\s*[｜\|ㅣ]\s*-\s*', '', text)
    text = re.sub(r'_\s*[｜\|ㅣ]\s*', '', text)
    text = re.sub(r'_\s*[，,]\s*', '', text)
    
    # 3. 한글 오인식 보정
    ocr_corrections = {
        '되직자': '퇴직자',
        '줌법': '준법',
        '되직': '퇴직',
        '줌법감시': '준법감시',
        '줌법감시인': '준법감시인',
        '과리료': '과태료',
        '제제내용': '제재내용',
        '오혐설계사': '보험설계사',
        '로혐설계사': '보험설계사',
        '견무정지': '업무정지',
    }
    for wrong, correct in ocr_corrections.items():
        text = text.replace(wrong, correct)
    
    # 4. 숫자-한글 사이 공백 제거
    text = re.sub(r'(?<=\d)\s+(?=[가-힣])', '', text)
    
    # 5. 한글 글자 사이 공백 제거
    text = re.sub(r'등\s+록\s+취\s+소', '등록취소', text)
    text = re.sub(r'업\s+무\s+정\s+지', '업무정지', text)
    text = re.sub(r'과\s+태\s+료', '과태료', text)
    text = re.sub(r'견\s+책', '견책', text)
    text = re.sub(r'감\s+봉', '감봉', text)
    text = re.sub(r'기\s+관', '기관', text)
    text = re.sub(r'임\s+원', '임원', text)
    text = re.sub(r'직\s+원', '직원', text)
    text = re.sub(r'임\s+직\s+원', '임직원', text)
    text = re.sub(r'퇴\s+직\s+자', '퇴직자', text)
    text = re.sub(r'준\s+법', '준법', text)
    text = re.sub(r'백\s+만\s+원', '백만원', text)
    text = re.sub(r'만\s+원', '만원', text)
    text = re.sub(r'부\s+과', '부과', text)
    text = re.sub(r'주\s+의', '주의', text)
    text = re.sub(r'경\s+고', '경고', text)
    text = re.sub(r'상\s+당', '상당', text)
    text = re.sub(r'위\s+법', '위법', text)
    text = re.sub(r'부\s+당', '부당', text)
    text = re.sub(r'사\s+항', '사항', text)
    text = re.sub(r'보\s+험\s+설\s+계\s+사', '보험설계사', text)
    # 추가 패턴: "제 조의", "가 " 등
    text = re.sub(r'제\s+조\s*의', '제조의', text)
    text = re.sub(r'([가-힣])\s+$', r'\1', text)  # 한글 뒤 공백 제거 (줄 끝)
    text = re.sub(r'^([가-힣])\s+', r'\1', text, flags=re.MULTILINE)  # 한글 앞 공백 제거 (줄 시작)
    
    # 6. 고립된 문자 제거
    text = re.sub(r'\bㅣ\b', '', text)
    text = re.sub(r'\b\|\b(?![가-힣])', '', text)
    text = text.replace('`', '')
    
    # 7. 숫자 오인식 보정
    text = re.sub(r'\b0{3,}\b', '', text)
    
    # 8. 과도한 공백 정리
    text = re.sub(r' {3,}', ' ', text)
    
    # 9. 앞쪽 불필요한 하이픈/점 제거
    text = text.lstrip('- ').lstrip('·').lstrip('- ')
    text = text.lstrip('. ')
    
    # 10. "ㅇ" 단독 문자 제거
    text = re.sub(r'\bㅇ\b(?=\s)', '', text)
    text = re.sub(r'(?<=\s)\bㅇ\b', '', text)

    return text.strip()


def remove_all_whitespace(text: str) -> str:
    """문자열의 모든 공백 문자 제거"""
    if text is None:
        return text
    return re.sub(r'\s+', '', text)


def add_particle_spacing(text: str) -> str:
    """지정된 조사/어미 뒤에 공백을 강제 추가하여 가독성 확보"""
    if text is None:
        return text
    
    # 뒤에만 공백 추가하는 조사/어미
    particles_suffix = [
        '하여', '록', '면', '다', '터', '의', '음', '는', '은', '를', '을', '에',
        '경우', '따라', '관한', '하며', '한후', '통해', '하였으나', '하였고', 
        '위한', '향후', '대한', '적인', '하고', '그러나', '하거나', '으며', '앞으로'
    ]
    
    # 앞뒤로 공백 추가하는 조사/어미
    particles_both = ['및', '등', '이후', '또는']
    
    # 뒤에만 공백 추가
    for token in particles_suffix:
        text = re.sub(rf'({re.escape(token)})(?=\S)', r'\1 ', text)
    
    # 앞뒤로 공백 추가
    for token in particles_both:
        # 앞뒤에 공백이 없으면 추가
        text = re.sub(rf'(?<!\s)({re.escape(token)})(?!\s)', r' \1 ', text)
    
    return text


def wrap_related_sections(text: str) -> str:
    """'관련법규', '관련규정' 앞에 줄바꿈을 넣고 <>로 감싸서 구분"""
    if text is None:
        return text
    
    def _wrap(match: re.Match) -> str:
        word = match.group(1)
        prefix = '\n' if match.start() != 0 else ''
        return f"{prefix}<{word}>"
    
    return re.sub(r'(관련법규|관련규정)', _wrap, text)


def clean_content_symbols(text: str) -> str:
    """내용 필드에서 불필요한 기호 및 공백 제거"""
    if text is None:
        return text
    # 지정된 불필요 기호 제거
    text = re.sub(r'[\[\],0]', '', text)
    # 연속 기호(문자·숫자·한글이 아닌 문자) → 단일 언더스코어
    text = re.sub(r'[^0-9A-Za-z가-힣\s]+', '_', text)
    
    # 1차로 모든 공백 제거
    text = remove_all_whitespace(text)
    
    # '관련법규'/'관련규정'을 줄바꿈 + <>로 강조
    text = wrap_related_sections(text)
    
    # 조사/어미 뒤에 띄어쓰기 강제
    text = add_particle_spacing(text)
    
    # 과도한 공백 정리
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def process_ocr_text(text, preserve_spacing=False):
    """
    OCR 텍스트 후처리
    
    Args:
        text: OCR로 추출된 텍스트
        preserve_spacing: 띄어쓰기 보존 여부 (True면 collapse_split_syllables 사용 안 함)
    
    Returns:
        후처리된 텍스트
    """
    if not text:
        return text
    
    # OCR 인공물 제거
    text = clean_ocr_artifacts(text)
    
    # 띄어쓰기 보존 옵션이 False인 경우에만 collapse_split_syllables 적용
    if not preserve_spacing:
        text = collapse_split_syllables(text)
    
    return text

