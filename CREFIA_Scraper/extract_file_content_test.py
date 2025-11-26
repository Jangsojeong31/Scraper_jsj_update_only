"""
downloads 폴더의 파일을 선택하여 전체 내용을 추출하는 스크립트
"""
import sys
from pathlib import Path
import os

# 프로젝트 루트 찾기 (common 모듈 import 위해)
def find_project_root():
    try:
        current = Path(__file__).resolve().parent
    except NameError:
        current = Path.cwd()
    
    while current != current.parent:
        if (current / 'common').exists() and (current / 'common' / 'base_scraper.py').exists():
            return current
        current = current.parent
    
    return Path.cwd()

project_root = find_project_root()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from common.file_extractor import FileExtractor
from data_scraper import extract_data_from_text, extract_dates_from_filename


def list_download_files(download_dir: str) -> list:
    """downloads 폴더의 파일 목록 반환"""
    if not os.path.exists(download_dir):
        print(f"⚠ 다운로드 폴더가 존재하지 않습니다: {download_dir}")
        return []
    
    files = []
    for item in os.listdir(download_dir):
        item_path = os.path.join(download_dir, item)
        if os.path.isfile(item_path):
            files.append(item)
    
    return sorted(files)


def extract_full_content(file_path: str) -> str:
    """파일의 전체 내용 추출"""
    file_extractor = FileExtractor(download_dir=os.path.dirname(file_path))
    
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.hwp':
        content = file_extractor.extract_hwp_content(file_path)
    elif file_ext == '.pdf':
        content = file_extractor.extract_pdf_content(file_path)
    elif file_ext in ['.doc', '.docx']:
        # Word 파일은 현재 지원하지 않지만, 필요시 추가 가능
        content = f"Word 파일 형식은 현재 지원하지 않습니다: {file_path}"
    else:
        # 텍스트 파일인 경우 직접 읽기
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='cp949') as f:
                    content = f.read()
            except Exception as e:
                content = f"파일 읽기 실패: {e}"
        except Exception as e:
            content = f"파일 읽기 실패: {e}"
    
    return content


def main():
    """메인 함수"""
    # downloads 폴더 경로
    download_dir = os.path.join("output", "downloads")
    download_dir_abs = os.path.abspath(download_dir)
    
    print(f"📂 다운로드 폴더: {download_dir_abs}\n")
    
    # 파일 목록 가져오기
    files = list_download_files(download_dir_abs)
    
    if not files:
        print("⚠ 다운로드 폴더에 파일이 없습니다.")
        return
    
    # 파일 목록 출력
    print("📋 파일 목록:")
    for idx, filename in enumerate(files, 1):
        file_path = os.path.join(download_dir_abs, filename)
        file_size = os.path.getsize(file_path)
        print(f"  [{idx}] {filename} ({file_size:,} bytes)")
    
    print()
    
    # 파일 선택
    try:
        choice = input("추출할 파일 번호를 입력하세요 (1-{}): ".format(len(files)))
        file_idx = int(choice) - 1
        
        if file_idx < 0 or file_idx >= len(files):
            print("⚠ 잘못된 번호입니다.")
            return
        
        selected_file = files[file_idx]
        file_path = os.path.join(download_dir_abs, selected_file)
        
        print(f"\n📄 선택된 파일: {selected_file}")
        print(f"📂 파일 경로: {file_path}\n")
        
        # 파일 내용 추출
        print("⏳ 파일 내용 추출 중...")
        content = extract_full_content(file_path)
        
        print(f"✅ 추출 완료! (총 {len(content):,}자)\n")
        
        # 날짜 정보 추출
        print("📅 날짜 정보 추출 중...")
        filename_enactment, filename_revision = extract_dates_from_filename(selected_file)
        if filename_enactment:
            print(f"  제정일 (파일명): {filename_enactment}")
        if filename_revision:
            print(f"  개정일 (파일명): {filename_revision}")
        
        # 파일 내용에서도 추출
        if content:
            content_enactment, content_revision, content_department = extract_data_from_text(content[:500])
            if content_enactment:
                print(f"  제정일 (파일내용): {content_enactment}")
            if content_revision:
                print(f"  개정일 (파일내용): {content_revision}")
            if content_department:
                print(f"  소관부서: {content_department}")
        
        print()
        
        # 결과 저장 옵션
        save_choice = input("결과를 파일로 저장하시겠습니까? (y/n): ").strip().lower()
        
        if save_choice == 'y':
            # 추출된 파일 저장용 폴더 생성
            extracted_dir = os.path.join(download_dir_abs, "extracted")
            os.makedirs(extracted_dir, exist_ok=True)
            
            # 출력 파일명 생성
            base_name = os.path.splitext(selected_file)[0]
            output_file = os.path.join(extracted_dir, f"{base_name}_extracted.txt")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"파일명: {selected_file}\n")
                f.write(f"파일 경로: {file_path}\n")
                f.write("=" * 80 + "\n\n")
                f.write("추출된 내용:\n")
                f.write("=" * 80 + "\n\n")
                f.write(content)
                f.write("\n\n" + "=" * 80 + "\n")
                f.write("날짜 정보:\n")
                f.write("=" * 80 + "\n")
                if filename_enactment:
                    f.write(f"제정일 (파일명): {filename_enactment}\n")
                if filename_revision:
                    f.write(f"개정일 (파일명): {filename_revision}\n")
                if content_enactment:
                    f.write(f"제정일 (파일내용): {content_enactment}\n")
                if content_revision:
                    f.write(f"개정일 (파일내용): {content_revision}\n")
                if content_department:
                    f.write(f"소관부서: {content_department}\n")
            
            print(f"✅ 결과 저장 완료: {output_file}")
        else:
            # 콘솔에 출력 (처음 1000자만)
            print("\n" + "=" * 80)
            print("파일 내용 (처음 1000자):")
            print("=" * 80)
            print(content[:1000])
            if len(content) > 1000:
                print(f"\n... (총 {len(content):,}자 중 1000자만 표시)")
            print("=" * 80)
    
    except ValueError:
        print("⚠ 숫자를 입력해주세요.")
    except KeyboardInterrupt:
        print("\n\n⚠ 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

