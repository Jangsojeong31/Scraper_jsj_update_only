"""
소스 패키지를 .whl 파일로 변환하는 스크립트

사용법:
1. 인터넷이 연결된 환경에서 실행
2. 이 스크립트는 source_packages 디렉토리의 .zip, .tar.gz 파일을 .whl로 변환합니다
3. 생성된 .whl 파일을 source_packages 디렉토리에 저장합니다
"""

import os
import subprocess
import sys
from pathlib import Path

def build_wheel_from_source(package_path: Path, output_dir: Path):
    """소스 패키지를 .whl 파일로 빌드"""
    package_name = package_path.stem
    print(f"\n{'='*60}")
    print(f"빌드 중: {package_path.name}")
    print(f"{'='*60}")
    
    try:
        # pip wheel 명령어로 .whl 파일 생성
        cmd = [
            sys.executable, "-m", "pip", "wheel",
            "--no-deps",  # 의존성은 이미 준비되어 있다고 가정
            str(package_path),
            "--wheel-dir", str(output_dir)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        print(f"✓ 성공: {package_path.name} -> .whl 파일 생성 완료")
        if result.stdout:
            print(result.stdout)
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ 실패: {package_path.name}")
        print(f"에러 메시지: {e.stderr}")
        return False
    except Exception as e:
        print(f"✗ 예외 발생: {package_path.name}")
        print(f"에러: {str(e)}")
        return False

def main():
    # 스크립트 위치 기준으로 source_packages 디렉토리 찾기
    script_dir = Path(__file__).parent
    source_packages_dir = script_dir / "source_packages"
    
    if not source_packages_dir.exists():
        print(f"오류: {source_packages_dir} 디렉토리를 찾을 수 없습니다.")
        sys.exit(1)
    
    # 소스 패키지 파일 찾기 (.zip, .tar.gz)
    source_files = []
    for ext in ['.zip', '.tar.gz']:
        source_files.extend(source_packages_dir.glob(f"*{ext}"))
    
    if not source_files:
        print("변환할 소스 패키지 파일이 없습니다.")
        sys.exit(0)
    
    print(f"\n발견된 소스 패키지: {len(source_files)}개")
    for f in source_files:
        print(f"  - {f.name}")
    
    # pip wheel 도구 확인
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "wheel"],
            check=True,
            capture_output=True
        )
    except:
        print("경고: pip wheel 업그레이드 실패 (계속 진행합니다)")
    
    # 각 소스 패키지를 .whl로 변환
    success_count = 0
    for source_file in source_files:
        if build_wheel_from_source(source_file, source_packages_dir):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"완료: {success_count}/{len(source_files)}개 패키지 변환 성공")
    print(f"{'='*60}")
    
    if success_count < len(source_files):
        print("\n일부 패키지 변환에 실패했습니다.")
        print("생성된 .whl 파일을 확인하고, 실패한 패키지는 수동으로 처리해주세요.")
    else:
        print("\n모든 패키지가 성공적으로 변환되었습니다!")
        print("생성된 .whl 파일을 source_packages 디렉토리에서 확인하세요.")

if __name__ == "__main__":
    main()


