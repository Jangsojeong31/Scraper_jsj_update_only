"""
법규 목록 API 클라이언트
외규 DB에서 법규 목록을 가져오고 업데이트하는 공통 모듈
"""
import os
import json
import requests
from typing import List, Dict, Optional
from pathlib import Path

# 공통 로거 사용
from common.common_logger import get_logger

logger = get_logger(
    name="regulation_api_client",
    log_file="regulation_api_client.log"
)

# 기본 타임아웃 설정
DEFAULT_TIMEOUT = 30


def load_env_file():
    """.env 파일을 직접 파싱하여 환경변수에 설정"""
    try:
        # 프로젝트 루트 찾기 (common 디렉토리 기준)
        current = Path(__file__).resolve().parent.parent
        if (current / 'common').exists():
            project_root = current
        else:
            project_root = Path.cwd()
    except:
        project_root = Path.cwd()
    
    env_paths = [
        project_root / '.env',
    ]
    
    # .env 파일 직접 파싱
    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # 주석이나 빈 줄 건너뛰기
                        if not line or line.startswith('#'):
                            continue
                        # KEY=VALUE 형식 파싱
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            # 따옴표 제거
                            if value.startswith('"') and value.endswith('"'):
                                value = value[1:-1]
                            elif value.startswith("'") and value.endswith("'"):
                                value = value[1:-1]
                            # 환경변수에 설정 (이미 있으면 덮어쓰지 않음)
                            if key and value and key not in os.environ:
                                os.environ[key] = value
                logger.info(f".env 파일 로드: {env_path}")
                return True
            except Exception as e:
                logger.warning(f".env 파일 파싱 중 오류 ({env_path}): {e}")
                continue
    
    # python-dotenv도 시도 (설치되어 있으면 사용)
    try:
        from dotenv import load_dotenv
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path, override=True)
                logger.info(f".env 파일 로드 (dotenv): {env_path}")
                return True
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"dotenv 로드 중 오류: {e}")
    
    return False


# 모듈 로드 시 .env 파일 자동 로드
load_env_file()


class RegulationAPIClient:
    """법규 목록 API 클라이언트 - srceCd 기반"""
    
    def __init__(self, base_url: str = None, api_key: str = None):
        """
        Args:
            base_url: API 베이스 URL (None이면 환경변수에서 읽기)
            api_key: API 인증 키 (None이면 환경변수에서 읽기)
        """
        # 환경변수에서 읽기
        self.base_url = (base_url or os.getenv('BASE_URL', '')).rstrip('/')
        self.api_key = api_key or os.getenv('API_KEY', '')
        
        if not self.base_url:
            raise ValueError(
                "API URL이 설정되지 않았습니다. "
                "환경변수 BASE_URL을 설정하거나 base_url 인자를 제공하세요."
            )
        
        self.session = requests.Session()
        
        # 기본 헤더 설정
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # API 키가 있으면 인증 헤더 추가
        if self.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_key}'
            })
            logger.info("API 클라이언트 초기화 완료 (인증 키 포함)")
        else:
            logger.warning("API 클라이언트 초기화 완료 (인증 키 없음)")
    
    def get_regulations(self, srce_cd: str) -> List[Dict]:
        """
        출처 코드로 필터링된 법규 목록 가져오기
        
        Args:
            srce_cd: 출처 코드 (예: 'FSB', 'KRX', 'LAW', 'KFA', 'CFA')
            
        Returns:
            법규 목록 리스트
            
        Raises:
            requests.RequestException: API 요청 실패 시
            ValueError: 응답 코드가 OK가 아닐 때
        """
        url = f"{self.base_url}/api/v1/external/selectOutsRegu"
        params = {'srceCd': srce_cd}
        
        try:
            logger.info(f"API 요청: {url}?srceCd={srce_cd}")
            print(f"✓ API 요청: {url}?srceCd={srce_cd}")
            
            response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            # 응답 코드 확인
            ret_code = data.get('retCode', '')
            if ret_code != 'OK':
                ret_msg = data.get('retMsg', '알 수 없는 오류')
                ret_sys_msg = data.get('retSysMsg', '')
                error_msg = f"API 응답 오류: {ret_code} - {ret_msg}"
                if ret_sys_msg:
                    error_msg += f" ({ret_sys_msg})"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            regulations = data.get('data', [])
            logger.info(f"API 응답 성공: {len(regulations)}개 레코드")
            print(f"✓ API 응답 성공: {len(regulations)}개 레코드")
            return regulations
            
        except requests.RequestException as e:
            error_msg = f"API 요청 실패: {e}"
            logger.error(error_msg)
            print(f"✗ {error_msg}")
            raise Exception(error_msg)
        except json.JSONDecodeError as e:
            error_msg = f"JSON 파싱 실패: {e}"
            logger.error(error_msg)
            print(f"✗ {error_msg}")
            raise ValueError(f"응답이 유효한 JSON 형식이 아닙니다: {e}")
    
    def update_regulation(self, regulation_id: str, data: Dict) -> bool:
        """
        법규 정보 업데이트
        
        Args:
            regulation_id: 외규 ID (outsReguPk)
            data: 업데이트할 데이터
                - revision_reason: 개정이유
                - revision_content: 개정내용
                - revision_date: 개정일
                - 기타 필드...
            
        Returns:
            성공 여부 (True/False)
        """
        url = f"{self.base_url}/api/v1/external/updateOutsRegu"
        
        # regulation_id를 data에 포함
        update_data = data.copy()
        update_data['outsReguPk'] = regulation_id
        
        try:
            logger.info(f"API 업데이트 요청: {url} (ID: {regulation_id})")
            print(f"✓ API 업데이트 요청: {url} (ID: {regulation_id})")
            
            response = self.session.post(url, json=update_data, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            result = response.json()
            ret_code = result.get('retCode', '')
            
            if ret_code == 'OK':
                logger.info(f"API 업데이트 성공: {regulation_id}")
                print(f"✓ API 업데이트 성공: {regulation_id}")
                return True
            else:
                ret_msg = result.get('retMsg', '알 수 없는 오류')
                logger.warning(f"API 업데이트 실패: {ret_code} - {ret_msg}")
                print(f"⚠ API 업데이트 실패: {ret_code} - {ret_msg}")
                return False
            
        except requests.RequestException as e:
            logger.error(f"API 업데이트 요청 실패: {e}")
            print(f"⚠ API 업데이트 요청 실패: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"API 업데이트 응답 JSON 파싱 실패: {e}")
            print(f"⚠ API 업데이트 응답 파싱 실패: {e}")
            return False

