# YARA Python Environment Setup Script
Write-Host "YARA Python Environment Setup" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Green

$ProjectDir = "D:\2.1 PyCharm\1 project\Create"
Write-Host "Project Directory: $ProjectDir" -ForegroundColor Yellow

# Check YARA Python installation
Write-Host "`nChecking YARA Python installation..." -ForegroundColor Yellow
$yaraCheck = & "$ProjectDir\.venv\Scripts\python.exe" -c "import yara; print('YARA OK')" 2>$null
if ($yaraCheck -eq "YARA OK") {
    Write-Host "YARA Python is installed" -ForegroundColor Green
} else {
    Write-Host "YARA Python is not installed. Please run: pip install yara-python" -ForegroundColor Red
    exit 1
}

# Set environment variables
Write-Host "`nSetting environment variables..." -ForegroundColor Yellow

$EnvVars = @{
    "ENABLE_YARA_SCAN" = "true"
    "YARA_RULES_PATH" = "$ProjectDir\yara\rules\rules.yar"
    "YARA_LOG_LEVEL" = "INFO"
    "YARA_SCAN_TIMEOUT" = "30"
    "YARA_OUTPUT_DIR" = "$ProjectDir\yara\output"
    "YARA_ALLOWED_EXTENSIONS" = ".exe,.dll,.ps1,.bat,.cmd,.py,.js,.vbs,.jar,.zip,.rar"
    "YARA_EXCLUDE_DIRS" = "node_modules,.git,__pycache__,.venv,venv"
    "YARA_MAX_FILE_SIZE" = "100"
}

foreach ($VarName in $EnvVars.Keys) {
    $VarValue = $EnvVars[$VarName]
    [Environment]::SetEnvironmentVariable($VarName, $VarValue, "User")
    Set-Item -Path "Env:$VarName" -Value $VarValue
    Write-Host "  Set $VarName = $VarValue" -ForegroundColor Green
}

# Create required directories
Write-Host "`nCreating required directories..." -ForegroundColor Yellow

$RequiredDirs = @(
    "$ProjectDir\yara\rules",
    "$ProjectDir\yara\output"
)

foreach ($Dir in $RequiredDirs) {
    if (Test-Path $Dir) {
        Write-Host "  Directory exists: $Dir" -ForegroundColor Green
    } else {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        Write-Host "  Created directory: $Dir" -ForegroundColor Green
    }
}

# Test YARA configuration
Write-Host "`nTesting YARA configuration..." -ForegroundColor Yellow

$testScript = @"
import os
import sys
sys.path.insert(0, '$ProjectDir')
os.chdir('$ProjectDir')
try:
    from yara_scanner import YARAFileScanner
    scanner = YARAFileScanner()
    if scanner.enabled and scanner.rules:
        print('YARA configuration test passed')
    else:
        print('YARA configuration test failed')
except Exception as e:
    print(f'YARA configuration test error: {e}')
"@

$TestResult = & "$ProjectDir\.venv\Scripts\python.exe" -c $testScript 2>$null

if ($TestResult -like "*passed*") {
    Write-Host "  YARA configuration test passed" -ForegroundColor Green
} else {
    Write-Host "  YARA configuration test failed: $TestResult" -ForegroundColor Red
}

Write-Host "`nConfiguration Summary:" -ForegroundColor Cyan
Write-Host "  YARA Scan: Enabled" -ForegroundColor White
Write-Host "  Rules File: $ProjectDir\yara\rules\rules.yar" -ForegroundColor White
Write-Host "  Output Directory: $ProjectDir\yara\output" -ForegroundColor White
Write-Host "  Log Level: INFO" -ForegroundColor White
Write-Host "  Scan Timeout: 30 seconds" -ForegroundColor White
Write-Host "  Max File Size: 100MB" -ForegroundColor White

Write-Host "`nUsage Examples:" -ForegroundColor Cyan
Write-Host "  # Run YARA scanner" -ForegroundColor White
Write-Host "  python yara_scanner.py" -ForegroundColor Gray
Write-Host "`n  # Run test script" -ForegroundColor White
Write-Host "  python yara_test.py" -ForegroundColor Gray

Write-Host "`nYARA Python environment setup completed!" -ForegroundColor Green
Write-Host "Tip: Restart PowerShell or IDE to ensure environment variables take effect" -ForegroundColor Yellow
