# burst_test.ps1
# Fires 10 concurrent upload + process requests against the running stack.
# Run this from inside Legacy-Document-Digitizer/ (so data\clean.pdf resolves).
# Uses Start-Job (built into PowerShell 5.1+) instead of Start-ThreadJob,
# which requires a module not present by default on most Windows machines.

$API_BASE = "http://localhost:8081/api/invoices"
$PDF_PATH = "data\clean.pdf"
$COUNT = 10

if (-not (Test-Path $PDF_PATH)) {
    Write-Host "ERROR: $PDF_PATH not found. Run this from the Legacy-Document-Digitizer folder." -ForegroundColor Red
    exit 1
}

$PDF_FULL_PATH = (Resolve-Path $PDF_PATH).Path

Write-Host "Starting burst test: $COUNT concurrent invoices..." -ForegroundColor Cyan
$startTime = Get-Date

# Each parallel job gets its OWN copy of the PDF. -InFile opens the file
# with an exclusive lock, so 10 jobs sharing one path collide instantly
# when fired within milliseconds of each other (this is what caused the
# "being used by another process" errors).
$tempDir = Join-Path $env:TEMP "burst_test_pdfs"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$pdfCopies = 1..$COUNT | ForEach-Object {
    $copyPath = Join-Path $tempDir "clean_$_.pdf"
    Copy-Item -Path $PDF_FULL_PATH -Destination $copyPath -Force
    $copyPath
}

# Step 1: fire all 10 "request-upload" calls in parallel using background jobs
$jobs = 1..$COUNT | ForEach-Object {
    $i = $_
    Start-Job -ScriptBlock {
        param($apiBase, $pdfPath, $index)
        try {
            $response = Invoke-RestMethod -Method POST -Uri "$apiBase/request-upload" `
                -ContentType "application/json" -Body '{"filename": "clean.pdf"}'

            Invoke-RestMethod -Method PUT -Uri $response.uploadUrl -InFile $pdfPath `
                -Headers @{"x-ms-blob-type"="BlockBlob"} -ContentType "application/pdf"

            Invoke-RestMethod -Method POST -Uri "$apiBase/$($response.id)/process" | Out-Null

            return @{ index = $index; doc_id = $response.id; ok = $true }
        } catch {
            return @{ index = $index; doc_id = $null; ok = $false; error = $_.Exception.Message }
        }
    } -ArgumentList $API_BASE, $pdfCopies[$i - 1], $i
}

Write-Host "Waiting for all $COUNT upload+trigger calls to finish..." -ForegroundColor Cyan
$results = $jobs | Wait-Job | Receive-Job
$jobs | Remove-Job

$triggerElapsed = (Get-Date) - $startTime
$triggerSeconds = [math]::Round($triggerElapsed.TotalSeconds, 1)
Write-Host "All triggers fired in $triggerSeconds seconds" -ForegroundColor Green
Write-Host ""

$docIds = @()
foreach ($r in ($results | Sort-Object index)) {
    if ($r.ok) {
        Write-Host "  [$($r.index)] doc_id=$($r.doc_id)" -ForegroundColor Gray
        $docIds += $r.doc_id
    } else {
        Write-Host "  [$($r.index)] FAILED: $($r.error)" -ForegroundColor Red
    }
}

if ($docIds.Count -eq 0) {
    Write-Host ""
    Write-Host "No invoices were triggered successfully. Stopping here." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Triggered $($docIds.Count) of $COUNT invoices. Now polling for completion..." -ForegroundColor Cyan
Write-Host "(Press Ctrl+C to stop polling early. The worker keeps running in Docker either way.)"
Write-Host ""

# Step 2: poll Postgres-backed status until all are done or timeout
$idList = ($docIds | ForEach-Object { "'$_'" }) -join ","
$timeout = 600
$pollStart = Get-Date

while ($true) {
    $elapsed = ((Get-Date) - $pollStart).TotalSeconds
    if ($elapsed -gt $timeout) {
        Write-Host "Timed out after $timeout seconds. Check docker logs manually." -ForegroundColor Yellow
        break
    }

    $query = "SELECT status, COUNT(*) FROM invoices WHERE doc_id IN ($idList) GROUP BY status;"
    $statusOutput = docker exec sap-postgres psql -U admin -d sap_invoices -t -c $query

    $statusText = ($statusOutput -join " ")
    $pendingCount = ([regex]::Matches($statusText, "PENDING|PROCESSING|RATE_LIMITED")).Count
    $elapsedRounded = [math]::Round($elapsed)
    Write-Host "[$elapsedRounded s] $statusText" -ForegroundColor DarkGray

    if ($pendingCount -eq 0 -and $statusText.Trim().Length -gt 0) {
        break
    }

    Start-Sleep -Seconds 5
}

Write-Host ""
Write-Host "=== FINAL RESULTS ===" -ForegroundColor Cyan
docker exec sap-postgres psql -U admin -d sap_invoices -c "SELECT doc_id, status FROM invoices WHERE doc_id IN ($idList) ORDER BY created_at;"

$totalElapsed = (Get-Date) - $startTime
$totalSeconds = [math]::Round($totalElapsed.TotalSeconds, 1)
Write-Host ""
Write-Host "Total wall-clock time: $totalSeconds seconds for $COUNT invoices" -ForegroundColor Green