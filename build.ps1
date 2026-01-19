# GFX Sync 빌드 스크립트
# 사용법: .\build.ps1

Write-Host "=== GFX Sync 빌드 ===" -ForegroundColor Cyan

# 1. PyInstaller 설치 확인
Write-Host "`n[1/3] PyInstaller 확인..." -ForegroundColor Yellow
$pyinstaller = pip show pyinstaller 2>$null
if (-not $pyinstaller) {
    Write-Host "PyInstaller 설치 중..."
    pip install pyinstaller --quiet
}

# 2. 의존성 설치
Write-Host "`n[2/3] 의존성 설치..." -ForegroundColor Yellow
pip install -r requirements.txt --quiet

# 3. 빌드
Write-Host "`n[3/3] EXE 빌드 중..." -ForegroundColor Yellow
pyinstaller build.spec --noconfirm

# 결과 확인
$exePath = "dist\GFX_Sync.exe"
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length / 1MB
    Write-Host "`n=== 빌드 완료 ===" -ForegroundColor Green
    Write-Host "출력: $exePath"
    Write-Host "크기: $([math]::Round($size, 2)) MB"
    Write-Host "`n실행: .\dist\GFX_Sync.exe"
} else {
    Write-Host "`n빌드 실패!" -ForegroundColor Red
    exit 1
}
