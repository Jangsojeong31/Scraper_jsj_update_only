"""
KoFIU JSON 파일에서 상세페이지URL을 읽어 PDF 추출 테스트
- 기존 JSON 파일의 상세페이지URL로 파일 다운로드
- PDF 추출 및 메타데이터 추출
- 기존 스크래퍼와 동일한 로직 적용
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

# common 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from common.file_extractor import FileExtractor
from extract_metadata import extract_metadata_from_content, extract_sanction_details, extract_incidents, format_date_to_iso
from ocr_extractor import OCRExtractor
from post_process_ocr import process_ocr_text, clean_content_symbols

# 기존 스크래퍼 클래스에서 필요한 메서드 import
from kofiu_scraper_v2 import KoFIUScraperV2

sys.stdout.reconfigure(encoding='utf-8')


class KoFIUTestExtractor:
    """JSON 파일에서 URL을 읽어 PDF 추출하는 테스트 클래스"""
    
    def __init__(self):
        # 기존 스크래퍼 인스턴스 생성 (업종 매핑 등 재사용)
        self.scraper = KoFIUScraperV2()
        self.results = []
    
    def derive_filename(self, url: str) -> str:
        """URL에서 파일명 추출"""
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        
        # fileNm 파라미터에서 파일명 추출
        if 'fileNm' in query and query['fileNm']:
            filename = unquote(query['fileNm'][0])
            return filename
        
        # URL 경로에서 파일명 추출
        path_name = parsed.path.split('/')[-1]
        if path_name:
            return unquote(path_name)
        
        return f"attachment_{int(time.time()*1000)}.pdf"
    
    def process_json_file(self, json_file_path: str):
        """JSON 파일을 읽어서 각 항목의 상세페이지URL로 PDF 추출"""
        print("=" * 60)
        print("KoFIU JSON 파일에서 PDF 추출 테스트")
        print("=" * 60)
        
        # JSON 파일 읽기
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\n총 {len(data)}개 항목 발견")
        print("\nPDF 추출 시작...\n")
        
        for idx, item in enumerate(data, 1):
            detail_url = item.get('상세페이지URL', '')
            if not detail_url:
                print(f"[{idx}/{len(data)}] 상세페이지URL이 없어 건너뜀")
                continue
            
            # 기존 데이터 유지
            result_item = item.copy()
            
            # 파일명 추출
            filename = self.derive_filename(detail_url)
            print(f"\n[{idx}/{len(data)}] {filename} 처리 중...")
            print(f"  URL: {detail_url}")
            
            # PDF 다운로드 및 추출 (기존 스크래퍼의 메서드 사용)
            attachment_content, doc_type, file_download_url = self.scraper.extract_attachment_content(
                detail_url,
                filename
            )
            
            result_item['파일다운로드URL'] = file_download_url
            result_item['제재조치내용'] = attachment_content
            
            # OCR 추출 여부 설정
            is_ocr = doc_type == 'PDF-OCR'
            result_item['OCR추출여부'] = '예' if is_ocr else '아니오'
            
            # PDF 내용에서 금융회사명, 제재조치일, 제재내용 추출
            if attachment_content and not attachment_content.startswith('['):
                if is_ocr:
                    print(f"  OCR 텍스트로 메타데이터 추출 중...")
                
                institution, sanction_date = extract_metadata_from_content(attachment_content)
                
                # 금융회사명: 기존 값이 있으면 유지, 없으면 PDF에서 추출한 값 사용
                if not result_item.get('금융회사명'):
                    if institution:
                        # 마지막 '*', '@' 제거
                        institution = institution.rstrip('*@')
                        result_item['금융회사명'] = institution
                        print(f"  금융회사명 (PDF): {institution}")
                
                # 업종 매핑 (기존 값이 없거나 '기타'인 경우만 업데이트)
                final_institution = result_item.get('금융회사명', '')
                if final_institution:
                    industry = self.scraper.get_industry(final_institution)
                    if not result_item.get('업종') or result_item.get('업종') == '기타':
                        result_item['업종'] = industry
                        print(f"  업종: {industry}")
                
                # 제재조치일: 기존 값이 없으면 PDF에서 추출한 값 사용
                if not result_item.get('제재조치일') and sanction_date:
                    result_item['제재조치일'] = sanction_date
                    print(f"  제재조치일 추출: {sanction_date}")
                
                # 제재내용 (표 데이터) 추출
                try:
                    sanction_details = extract_sanction_details(attachment_content)
                    if sanction_details:
                        result_item['제재내용'] = sanction_details
                        print(f"  제재내용 추출: {len(sanction_details)}자")
                    else:
                        print(f"  제재내용 추출: 없음")
                except Exception as e:
                    print(f"  ⚠ 제재내용 추출 중 오류 발생: {e}")
                    import traceback
                    traceback.print_exc()
                    if not result_item.get('제재내용'):
                        result_item['제재내용'] = ''
                
                # 사건 제목/내용 추출 (4번 항목)
                incidents = {}
                try:
                    print(f"  사건 제목/내용 추출 중...")
                    incidents = extract_incidents(attachment_content)
                    if incidents:
                        # OCR 추출인 경우 '내용' 필드에 clean_content_symbols 적용
                        if is_ocr:
                            for key in list(incidents.keys()):
                                if key.startswith('내용'):
                                    # 먼저 process_ocr_text로 기본 후처리 (띄어쓰기 보존)
                                    processed = process_ocr_text(incidents[key], preserve_spacing=True)
                                    # 그 다음 clean_content_symbols로 조사 뒤 띄어쓰기 추가
                                    incidents[key] = clean_content_symbols(processed)
                        result_item.update(incidents)
                        incident_count = len([k for k in incidents.keys() if k.startswith('제목')])
                        print(f"  사건 추출: {incident_count}건")
                    else:
                        print(f"  사건 추출: 없음")
                except Exception as e:
                    print(f"  ⚠ 사건 추출 중 오류 발생: {e}")
                    import traceback
                    traceback.print_exc()
                    incidents = {}
                
                # 메타데이터 추출 결과가 모두 비어있고, 일반 텍스트 추출이었던 경우 OCR 재시도
                # 금융회사명, 제재조치일은 제외 (목록에서 추출하거나 필수 항목이 아님)
                has_metadata = (
                    result_item.get('제재내용') or 
                    incidents
                )
                
                if (not has_metadata and 
                    doc_type == 'PDF-텍스트' and 
                    attachment_content and 
                    len(attachment_content.strip()) > 0 and
                    not attachment_content.startswith('[')):
                    print(f"  ⚠ 메타데이터 추출 실패 - OCR 재시도 중...")
                    # 파일을 다시 다운로드하여 OCR 시도
                    if self.scraper.is_pdf_url(detail_url):
                        filename = self.derive_filename(detail_url)
                        file_path, actual_filename = self.scraper.file_extractor.download_file(
                            url=detail_url,
                            filename=filename,
                            referer=self.scraper.list_url
                        )
                        
                        if file_path and os.path.exists(file_path) and self.scraper.ocr_extractor.is_available():
                            ocr_text = self.scraper.ocr_extractor.extract_text(file_path, mode='auto')
                            if ocr_text:
                                # OCR 결과 후처리
                                ocr_content = process_ocr_text(ocr_text, preserve_spacing=True)
                                result_item['제재조치내용'] = ocr_content
                                result_item['OCR추출여부'] = '예'
                                doc_type = 'PDF-OCR'
                                is_ocr = True
                                
                                print(f"  ✓ OCR 재시도 성공 ({len(ocr_content)}자)")
                                
                                # OCR 텍스트로 메타데이터 재추출
                                institution, sanction_date = extract_metadata_from_content(ocr_content)
                                
                                if not result_item.get('금융회사명'):
                                    if institution:
                                        institution = institution.rstrip('*@')
                                        result_item['금융회사명'] = institution
                                
                                final_institution = result_item.get('금융회사명', '')
                                if final_institution:
                                    industry = self.scraper.get_industry(final_institution)
                                    if not result_item.get('업종') or result_item.get('업종') == '기타':
                                        result_item['업종'] = industry
                                else:
                                    result_item['업종'] = '기타'
                                
                                if not result_item.get('제재조치일') and sanction_date:
                                    result_item['제재조치일'] = sanction_date
                                
                                try:
                                    sanction_details = extract_sanction_details(ocr_content)
                                    if sanction_details:
                                        result_item['제재내용'] = sanction_details
                                except Exception as e:
                                    result_item['제재내용'] = ''
                                
                                try:
                                    incidents = extract_incidents(ocr_content)
                                    if incidents:
                                        for key in list(incidents.keys()):
                                            if key.startswith('내용'):
                                                processed = process_ocr_text(incidents[key], preserve_spacing=True)
                                                incidents[key] = clean_content_symbols(processed)
                                        result_item.update(incidents)
                                except Exception as e:
                                    incidents = {}
                                
                                # 임시 파일 삭제
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                            else:
                                print(f"  ✗ OCR 재시도 실패 (결과 없음)")
                                # 임시 파일 삭제
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                        else:
                            print(f"  ✗ OCR 재시도 불가 (파일 다운로드 실패 또는 OCR 사용 불가)")
            
            # 업종 필드가 없는 경우 기타로 설정
            if '업종' not in result_item:
                result_item['업종'] = '기타'
            
            # OCR추출여부 필드가 없는 경우 기본값 설정
            if 'OCR추출여부' not in result_item:
                result_item['OCR추출여부'] = '아니오'
            
            self.results.append(result_item)
            time.sleep(1)  # 서버 부하 방지
        
        # 리소스 정리
        self.scraper.close()
    
    def save_results(self, filename='test_kofiu_results.json'):
        """결과 저장 (기존 스크래퍼의 save_results 메서드 재사용)"""
        # 기존 스크래퍼의 _split_incidents 메서드 사용
        self.scraper.results = self.results
        self.scraper.save_results(filename)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='KoFIU JSON 파일에서 PDF 추출 테스트')
    parser.add_argument('--input', type=str, default='kofiu_results.json', 
                       help='입력 JSON 파일 경로 (기본값: kofiu_results.json)')
    parser.add_argument('--output', type=str, default='test_kofiu_results.json',
                       help='출력 JSON 파일명 (기본값: test_kofiu_results.json)')
    
    args = parser.parse_args()
    
    # 입력 파일 경로 확인
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, args.input)
    
    if not os.path.exists(input_path):
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return
    
    # 추출 실행
    extractor = KoFIUTestExtractor()
    extractor.process_json_file(input_path)
    extractor.save_results(args.output)
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print(f"결과가 {args.output}에 저장되었습니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()

