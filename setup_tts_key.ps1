# setup_tts_key.ps1 — OpenAI API 키를 화면에 보이지 않게 입력받아 로컬 .env 에만 저장한다 (10-19, 시연 음성 녹음용).
# 실행:  & .\setup_tts_key.ps1   (저장소 루트). 키는 채팅·로그·커밋 어디에도 남지 않는다 — .env 는 git 제외.
$ErrorActionPreference = "Stop"
$envPath = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envPath)) { New-Item -ItemType File -Path $envPath | Out-Null }

$sec = Read-Host -AsSecureString "OpenAI API 키를 붙여 넣고 Enter (입력 글자는 보이지 않습니다)"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$key = ($key -replace '[^\x21-\x7E]', '')          # 붙여넣기에 섞인 공백·제어문자 제거 (Pi 토큰 사고와 같은 교훈)

if ($key.Length -lt 20 -or -not $key.StartsWith("sk-")) {
  Write-Host ("형식이 아닌 것 같습니다 — 'sk-' 로 시작해야 합니다. 받은 길이: {0}. 저장하지 않았습니다." -f $key.Length) -ForegroundColor Yellow
  exit 1
}

$lines = @(Get-Content -Path $envPath -Encoding UTF8) | Where-Object { $_ -notmatch '^(OPENAI_API_KEY|TTS_PROVIDER)=' }
$lines += "TTS_PROVIDER=openai"
$lines += "OPENAI_API_KEY=$key"
[IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
$key = $null
Write-Host ("저장됨: .env 에 OPENAI_API_KEY (길이 {0}자, 'sk-' 로 시작). 이 창은 닫아도 됩니다." -f ($lines[-1].Length - 15)) -ForegroundColor Green
