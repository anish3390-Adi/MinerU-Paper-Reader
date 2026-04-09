$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Require-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command: $Name"
    }
}

Write-Host "[1/3] Checking runtime..."
Require-Command python
Require-Command node
Require-Command corepack

$translatorDir = Join-Path $projectRoot "external\md-translator"
$standaloneEntry = Join-Path $translatorDir ".next\standalone\server.js"

if (-not (Test-Path -LiteralPath $translatorDir)) {
    throw "md-translator directory not found: $translatorDir"
}

if (-not (Test-Path -LiteralPath $standaloneEntry)) {
    Write-Host "[2/3] Building md-translator..."
    Push-Location $translatorDir
    try {
        $env:LOCAL_API_SERVER = "true"
        corepack yarn install
        corepack yarn build
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[2/3] md-translator already built. Skipping build."
}

Write-Host "[3/3] Starting Streamlit..."
python -m streamlit run app.py --server.headless=true
