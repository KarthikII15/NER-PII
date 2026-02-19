<#
.SYNOPSIS
    Pre-flight security check for Secure Doc AI deployment.
    Must ALL PASS before going live.
#>

$pass = $true

# Check 1: BitLocker
Write-Host "CHECK 1: BitLocker status..."
$bitlocker = manage-bde -status C: 2>&1
if ($bitlocker -match "Protection On") {
    Write-Host "  [PASS] BitLocker Protection ON"
}
else {
    Write-Host "  [WARN] BitLocker not enabled. Required before Go-Live."
    # Not hard-fail in Phase 1, becomes FAIL in Phase 5
}

# Check 2: WSL2 Memory Cap
Write-Host "CHECK 2: WSL2 .wslconfig..."
$wslcfg = "$env:USERPROFILE\.wslconfig"
if (Test-Path $wslcfg) {
    $content = Get-Content $wslcfg -Raw
    if ($content -match "memory=8GB") {
        Write-Host "  [PASS] .wslconfig memory cap found"
    }
    else {
        Write-Host "  [FAIL] .wslconfig does not cap memory at 8GB"
        $pass = $false
    }
}
else {
    Write-Host "  [FAIL] .wslconfig not found at $wslcfg"
    $pass = $false
}

# Check 3: .env not in Git
Write-Host "CHECK 3: .env not tracked by Git..."
# Use git root to resolve path correctly when run from a subdirectory
$gitRoot = & git rev-parse --show-toplevel
$gitRoot = $gitRoot.Trim()
$envAbsPath = (Resolve-Path ".env" -ErrorAction SilentlyContinue)
if ($null -ne $envAbsPath) {
    $envRelPath = $envAbsPath.Path.Substring($gitRoot.Length + 1) -replace "\\", "/"
    $rawTracked = & git -C $gitRoot ls-files $envRelPath
    $tracked = if ($null -ne $rawTracked) { "$rawTracked".Trim() } else { "" }
}
else {
    $tracked = ""
}
if ($tracked -eq "") {
    Write-Host "  [PASS] .env is NOT tracked by Git"
}
else {
    Write-Host "  [FAIL] .env IS tracked by Git. Run: git rm --cached $envRelPath"
    $pass = $false
}

# Check 4: API_KEY not default
Write-Host "CHECK 4: API_KEY not default..."
if (Test-Path ".env") {
    $envContent = Get-Content ".env" -Raw
    if ($envContent -match "API_KEY=CHANGE_ME") {
        Write-Host "  [FAIL] API_KEY is still the default value"
        $pass = $false
    }
    else {
        Write-Host "  [PASS] API_KEY appears to be customised"
    }
}
else {
    Write-Host "  [FAIL] .env file not found"
    $pass = $false
}

# Check 5: Container UID
Write-Host "CHECK 5: Container runs as non-root..."
$rawUid = & docker exec pii_processor id -u 2>&1
$uid = if ($null -ne $rawUid) { "$rawUid".Trim() } else { "" }
if ($uid -eq "1001") {
    Write-Host "  [PASS] Container running as UID 1001"
}
else {
    Write-Host "  [FAIL] Container UID is '$uid' (expected 1001)"
    $pass = $false
}

# Summary
Write-Host ""
if ($pass) {
    Write-Host "[ALL CHECKS PASSED] Safe to proceed." -ForegroundColor Green
}
else {
    Write-Host "[CHECKS FAILED] Fix the above issues before continuing." -ForegroundColor Red
    exit 1
}
