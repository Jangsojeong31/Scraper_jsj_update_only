"""
파일 비교 공통 모듈
다운로드한 파일과 기존 파일을 비교하여 변경사항을 감지
"""
import os
import hashlib
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class FileComparator:
    """파일 비교 클래스 - 다운로드한 파일과 기존 파일 비교"""
    
    def __init__(self, base_dir: str = "output/downloads"):
        """
        Args:
            base_dir: 파일 저장 기본 디렉토리
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        # PDF 텍스트 추출 결과 캐싱 (중복 추출 방지)
        self._pdf_text_cache: Dict[str, str] = {}
    
    def get_file_hash(self, filepath: str) -> Optional[str]:
        """
        파일의 해시값 계산 (MD5)
        
        Args:
            filepath: 파일 경로
            
        Returns:
            MD5 해시값 또는 None
        """
        if not os.path.exists(filepath):
            return None
        
        try:
            hash_md5 = hashlib.md5()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            print(f"  ⚠ 파일 해시 계산 실패 ({filepath}): {e}")
            return None
    
    def compare_files(self, new_file: str, old_file: str) -> Dict:
        """
        두 파일을 비교하여 변경사항 반환
        
        Args:
            new_file: 새 파일 경로
            old_file: 기존 파일 경로
            
        Returns:
            비교 결과 딕셔너리:
            {
                'changed': bool,  # 변경 여부
                'new_exists': bool,  # 새 파일 존재 여부
                'old_exists': bool,  # 기존 파일 존재 여부
                'same_content': bool,  # 내용 동일 여부
                'new_hash': str,  # 새 파일 해시
                'old_hash': str,  # 기존 파일 해시
                'new_size': int,  # 새 파일 크기
                'old_size': int,  # 기존 파일 크기
                'diff_summary': str,  # 변경사항 요약
            }
        """
        result = {
            'changed': False,
            'new_exists': os.path.exists(new_file),
            'old_exists': os.path.exists(old_file),
            'same_content': False,
            'new_hash': None,
            'old_hash': None,
            'new_size': 0,
            'old_size': 0,
            'diff_summary': '',
        }
        
        # 새 파일 정보
        if result['new_exists']:
            result['new_hash'] = self.get_file_hash(new_file)
            result['new_size'] = os.path.getsize(new_file)
        
        # 기존 파일 정보
        if result['old_exists']:
            result['old_hash'] = self.get_file_hash(old_file)
            result['old_size'] = os.path.getsize(old_file)
        
        # 두 파일 모두 존재하는 경우 비교
        if result['new_exists'] and result['old_exists']:
            # 해시 비교 (빠른 비교)
            if result['new_hash'] == result['old_hash']:
                result['same_content'] = True
                result['diff_summary'] = '파일 내용 동일 (해시 일치)'
            else:
                result['changed'] = True
                result['same_content'] = False
                
                # 텍스트 파일인 경우 상세 diff 생성
                if self._is_text_file(new_file) and self._is_text_file(old_file):
                    diff_summary = self._get_text_diff_summary(old_file, new_file)
                    result['diff_summary'] = diff_summary
                elif self._is_pdf_file(new_file) and self._is_pdf_file(old_file):
                    # PDF 파일인 경우 텍스트 추출 후 비교
                    pdf_diff_summary = self._get_pdf_diff_summary(old_file, new_file)
                    result['diff_summary'] = pdf_diff_summary
                else:
                    # 바이너리 파일인 경우 크기 비교만
                    size_diff = result['new_size'] - result['old_size']
                    if size_diff > 0:
                        result['diff_summary'] = f'파일 크기 증가: {result["old_size"]} → {result["new_size"]} bytes (+{size_diff})'
                    elif size_diff < 0:
                        result['diff_summary'] = f'파일 크기 감소: {result["old_size"]} → {result["new_size"]} bytes ({size_diff})'
                    else:
                        result['diff_summary'] = f'파일 내용 변경 (크기 동일: {result["new_size"]} bytes)'
        elif result['new_exists'] and not result['old_exists']:
            result['changed'] = True
            result['diff_summary'] = f'새 파일 추가 ({result["new_size"]} bytes)'
        elif not result['new_exists'] and result['old_exists']:
            result['changed'] = True
            result['diff_summary'] = f'파일 삭제됨 (기존: {result["old_size"]} bytes)'
        
        return result
    
    def _is_text_file(self, filepath: str) -> bool:
        """파일이 텍스트 파일인지 확인"""
        try:
            # 확장자로 판단
            text_extensions = ['.txt', '.csv', '.json', '.xml', '.html', '.htm', '.py', '.js', '.md']
            ext = Path(filepath).suffix.lower()
            if ext in text_extensions:
                return True
            
            # 파일 내용으로 판단 (처음 몇 바이트 확인)
            with open(filepath, 'rb') as f:
                chunk = f.read(512)
                # 텍스트 파일은 대부분 인쇄 가능한 문자로 구성
                try:
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    return False
        except:
            return False
    
    def _is_pdf_file(self, filepath: str) -> bool:
        """파일이 PDF 파일인지 확인"""
        try:
            ext = Path(filepath).suffix.lower()
            if ext == '.pdf':
                # PDF 시그니처 확인 (%PDF)
                with open(filepath, 'rb') as f:
                    first_bytes = f.read(4)
                    return first_bytes[:4] == b'%PDF'
            return False
        except:
            return False
    
    def _get_pdf_diff_summary(self, old_file: str, new_file: str) -> str:
        """
        PDF 파일의 diff 요약 생성 (텍스트 추출 후 비교)
        
        Args:
            old_file: 기존 PDF 파일 경로
            new_file: 새 PDF 파일 경로
            
        Returns:
            변경사항 요약 문자열
        """
        try:
            # FileExtractor를 사용하여 PDF 텍스트 추출
            # 순환 참조 방지를 위해 여기서 직접 import
            from common.file_extractor import FileExtractor
            
            extractor = FileExtractor()
            
            # 캐시 확인
            if old_file not in self._pdf_text_cache:
                print(f"    PDF 텍스트 추출 중 (기존 파일)...")
                self._pdf_text_cache[old_file] = extractor.extract_pdf_content(old_file)
            else:
                print(f"    PDF 텍스트 캐시 사용 (기존 파일)")
            old_text = self._pdf_text_cache[old_file]
            
            if new_file not in self._pdf_text_cache:
                print(f"    PDF 텍스트 추출 중 (새 파일)...")
                self._pdf_text_cache[new_file] = extractor.extract_pdf_content(new_file)
            else:
                print(f"    PDF 텍스트 캐시 사용 (새 파일)")
            new_text = self._pdf_text_cache[new_file]
            
            if not old_text and not new_text:
                # 텍스트 추출 실패 시 크기 비교로 fallback
                size_diff = os.path.getsize(new_file) - os.path.getsize(old_file)
                if size_diff > 0:
                    return f'PDF 파일 크기 증가: {os.path.getsize(old_file)} → {os.path.getsize(new_file)} bytes (+{size_diff})'
                elif size_diff < 0:
                    return f'PDF 파일 크기 감소: {os.path.getsize(old_file)} → {os.path.getsize(new_file)} bytes ({size_diff})'
                else:
                    return f'PDF 파일 내용 변경 (크기 동일, 텍스트 추출 실패)'
            
            if not old_text:
                return f'PDF 텍스트 추출 실패 (기존 파일), 새 파일: {len(new_text)}자'
            if not new_text:
                return f'PDF 텍스트 추출 실패 (새 파일), 기존 파일: {len(old_text)}자'
            
            # 텍스트를 줄 단위로 분리
            old_lines = old_text.splitlines()
            new_lines = new_text.splitlines()
            
            # 통계 계산
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=os.path.basename(old_file),
                tofile=os.path.basename(new_file),
                lineterm=''
            ))
            
            # 변경사항 통계
            added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
            removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
            
            summary = f'PDF 텍스트 변경: {removed}줄 삭제, {added}줄 추가'
            
            # 텍스트 길이 변화
            text_diff = len(new_text) - len(old_text)
            if text_diff > 0:
                summary += f' (텍스트 길이: {len(old_text)} → {len(new_text)}자, +{text_diff})'
            elif text_diff < 0:
                summary += f' (텍스트 길이: {len(old_text)} → {len(new_text)}자, {text_diff})'
            else:
                summary += f' (텍스트 길이 동일: {len(new_text)}자)'
            
            return summary
        except Exception as e:
            print(f"    ⚠ PDF diff 생성 실패: {e}")
            # fallback: 크기 비교
            try:
                size_diff = os.path.getsize(new_file) - os.path.getsize(old_file)
                if size_diff > 0:
                    return f'PDF 파일 크기 증가: {os.path.getsize(old_file)} → {os.path.getsize(new_file)} bytes (+{size_diff})'
                elif size_diff < 0:
                    return f'PDF 파일 크기 감소: {os.path.getsize(old_file)} → {os.path.getsize(new_file)} bytes ({size_diff})'
                else:
                    return f'PDF 파일 내용 변경 (크기 동일: {os.path.getsize(new_file)} bytes)'
            except:
                return f'PDF 파일 비교 실패: {e}'
    
    def _get_text_diff_summary(self, old_file: str, new_file: str) -> str:
        """
        텍스트 파일의 diff 요약 생성
        
        Args:
            old_file: 기존 파일 경로
            new_file: 새 파일 경로
            
        Returns:
            변경사항 요약 문자열
        """
        try:
            with open(old_file, 'r', encoding='utf-8', errors='ignore') as f:
                old_lines = f.readlines()
            with open(new_file, 'r', encoding='utf-8', errors='ignore') as f:
                new_lines = f.readlines()
            
            # 통계 계산
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=os.path.basename(old_file),
                tofile=os.path.basename(new_file),
                lineterm=''
            ))
            
            # 변경사항 통계
            added = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
            removed = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))
            
            summary = f'텍스트 변경: {removed}줄 삭제, {added}줄 추가'
            
            # 변경된 줄 수가 적으면 상세 정보 추가
            if len(diff) < 50:
                summary += f' (총 {len(diff)}줄 diff)'
            
            return summary
        except Exception as e:
            return f'텍스트 비교 실패: {e}'
    
    def get_unified_diff(self, old_file: str, new_file: str, context_lines: int = 3) -> List[str]:
        """
        Unified diff 형식으로 변경사항 반환
        
        Args:
            old_file: 기존 파일 경로
            new_file: 새 파일 경로
            context_lines: 컨텍스트 줄 수
            
        Returns:
            diff 라인 리스트
        """
        if not (os.path.exists(old_file) and os.path.exists(new_file)):
            return []
        
        try:
            # 텍스트 파일인 경우
            if self._is_text_file(old_file) and self._is_text_file(new_file):
                with open(old_file, 'r', encoding='utf-8', errors='ignore') as f:
                    old_lines = f.readlines()
                with open(new_file, 'r', encoding='utf-8', errors='ignore') as f:
                    new_lines = f.readlines()
                
                diff = list(difflib.unified_diff(
                    old_lines, new_lines,
                    fromfile=os.path.basename(old_file),
                    tofile=os.path.basename(new_file),
                    n=context_lines,
                    lineterm=''
                ))
                
                return diff
            
            # PDF 파일인 경우 텍스트 추출 후 비교
            elif self._is_pdf_file(old_file) and self._is_pdf_file(new_file):
                from common.file_extractor import FileExtractor
                extractor = FileExtractor()
                
                # 캐시 확인 (이미 추출된 경우 재사용)
                if old_file not in self._pdf_text_cache:
                    self._pdf_text_cache[old_file] = extractor.extract_pdf_content(old_file)
                old_text = self._pdf_text_cache[old_file]
                
                if new_file not in self._pdf_text_cache:
                    self._pdf_text_cache[new_file] = extractor.extract_pdf_content(new_file)
                new_text = self._pdf_text_cache[new_file]
                
                if not old_text or not new_text:
                    return []
                
                old_lines = old_text.splitlines()
                new_lines = new_text.splitlines()
                
                diff = list(difflib.unified_diff(
                    old_lines, new_lines,
                    fromfile=os.path.basename(old_file) + ' (PDF 텍스트)',
                    tofile=os.path.basename(new_file) + ' (PDF 텍스트)',
                    n=context_lines,
                    lineterm=''
                ))
                
                return diff
            
            else:
                return []
        except Exception as e:
            print(f"  ⚠ Unified diff 생성 실패: {e}")
            return []
    
    def _generate_html_diff(self, old_file: str, new_file: str, diff_lines: List[str], context_lines: int = 3) -> str:
        """
        Unified diff를 HTML 형식으로 변환
        
        Args:
            old_file: 기존 파일 경로
            new_file: 새 파일 경로
            diff_lines: unified diff 라인 리스트
            context_lines: 컨텍스트 줄 수
            
        Returns:
            HTML 형식의 diff 문자열
        """
        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>파일 비교 결과</title>
    <style>
        body {{
            font-family: 'Malgun Gothic', '맑은 고딕', Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .info {{
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            border-left: 4px solid #2196F3;
        }}
        .info p {{
            margin: 5px 0;
            color: #555;
        }}
        .diff-container {{
            border: 1px solid #ddd;
            border-radius: 5px;
            overflow-x: auto;
        }}
        .diff-line {{
            padding: 5px 10px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .diff-line.removed {{
            background-color: #ffebee;
            color: #c62828;
            border-left: 4px solid #f44336;
        }}
        .diff-line.added {{
            background-color: #e8f5e9;
            color: #2e7d32;
            border-left: 4px solid #4CAF50;
        }}
        .diff-line.context {{
            background-color: #fafafa;
            color: #666;
        }}
        .diff-line.header {{
            background-color: #e3f2fd;
            color: #1565c0;
            font-weight: bold;
            padding: 10px;
            border-bottom: 2px solid #2196F3;
        }}
        .line-number {{
            display: inline-block;
            width: 60px;
            text-align: right;
            padding-right: 10px;
            color: #999;
            user-select: none;
        }}
        .stats {{
            background-color: #fff3cd;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
            border-left: 4px solid #ffc107;
        }}
        .stats h3 {{
            margin-top: 0;
            color: #856404;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 파일 비교 결과</h1>
        <div class="info">
            <p><strong>생성 시간:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>기존 파일:</strong> {old_file}</p>
            <p><strong>새 파일:</strong> {new_file}</p>
        </div>
        <div class="diff-container">
"""
        
        # 통계 계산
        added_count = 0
        removed_count = 0
        
        for line in diff_lines:
            if line.startswith('---') or line.startswith('+++') or line.startswith('@@'):
                # 헤더 라인
                html += f'            <div class="diff-line header">{self._escape_html(line)}</div>\n'
            elif line.startswith('-') and not line.startswith('---'):
                # 삭제된 라인
                removed_count += 1
                html += f'            <div class="diff-line removed">{self._escape_html(line)}</div>\n'
            elif line.startswith('+') and not line.startswith('+++'):
                # 추가된 라인
                added_count += 1
                html += f'            <div class="diff-line added">{self._escape_html(line)}</div>\n'
            else:
                # 컨텍스트 라인
                html += f'            <div class="diff-line context">{self._escape_html(line)}</div>\n'
        
        html += """        </div>
        <div class="stats">
            <h3>📊 변경 통계</h3>
            <p><strong>추가된 줄:</strong> <span style="color: #2e7d32;">{}</span></p>
            <p><strong>삭제된 줄:</strong> <span style="color: #c62828;">{}</span></p>
        </div>
    </div>
</body>
</html>""".format(added_count, removed_count)
        
        return html
    
    def _escape_html(self, text: str) -> str:
        """HTML 특수 문자 이스케이프"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#x27;'))
    
    def save_diff_to_file(self, old_file: str, new_file: str, output_path: str, context_lines: int = 3, save_html: bool = True) -> bool:
        """
        diff 결과를 파일로 저장 (텍스트 및 HTML 형식)
        
        Args:
            old_file: 기존 파일 경로
            new_file: 새 파일 경로
            output_path: 출력 파일 경로 (.diff 확장자)
            context_lines: 컨텍스트 줄 수
            save_html: HTML 형식도 함께 저장할지 여부
            
        Returns:
            저장 성공 여부
        """
        diff_lines = self.get_unified_diff(old_file, new_file, context_lines)
        if not diff_lines:
            return False
        
        try:
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 텍스트 diff 저장
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"# 파일 비교 결과\n")
                f.write(f"# 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 기존 파일: {old_file}\n")
                f.write(f"# 새 파일: {new_file}\n")
                f.write(f"# {'=' * 70}\n\n")
                f.write('\n'.join(diff_lines))
            
            # HTML diff 저장 (선택사항)
            if save_html:
                html_path = str(output_path).replace('.diff', '.html')
                html_content = self._generate_html_diff(old_file, new_file, diff_lines, context_lines)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
            
            return True
        except Exception as e:
            print(f"  ⚠ Diff 파일 저장 실패: {e}")
            return False
    
    def compare_and_report(self, new_file: str, old_file: str, save_diff: bool = True) -> Dict:
        """
        파일 비교 및 리포트 생성
        
        Args:
            new_file: 새 파일 경로
            old_file: 기존 파일 경로
            save_diff: diff 파일 저장 여부
            
        Returns:
            비교 결과 딕셔너리 (compare_files 결과 + diff_file 경로)
        """
        result = self.compare_files(new_file, old_file)
        
        # diff 파일 저장
        if save_diff and result['changed'] and result['new_exists'] and result['old_exists']:
            # 텍스트 파일 또는 PDF 파일인 경우 diff 저장
            is_text = self._is_text_file(new_file) and self._is_text_file(old_file)
            is_pdf = self._is_pdf_file(new_file) and self._is_pdf_file(old_file)
            
            if is_text or is_pdf:
                # diff 파일 경로 생성
                old_name = Path(old_file).stem
                new_name = Path(new_file).stem
                diff_dir = self.base_dir / "diffs"
                diff_dir.mkdir(parents=True, exist_ok=True)
                diff_file = diff_dir / f"{old_name}_vs_{new_name}.diff"
                
                if self.save_diff_to_file(old_file, new_file, str(diff_file), save_html=True):
                    result['diff_file'] = str(diff_file)
                    html_file = diff_file.with_suffix('.html')
                    print(f"  ✓ Diff 파일 저장: {diff_file}")
                    print(f"  ✓ HTML Diff 파일 저장: {html_file}")
        
        return result

