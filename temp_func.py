def extract_sanction_info(content):
    """제재조치내용에서 제재대상과 제재내용 추출"""
    if not content or content.startswith('[') or content.startswith('[오류'):
        return '', ''
    
    targets = []
    sanctions = []
    
    # OCR로 추출된 텍스트는 글자 사이에 공백이 있을 수 있음 (예: "기 관")
    content = collapse_split_syllables(content)
    # 공백 제거 버전도 확인
    content_no_space = content.replace(' ', '')

    # 반복적으로 등장하는 OCR 치환 오류 보정
    ocr_replacements = {
        '오 혐 설 계 사': '보험설계사',
        '오혐설계사': '보험설계사',
        '로 혐 설 계 사': '보험설계사',
        '로혐설계사': '보험설계사',
        '견 무 정 지': '업무정지',
        '견무정지': '업무정지'
    }
    for wrong, correct in ocr_replacements.items():
        content = content.replace(wrong, correct)
        content_no_space = content_no_space.replace(wrong.replace(' ', ''), correct.replace(' ', ''))
 
    target_alias_map = {
        '기관': '기관',
        '임원': '임원',
        '직원': '직원',
        '임직원': '임직원',
        '임원직원': '임원|직원',
        '임원/직원': '임원|직원',
        '임원·직원': '임원|직원',
        '임원ㆍ직원': '임원|직원',
        '임·직원': '임원|직원',
        '임ㆍ직원': '임원|직원',
        '임원및직원': '임원|직원',
        '임원과직원': '임원|직원',
        '보험설계사': '보험설계사',
        '보험설계사등': '보험설계사 등',
        '보험대리점': '보험대리점',
        '보험중개사': '보험중개사',
        '재심': '재심'
    }

    # "등" 접미사가 붙은 대상을 표준화
    target_alias_map.update({
        '기관등': '기관 등',
        '임원등': '임원 등',
        '직원등': '직원 등'
    })

    def clean_fragment(fragment: str) -> str:
        fragment = fragment.strip()
        fragment = re.sub(r'^[|\-·•◦\.]+\s*', '', fragment)
        fragment = fragment.strip(' ,;')
        fragment = re.sub(r'\s*,\s*', ', ', fragment)
        fragment = re.sub(r'\s+', ' ', fragment)
        return fragment
