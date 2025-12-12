#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""스크래퍼 진행 상태 모니터링 스크립트"""

import time
import json
import os
from pathlib import Path

def monitor_progress():
    print("\n=== 검사업무 스크래퍼 진행 상태 모니터링 ===")
    print("스크래퍼가 실행 중입니다. 진행 상태를 주기적으로 확인합니다...\n")
    
    result_file = Path("inspection_results.json")
    csv_file = Path("inspection_results.csv")
    check_count = 0
    max_checks = 120  # 최대 20분 (10초 간격)
    
    while check_count < max_checks:
        check_count += 1
        elapsed = round(check_count * 10 / 60, 1)
        
        print(f"[{check_count}] 진행 상태 확인 중... (경과 시간: {elapsed}분)")
        
        if result_file.exists():
            print("\n=== 결과 파일 생성 완료! ===")
            
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                
                record_count = len(content)
                print(f"수집된 레코드 수: {record_count} 개")
                print("\n수집된 데이터 샘플:")
                for i, record in enumerate(content[:5], 1):
                    print(f"  {i}. 구분: {record.get('구분', '-')}, 제목: {record.get('제목', '-')[:50]}...")
                
                if csv_file.exists():
                    csv_size = csv_file.stat().st_size
                    print(f"\nCSV 파일 크기: {round(csv_size/1024, 2)} KB")
                
                print("\n=== 스크래핑 완료 ===")
                break
            except Exception as e:
                print(f"결과 파일을 읽는 중 오류 발생: {e}")
        else:
            print("  → 아직 결과 파일이 생성되지 않았습니다. 계속 대기 중...")
        
        if check_count < max_checks:
            time.sleep(10)
    
    if check_count >= max_checks:
        print("\n=== 모니터링 시간 초과 ===")
        print("20분 동안 결과 파일이 생성되지 않았습니다.")
        print("스크래퍼가 계속 실행 중일 수 있습니다. 수동으로 확인해주세요.")

if __name__ == "__main__":
    monitor_progress()








