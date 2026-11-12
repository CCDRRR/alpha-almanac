# WQB 知識管家：一鍵安裝（Windows PowerShell 5.1 / 7 皆可）
# 用法：powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# 1. 找 Python 3.11 以上
Step "尋找 Python 3.11+"
$py = $null
foreach ($cand in @(@("py", "-3.13"), @("py", "-3.12"), @("py", "-3.11"), @("py", "-3"), @("python"))) {
    try {
        $exe = $cand[0]; $rest = @($cand | Select-Object -Skip 1)
        $ver = & $exe @rest -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver -and [version]$ver -ge [version]"3.11") { $py = $cand; break }
    } catch { }
}
if (-not $py) {
    Write-Host "找不到 Python 3.11 以上。請到 https://www.python.org/downloads/ 安裝（勾選 Add to PATH）後再執行一次。" -ForegroundColor Red
    exit 1
}
Write-Host "使用：$($py -join ' ')（Python $ver）"

# 2. 建立虛擬環境
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Step "建立虛擬環境 .venv"
    $exe = $py[0]; $rest = @($py | Select-Object -Skip 1)
    & $exe @rest -m venv .venv
}
$vpy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# 3. 安裝套件（torch 用 CPU 版，比 GPU 版小很多）
Step "安裝套件（第一次約 5–10 分鐘）"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu --quiet
& $vpy -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "套件安裝失敗，請把上面的錯誤訊息貼到論壇問我。" -ForegroundColor Red; exit 1 }

# 4. 帳密設定檔
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已建立 .env，請填入你的 WQB 帳號密碼（只存在你的電腦，不會上傳）。"
}

Step "安裝完成！接下來："
Write-Host @"
  1. 編輯 .env，填入 WQ_ACCOUNT / WQ_PASSWORD：
       notepad .env
  2. 建立知識庫（會打開瀏覽器掃臉；之後爬資料＋建索引約 30 分鐘）：
       .venv\Scripts\python -m wqbka.bootstrap
  3. 接上 Claude Desktop（自動找設定檔並加入，原本的設定會保留並備份）：
       .venv\Scripts\python -m wqbka.desktop_config
     完成後從系統匣「Quit」Claude Desktop 再重開。
"@
