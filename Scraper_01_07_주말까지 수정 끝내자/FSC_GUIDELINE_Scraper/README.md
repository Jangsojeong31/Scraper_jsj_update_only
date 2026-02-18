# 금융위원회 행정지도 스크래퍼

금융위원회의 행정지도 데이터를 추출하는 Python 스크래퍼입니다.

## 개요

이 스크래퍼는 금융위원회 웹사이트에서 행정지도 관련 정보를 수집합니다:

- **금융위원회 행정지도** (https://better.fsc.go.kr/fsc_new/status/adminMap/OpertnList.do?stNo=11&muNo=145&muGpNo=60)

## 디렉토리 구조

```
FSC_GUIDELINE_Scraper/
├── input/              # 입력 파일 디렉토리
├── output/             # 출력 파일 디렉토리
│   ├── csv/           # CSV 형식 결과 파일
│   ├── json/          # JSON 형식 결과 파일
│   ├── downloads/     # 다운로드된 파일
│   └── debug/         # 디버그 파일
├── fsc_guideline_scraper.py  # 메인 스크래퍼 파일
└── README.md          # 이 파일
```

## 사용 방법

### 1. 필수 패키지 설치

```bash
pip install -r ../../requirements.txt
```

### 2. 스크래퍼 실행

```bash
# 기본 실행
python fsc_guideline_scraper.py

# 대기 시간 조정 (기본값: 1.0초)
python fsc_guideline_scraper.py --delay 2.0
```

## 추출 필드

스크래퍼는 다음 8개 필드를 추출합니다:

1. **출처** - 데이터 출처 (금융위원회_행정지도)
2. **제목** - 문서 제목
3. **시행일** - 시행일자
4. **내용** - 본문 내용
5. **담당부서** - 담당 부서
6. **링크** - 상세 페이지 URL
7. **첨부파일링크** - 첨부파일 다운로드 링크
8. **첨부파일명** - 첨부파일 이름

## 결과 파일

스크래퍼 실행 후 다음 파일이 생성됩니다:
- `output/json/fsc_guideline_results.json`: JSON 형식의 결과 파일
- `output/csv/fsc_guideline_results.csv`: CSV 형식의 결과 파일
- `output/downloads/`: 다운로드된 파일
- `output/debug/`: 디버그용 HTML 파일

## 주의사항

- 스크래핑 시 서버에 과도한 부하를 주지 않도록 적절한 대기 시간이 설정되어 있습니다.
- 웹사이트 구조가 변경될 경우 스크래퍼 수정이 필요할 수 있습니다.
- 네트워크 연결이 안정적인 환경에서 실행하는 것을 권장합니다.
- JavaScript로 동적 로드되는 페이지이므로 Selenium을 사용합니다 (폐쇄망 호환).

