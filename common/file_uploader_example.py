"""
파일 업로드 모듈 사용 예제
"""
from common.file_uploader import FileUploader


# ============================================
# 예제 1: 기본 API 업로드
# ============================================
def example_basic_upload():
    """기본적인 JSON/CSV 파일 업로드"""
    
    # 업로더 생성 (API URL과 인증 키 설정)
    uploader = FileUploader(
        api_url="https://api.example.com/data/upload",
        api_key="your-api-key-here",  # 선택사항
        timeout=30,
        retry_count=3
    )
    
    # JSON 파일 업로드
    result = uploader.upload_json_file(
        json_file_path="output/law_scraper.json",
        batch_size=100  # 한 번에 100건씩 전송
    )
    
    print(f"업로드 결과: {result['message']}")
    print(f"성공: {result['success']}")
    print(f"업로드된 레코드: {result['uploaded_records']}/{result['total_records']}")
    
    # CSV 파일 업로드
    result = uploader.upload_csv_file(
        csv_file_path="output/law_scraper.csv",
        batch_size=100
    )
    
    print(f"업로드 결과: {result['message']}")


# ============================================
# 예제 2: 커스텀 헤더 사용
# ============================================
def example_custom_headers():
    """커스텀 HTTP 헤더를 사용한 업로드"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/data/upload",
        api_key="your-api-key-here",
        headers={
            'X-Custom-Header': 'custom-value',
            'X-Client-Version': '1.0.0'
        }
    )
    
    result = uploader.upload_json_file("output/law_scraper.json")
    print(f"업로드 결과: {result['message']}")


# ============================================
# 예제 3: 다른 엔드포인트 사용
# ============================================
def example_custom_endpoint():
    """특정 파일만 다른 엔드포인트로 업로드"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/data/upload",  # 기본 URL
        api_key="your-api-key-here"
    )
    
    # 기본 URL 사용
    result1 = uploader.upload_json_file("output/law_scraper.json")
    
    # 다른 엔드포인트 사용
    result2 = uploader.upload_json_file(
        "output/law_scraper.json",
        endpoint="https://api.example.com/data/special-upload"
    )
    
    print(f"기본 엔드포인트 결과: {result1['message']}")
    print(f"커스텀 엔드포인트 결과: {result2['message']}")


# ============================================
# 예제 4: 데이터 리스트 직접 업로드
# ============================================
def example_direct_data_upload():
    """데이터 리스트를 직접 업로드"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/data/upload",
        api_key="your-api-key-here"
    )
    
    # 업로드할 데이터
    data = [
        {'id': 1, 'title': '제목1', 'content': '내용1'},
        {'id': 2, 'title': '제목2', 'content': '내용2'},
        {'id': 3, 'title': '제목3', 'content': '내용3'},
    ]
    
    # 데이터 업로드
    result = uploader.upload_data(
        data=data,
        batch_size=10
    )
    
    print(f"업로드 결과: {result['message']}")


# ============================================
# 예제 5: 스크래퍼에서 사용하기
# ============================================
def example_in_scraper():
    """스크래퍼 코드에서 사용하는 예제"""
    
    # 스크래핑 후 결과 저장
    results = [
        {'번호': 1, '제목': '법규1', '내용': '내용1'},
        {'번호': 2, '제목': '법규2', '내용': '내용2'},
    ]
    
    # JSON 파일로 저장
    import json
    with open('output/results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # API를 통해 업로드
    uploader = FileUploader(
        api_url="https://api.example.com/data/upload",
        api_key="your-api-key-here"
    )
    
    result = uploader.upload_json_file('output/results.json')
    
    if result['success']:
        print(f"✅ 업로드 성공: {result['uploaded_records']}건")
    else:
        print(f"❌ 업로드 실패: {result['message']}")
        if result['errors']:
            for error in result['errors']:
                print(f"  - {error}")


# ============================================
# 예제 6: 환경변수에서 설정 읽기
# ============================================
def example_from_env():
    """환경변수에서 API 설정 읽기"""
    import os
    
    uploader = FileUploader(
        api_url=os.getenv('UPLOAD_API_URL', 'https://api.example.com/data/upload'),
        api_key=os.getenv('UPLOAD_API_KEY')  # None이면 헤더에 추가되지 않음
    )
    
    result = uploader.upload_json_file("output/law_scraper.json")
    print(f"업로드 결과: {result['message']}")


# ============================================
# 예제 7: 바이너리 파일 업로드 (HWP, PDF, DOC 등)
# ============================================
def example_binary_file_upload():
    """바이너리 파일(HWP, PDF, DOC 등) 업로드"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/files/upload",
        api_key="your-api-key-here"
    )
    
    # 단일 파일 업로드
    result = uploader.upload_file(
        file_path="output/downloads/document.pdf",
        field_name="file"  # 서버에서 기대하는 필드명
    )
    
    if result['success']:
        print(f"✅ 파일 업로드 성공: {result['file_name']}")
    else:
        print(f"❌ 파일 업로드 실패: {result['error']}")
    
    # HWP 파일 업로드
    result = uploader.upload_file("output/downloads/document.hwp")
    print(f"업로드 결과: {result['message']}")
    
    # DOC 파일 업로드
    result = uploader.upload_file("output/downloads/document.doc")
    print(f"업로드 결과: {result['message']}")


# ============================================
# 예제 8: 여러 파일 일괄 업로드
# ============================================
def example_multiple_files_upload():
    """여러 파일을 한 번에 업로드"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/files/upload",
        api_key="your-api-key-here"
    )
    
    # 여러 파일 경로 리스트
    file_paths = [
        "output/downloads/file1.pdf",
        "output/downloads/file2.hwp",
        "output/downloads/file3.doc"
    ]
    
    # 여러 파일 업로드
    result = uploader.upload_files(
        file_paths=file_paths,
        field_name="file"
    )
    
    print(f"전체 업로드 결과: {result['message']}")
    print(f"성공: {result['uploaded_files']}개, 실패: {result['failed_files']}개")


# ============================================
# 예제 9: 파일과 메타데이터 함께 업로드
# ============================================
def example_file_with_metadata():
    """파일과 함께 메타데이터 전송"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/files/upload",
        api_key="your-api-key-here"
    )
    
    # 파일과 함께 전송할 추가 데이터
    additional_data = {
        'title': '법규 문서',
        'category': '법규',
        'source': '법제처',
        'upload_date': '2024-01-01'
    }
    
    result = uploader.upload_file(
        file_path="output/downloads/document.pdf",
        additional_data=additional_data
    )
    
    print(f"업로드 결과: {result['message']}")


# ============================================
# 예제 10: 스크래퍼에서 다운로드한 파일 업로드
# ============================================
def example_upload_downloaded_files():
    """스크래퍼에서 다운로드한 파일들을 업로드"""
    
    uploader = FileUploader(
        api_url="https://api.example.com/files/upload",
        api_key="your-api-key-here"
    )
    
    import os
    import glob
    
    # 다운로드 폴더의 모든 PDF 파일 찾기
    download_dir = "output/downloads"
    pdf_files = glob.glob(os.path.join(download_dir, "*.pdf"))
    hwp_files = glob.glob(os.path.join(download_dir, "*.hwp"))
    
    # 모든 파일 업로드
    all_files = pdf_files + hwp_files
    
    if all_files:
        result = uploader.upload_files(all_files)
        print(f"업로드 완료: {result['uploaded_files']}/{result['total_files']}개")
    else:
        print("업로드할 파일이 없습니다.")


if __name__ == "__main__":
    print("파일 업로드 모듈 사용 예제")
    print("=" * 50)
    print("\n각 예제 함수를 호출하여 사용할 수 있습니다.")
    print("\n예: example_basic_upload()")
    print("예: example_binary_file_upload()")

