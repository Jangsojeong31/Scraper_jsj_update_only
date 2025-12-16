"""
파일 업로드 공통 모듈
JSON/CSV 파일 및 바이너리 파일(HWP, PDF, DOC, DOCX, XLS, XLSX 등)을 REST API를 통해 업로드하는 기능 제공

주요 기능:
- JSON/CSV 데이터 업로드 (배치 처리 지원)
- 바이너리 파일 업로드 (HWP, PDF, DOC 등)
- 여러 파일 일괄 업로드
- 자동 재시도 및 에러 처리
"""
import os
import json
import csv
import requests
from typing import List, Dict, Optional, Union
import time
from pathlib import Path


class FileUploader:
    """파일 업로드 클래스 - REST API를 통한 파일 업로드 지원"""
    
    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        retry_count: int = 3,
        headers: Optional[Dict[str, str]] = None
    ):
        """
        Args:
            api_url: REST API 엔드포인트 URL (예: "https://api.example.com/data/upload")
            api_key: API 인증 키 (선택사항)
            timeout: 요청 타임아웃 (초)
            retry_count: 실패 시 재시도 횟수
            headers: 추가 HTTP 헤더 (선택사항)
        """
        if not api_url:
            raise ValueError("API URL은 필수입니다.")
        
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
        
        # 기본 헤더 설정
        default_headers = {
            'Content-Type': 'application/json'
        }
        
        # API 키가 있으면 헤더에 추가
        if self.api_key:
            default_headers['Authorization'] = f'Bearer {self.api_key}'
        
        # 추가 헤더 저장 (파일 업로드 시에도 사용)
        self._additional_headers = headers if headers else {}
        
        # 추가 헤더가 있으면 병합
        if headers:
            default_headers.update(headers)
        
        self.session.headers.update(default_headers)
    
    def upload_json_file(
        self,
        json_file_path: str,
        batch_size: int = 100,
        endpoint: Optional[str] = None
    ) -> Dict:
        """
        JSON 파일을 API를 통해 업로드
        
        Args:
            json_file_path: 업로드할 JSON 파일 경로
            batch_size: 배치 크기 (한 번에 전송할 레코드 수)
            endpoint: API 엔드포인트 (None이면 self.api_url 사용)
            
        Returns:
            업로드 결과 딕셔너리:
            {
                'success': bool,
                'total_records': int,
                'uploaded_records': int,
                'failed_records': int,
                'errors': List[str],
                'message': str
            }
        """
        if not os.path.exists(json_file_path):
            return {
                'success': False,
                'total_records': 0,
                'uploaded_records': 0,
                'failed_records': 0,
                'errors': [f'파일을 찾을 수 없습니다: {json_file_path}'],
                'message': '파일 없음'
            }
        
        try:
            # JSON 파일 읽기
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 리스트가 아니면 리스트로 변환
            if not isinstance(data, list):
                data = [data]
            
            return self.upload_data(
                data=data,
                batch_size=batch_size,
                endpoint=endpoint
            )
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'total_records': 0,
                'uploaded_records': 0,
                'failed_records': 0,
                'errors': [f'JSON 파싱 오류: {str(e)}'],
                'message': 'JSON 파싱 실패'
            }
        except Exception as e:
            return {
                'success': False,
                'total_records': 0,
                'uploaded_records': 0,
                'failed_records': 0,
                'errors': [f'파일 읽기 오류: {str(e)}'],
                'message': '파일 읽기 실패'
            }
    
    def upload_csv_file(
        self,
        csv_file_path: str,
        batch_size: int = 100,
        endpoint: Optional[str] = None,
        encoding: str = 'utf-8-sig'
    ) -> Dict:
        """
        CSV 파일을 API를 통해 업로드
        
        Args:
            csv_file_path: 업로드할 CSV 파일 경로
            batch_size: 배치 크기 (한 번에 전송할 레코드 수)
            endpoint: API 엔드포인트 (None이면 self.api_url 사용)
            encoding: CSV 파일 인코딩 (기본값: utf-8-sig)
            
        Returns:
            업로드 결과 딕셔너리
        """
        if not os.path.exists(csv_file_path):
            return {
                'success': False,
                'total_records': 0,
                'uploaded_records': 0,
                'failed_records': 0,
                'errors': [f'파일을 찾을 수 없습니다: {csv_file_path}'],
                'message': '파일 없음'
            }
        
        try:
            # CSV 파일 읽기
            data = []
            with open(csv_file_path, 'r', encoding=encoding) as f:
                # 주석 라인 건너뛰기
                reader = csv.DictReader(
                    row for row in f if not row.strip().startswith('#')
                )
                for row in reader:
                    # 빈 값 제거
                    cleaned_row = {k: v for k, v in row.items() if k}
                    if cleaned_row:
                        data.append(cleaned_row)
            
            return self.upload_data(
                data=data,
                batch_size=batch_size,
                endpoint=endpoint
            )
        except Exception as e:
            return {
                'success': False,
                'total_records': 0,
                'uploaded_records': 0,
                'failed_records': 0,
                'errors': [f'CSV 읽기 오류: {str(e)}'],
                'message': 'CSV 읽기 실패'
            }
    
    def upload_data(
        self,
        data: List[Dict],
        batch_size: int = 100,
        endpoint: Optional[str] = None
    ) -> Dict:
        """
        데이터 리스트를 API를 통해 업로드
        
        Args:
            data: 업로드할 데이터 리스트
            batch_size: 배치 크기 (한 번에 전송할 레코드 수)
            endpoint: API 엔드포인트 (None이면 self.api_url 사용)
            
        Returns:
            업로드 결과 딕셔너리
        """
        if not data:
            return {
                'success': False,
                'total_records': 0,
                'uploaded_records': 0,
                'failed_records': 0,
                'errors': ['업로드할 데이터가 없습니다.'],
                'message': '데이터 없음'
            }
        
        url = endpoint or self.api_url
        if not url:
            return {
                'success': False,
                'total_records': len(data),
                'uploaded_records': 0,
                'failed_records': len(data),
                'errors': ['API URL이 설정되지 않았습니다.'],
                'message': 'API URL 없음'
            }
        
        total_records = len(data)
        uploaded_records = 0
        failed_records = 0
        errors = []
        
        # 배치로 나누어 업로드
        total_batches = (total_records + batch_size - 1) // batch_size
        
        print(f"📤 API를 통해 데이터 업로드 시작: {total_records}건 (배치 크기: {batch_size})")
        
        for batch_idx in range(0, total_records, batch_size):
            batch = data[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            
            print(f"  배치 {batch_num}/{total_batches} 업로드 중... ({len(batch)}건)")
            
            # 재시도 로직
            success = False
            last_error = None
            
            for attempt in range(self.retry_count):
                try:
                    response = self.session.post(
                        url,
                        json=batch,
                        timeout=self.timeout
                    )
                    
                    # 성공 응답 확인 (200, 201, 202 등)
                    if response.status_code in [200, 201, 202]:
                        success = True
                        uploaded_records += len(batch)
                        print(f"    ✓ 배치 {batch_num} 업로드 성공")
                        break
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                        if attempt < self.retry_count - 1:
                            wait_time = (attempt + 1) * 2
                            print(f"    ⚠ 재시도 {attempt + 1}/{self.retry_count} ({wait_time}초 후)...")
                            time.sleep(wait_time)
                
                except requests.exceptions.Timeout:
                    last_error = f"요청 타임아웃 ({self.timeout}초)"
                    if attempt < self.retry_count - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"    ⚠ 재시도 {attempt + 1}/{self.retry_count} ({wait_time}초 후)...")
                        time.sleep(wait_time)
                
                except requests.exceptions.RequestException as e:
                    last_error = f"요청 오류: {str(e)}"
                    if attempt < self.retry_count - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"    ⚠ 재시도 {attempt + 1}/{self.retry_count} ({wait_time}초 후)...")
                        time.sleep(wait_time)
                
                except Exception as e:
                    last_error = f"예상치 못한 오류: {str(e)}"
                    break
            
            if not success:
                failed_records += len(batch)
                error_msg = f"배치 {batch_num} 업로드 실패: {last_error}"
                errors.append(error_msg)
                print(f"    ✗ {error_msg}")
            
            # 서버 부하 방지를 위한 대기
            if batch_idx + batch_size < total_records:
                time.sleep(0.5)
        
        result = {
            'success': failed_records == 0,
            'total_records': total_records,
            'uploaded_records': uploaded_records,
            'failed_records': failed_records,
            'errors': errors,
            'message': f'{uploaded_records}/{total_records}건 업로드 완료'
        }
        
        print(f"\n📊 업로드 결과: {result['message']}")
        if errors:
            print(f"  ⚠ 실패한 배치: {len(errors)}개")
        
        return result
    
    def upload_file(
        self,
        file_path: str,
        endpoint: Optional[str] = None,
        field_name: str = 'file',
        additional_data: Optional[Dict] = None
    ) -> Dict:
        """
        바이너리 파일(HWP, PDF, DOC 등)을 API를 통해 업로드
        
        Args:
            file_path: 업로드할 파일 경로
            endpoint: API 엔드포인트 (None이면 self.api_url 사용)
            field_name: 서버에서 기대하는 파일 필드명 (기본값: 'file')
            additional_data: 파일과 함께 전송할 추가 데이터 (선택사항)
            
        Returns:
            업로드 결과 딕셔너리:
            {
                'success': bool,
                'file_path': str,
                'file_name': str,
                'file_size': int,
                'error': Optional[str],
                'message': str
            }
        """
        if not os.path.exists(file_path):
            return {
                'success': False,
                'file_path': file_path,
                'file_name': os.path.basename(file_path),
                'file_size': 0,
                'error': f'파일을 찾을 수 없습니다: {file_path}',
                'message': '파일 없음'
            }
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        url = endpoint or self.api_url
        
        if not url:
            return {
                'success': False,
                'file_path': file_path,
                'file_name': file_name,
                'file_size': file_size,
                'error': 'API URL이 설정되지 않았습니다.',
                'message': 'API URL 없음'
            }
        
        print(f"📤 파일 업로드 시작: {file_name} ({file_size:,} bytes)")
        
        # 재시도 로직
        last_error = None
        
        for attempt in range(self.retry_count):
            try:
                # 파일을 바이너리로 읽기
                with open(file_path, 'rb') as f:
                    files = {
                        field_name: (file_name, f, self._get_content_type(file_path))
                    }
                    
                    # 추가 데이터가 있으면 data에 포함
                    data = additional_data if additional_data else None
                    
                    # multipart/form-data로 업로드 (Content-Type 헤더는 requests가 자동 설정)
                    # Authorization 헤더는 유지해야 하므로 별도로 설정
                    headers = {}
                    if self.api_key:
                        headers['Authorization'] = f'Bearer {self.api_key}'
                    
                    # 추가 헤더가 있으면 병합
                    if hasattr(self, '_additional_headers'):
                        headers.update(self._additional_headers)
                    
                    # 파일 업로드 시에는 Content-Type을 자동으로 설정하도록 헤더에서 제거
                    upload_headers = {k: v for k, v in self.session.headers.items() 
                                    if k.lower() != 'content-type'}
                    upload_headers.update(headers)
                    
                    response = self.session.post(
                        url,
                        files=files,
                        data=data,
                        headers=upload_headers,
                        timeout=self.timeout
                    )
                
                # 성공 응답 확인 (200, 201, 202 등)
                if response.status_code in [200, 201, 202]:
                    print(f"  ✓ 파일 업로드 성공: {file_name}")
                    return {
                        'success': True,
                        'file_path': file_path,
                        'file_name': file_name,
                        'file_size': file_size,
                        'error': None,
                        'message': f'파일 업로드 성공: {file_name}',
                        'response': response.json() if response.content else None
                    }
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                    if attempt < self.retry_count - 1:
                        wait_time = (attempt + 1) * 2
                        print(f"  ⚠ 재시도 {attempt + 1}/{self.retry_count} ({wait_time}초 후)...")
                        time.sleep(wait_time)
            
            except requests.exceptions.Timeout:
                last_error = f"요청 타임아웃 ({self.timeout}초)"
                if attempt < self.retry_count - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"  ⚠ 재시도 {attempt + 1}/{self.retry_count} ({wait_time}초 후)...")
                    time.sleep(wait_time)
            
            except requests.exceptions.RequestException as e:
                last_error = f"요청 오류: {str(e)}"
                if attempt < self.retry_count - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"  ⚠ 재시도 {attempt + 1}/{self.retry_count} ({wait_time}초 후)...")
                    time.sleep(wait_time)
            
            except Exception as e:
                last_error = f"예상치 못한 오류: {str(e)}"
                break
        
        print(f"  ✗ 파일 업로드 실패: {file_name} - {last_error}")
        return {
            'success': False,
            'file_path': file_path,
            'file_name': file_name,
            'file_size': file_size,
            'error': last_error,
            'message': f'파일 업로드 실패: {file_name}'
        }
    
    def upload_files(
        self,
        file_paths: Union[List[str], str],
        endpoint: Optional[str] = None,
        field_name: str = 'file',
        additional_data: Optional[Dict] = None
    ) -> Dict:
        """
        여러 파일을 순차적으로 업로드
        
        Args:
            file_paths: 업로드할 파일 경로 리스트 또는 단일 파일 경로
            endpoint: API 엔드포인트 (None이면 self.api_url 사용)
            field_name: 서버에서 기대하는 파일 필드명 (기본값: 'file')
            additional_data: 각 파일과 함께 전송할 추가 데이터 (선택사항)
            
        Returns:
            업로드 결과 딕셔너리:
            {
                'success': bool,
                'total_files': int,
                'uploaded_files': int,
                'failed_files': int,
                'results': List[Dict],  # 각 파일의 업로드 결과
                'errors': List[str],
                'message': str
            }
        """
        # 단일 파일인 경우 리스트로 변환
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        if not file_paths:
            return {
                'success': False,
                'total_files': 0,
                'uploaded_files': 0,
                'failed_files': 0,
                'results': [],
                'errors': ['업로드할 파일이 없습니다.'],
                'message': '파일 없음'
            }
        
        total_files = len(file_paths)
        uploaded_files = 0
        failed_files = 0
        results = []
        errors = []
        
        print(f"📤 여러 파일 업로드 시작: {total_files}개 파일")
        
        for idx, file_path in enumerate(file_paths, 1):
            print(f"\n[{idx}/{total_files}] {os.path.basename(file_path)}")
            
            result = self.upload_file(
                file_path=file_path,
                endpoint=endpoint,
                field_name=field_name,
                additional_data=additional_data
            )
            
            results.append(result)
            
            if result['success']:
                uploaded_files += 1
            else:
                failed_files += 1
                errors.append(f"{result['file_name']}: {result['error']}")
            
            # 서버 부하 방지를 위한 대기
            if idx < total_files:
                time.sleep(0.5)
        
        overall_success = failed_files == 0
        
        result_summary = {
            'success': overall_success,
            'total_files': total_files,
            'uploaded_files': uploaded_files,
            'failed_files': failed_files,
            'results': results,
            'errors': errors,
            'message': f'{uploaded_files}/{total_files}개 파일 업로드 완료'
        }
        
        print(f"\n📊 업로드 결과: {result_summary['message']}")
        if errors:
            print(f"  ⚠ 실패한 파일: {len(errors)}개")
            for error in errors[:5]:  # 최대 5개만 출력
                print(f"    - {error}")
            if len(errors) > 5:
                print(f"    ... 외 {len(errors) - 5}개")
        
        return result_summary
    
    def _get_content_type(self, file_path: str) -> str:
        """
        파일 확장자에 따른 Content-Type 반환
        
        Args:
            file_path: 파일 경로
            
        Returns:
            Content-Type 문자열
        """
        ext = Path(file_path).suffix.lower()
        
        content_types = {
            '.hwp': 'application/x-hwp',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.txt': 'text/plain',
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.7z': 'application/x-7z-compressed',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
        }
        
        return content_types.get(ext, 'application/octet-stream')

