import time
import subprocess
import sys

print("=" * 60)
print("검사업무 스크래핑 시작 (3개 항목)")
print("=" * 60)

start_time = time.time()

try:
    result = subprocess.run(
        [sys.executable, "run_pipeline.py", "--limit", "3"],
        text=True,
        capture_output=False
    )
    exit_code = result.returncode
except KeyboardInterrupt:
    print("\n[중단됨] 사용자가 실행을 취소했습니다.")
    exit_code = 1
except Exception as e:
    print(f"\n[오류] 실행 중 오류 발생: {e}")
    exit_code = 1

end_time = time.time()
elapsed_time = end_time - start_time

print("\n" + "=" * 60)
print(f"총 경과 시간: {elapsed_time:.2f}초 ({elapsed_time/60:.2f}분)")
print("=" * 60)

sys.exit(exit_code)

