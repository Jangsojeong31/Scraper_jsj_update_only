# 스크래퍼 진행 상태 모니터링 스크립트

Write-Host "`n=== 검사업무 스크래퍼 진행 상태 모니터링 ===" -ForegroundColor Cyan
Write-Host "스크래퍼가 실행 중입니다. 진행 상태를 주기적으로 확인합니다...`n" -ForegroundColor Yellow

$resultFile = "inspection_results.json"
$csvFile = "inspection_results.csv"
$checkCount = 0
$maxChecks = 120  # 최대 20분 (10초 간격)

while ($checkCount -lt $maxChecks) {
    $checkCount++
    $elapsed = [math]::Round($checkCount * 10 / 60, 1)
    
    Write-Host "[$checkCount] 진행 상태 확인 중... (경과 시간: ${elapsed}분)" -ForegroundColor Gray
    
    if (Test-Path $resultFile) {
        Write-Host "`n=== 결과 파일 생성 완료! ===" -ForegroundColor Green
        
        try {
            $content = Get-Content $resultFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $recordCount = $content.Count
            
            Write-Host "수집된 레코드 수: $recordCount 개" -ForegroundColor Cyan
            Write-Host "`n수집된 데이터 샘플:" -ForegroundColor Yellow
            $content | Select-Object -First 5 | Format-Table -AutoSize
            
            if (Test-Path $csvFile) {
                $csvSize = (Get-Item $csvFile).Length
                Write-Host "`nCSV 파일 크기: $([math]::Round($csvSize/1KB, 2)) KB" -ForegroundColor Cyan
            }
            
            Write-Host "`n=== 스크래핑 완료 ===" -ForegroundColor Green
            break
        }
        catch {
            Write-Host "결과 파일을 읽는 중 오류 발생: $_" -ForegroundColor Red
        }
    }
    else {
        # 프로세스가 실행 중인지 확인
        $pythonProcess = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*fss_scraper*" }
        if (-not $pythonProcess) {
            Write-Host "`n경고: Python 프로세스를 찾을 수 없습니다." -ForegroundColor Yellow
        }
    }
    
    if ($checkCount -lt $maxChecks) {
        Start-Sleep -Seconds 10
    }
}

if ($checkCount -ge $maxChecks) {
    Write-Host "`n=== 모니터링 시간 초과 ===" -ForegroundColor Yellow
    Write-Host "20분 동안 결과 파일이 생성되지 않았습니다." -ForegroundColor Yellow
    Write-Host "스크래퍼가 계속 실행 중일 수 있습니다. 수동으로 확인해주세요." -ForegroundColor Yellow
}










