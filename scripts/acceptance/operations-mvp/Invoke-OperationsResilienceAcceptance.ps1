[CmdletBinding()]
param(
    [string]$JavaBaseUrl = 'http://127.0.0.1:8080',
    [string]$AgentBaseUrl = 'http://127.0.0.1:8090',
    [Parameter(Mandatory = $true)]
    [string]$JavaLogPath,
    [Parameter(Mandatory = $true)]
    [string]$AgentLogPath,
    [Parameter(Mandatory = $true)]
    [string]$AgentRestartScript,
    [string]$OutputRoot,
    [int]$StreamTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $repositoryRoot = Resolve-Path (Join-Path $scriptRoot '../../..')
    $OutputRoot = Join-Path $repositoryRoot ".local-acceptance/operations-resilience/$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
foreach ($path in @($JavaLogPath, $AgentLogPath, $AgentRestartScript)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "必需文件不存在：$path" }
}
$javaLogStart = @(Get-Content -LiteralPath $JavaLogPath).Count
$agentLogStart = @(Get-Content -LiteralPath $AgentLogPath).Count

function Invoke-Json([string]$Method, [string]$Uri, [object]$Body, [string]$Name) {
    $parameters = @{ Method = $Method; Uri = $Uri; TimeoutSec = 60; ContentType = 'application/json; charset=utf-8' }
    if ($null -ne $Body) { $parameters.Body = $Body | ConvertTo-Json -Depth 50 -Compress }
    try { $response = Invoke-WebRequest @parameters }
    catch {
        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'NO_RESPONSE' }
        $detail = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
        "$Method $Uri`nHTTP=$status`n$detail" | Set-Content -LiteralPath (Join-Path $OutputRoot "$Name.error.txt") -Encoding UTF8
        throw "真实接口调用失败：$Name，HTTP=$status"
    }
    $response.Content | Set-Content -LiteralPath (Join-Path $OutputRoot "$Name.response.json") -Encoding UTF8
    $envelope = $response.Content | ConvertFrom-Json -Depth 100
    if ($envelope.code -ne 'SUCCESS' -or $null -eq $envelope.data) { throw "Java API 非成功响应：$Name" }
    return $envelope.data
}

function New-Conversation([string]$Name) {
    return Invoke-Json 'POST' "$JavaBaseUrl/api/operations/conversations" @{} $Name
}

function Submit([string]$ConversationId, [string]$Message, [string]$ClientRequestId, [string]$Name) {
    return Invoke-Json 'POST' "$JavaBaseUrl/api/operations/conversations/$ConversationId/messages" @{
        message = $Message
        clientRequestId = $ClientRequestId
    } $Name
}

function Read-Sequences([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return @() }
    $events = @()
    foreach ($block in @((Get-Content -Raw -LiteralPath $Path) -split "(?:`r?`n){2,}")) {
        $data = @($block -split "`r?`n" | Where-Object { $_ -like 'data:*' })
        if ($data.Count -eq 0) { continue }
        $events += (($data | ForEach-Object { $_.Substring(5).TrimStart() }) -join "`n") | ConvertFrom-Json -Depth 100
    }
    return $events
}

function Complete-Stream([string]$RunId, [string]$Name, [int]$AfterSequence = 0) {
    $path = Join-Path $OutputRoot "$Name.sse"
    & curl.exe --silent --show-error --fail-with-body --no-buffer --max-time $StreamTimeoutSeconds `
        -H 'Accept: text/event-stream' -H "Last-Event-ID: $AfterSequence" `
        "$JavaBaseUrl/api/operations/runs/$RunId/events?afterSequence=$AfterSequence" --output $path
    if ($LASTEXITCODE -ne 0) { throw "SSE 调用失败：$Name，exit=$LASTEXITCODE" }
    return $path
}

$conversation = New-Conversation 'create-resilience-conversation'
$conversationId = [string]$conversation.conversationId
$requestId = [Guid]::NewGuid().ToString()
$message = '收集一下今天有哪些 AI 相关的热点话题，给出最热的前 10 条。'
$first = Submit $conversationId $message $requestId 'idempotency-first'
$second = Submit $conversationId $message $requestId 'idempotency-second'
if ($first.runId -ne $second.runId -or $first.agentRunId -ne $second.agentRunId) {
    throw '相同 clientRequestId 返回了不同 run'
}

$partialPath = Join-Path $OutputRoot 'reconnect-partial.sse'
& curl.exe --silent --show-error --no-buffer --max-time 2 -H 'Accept: text/event-stream' `
    "$JavaBaseUrl/api/operations/runs/$($first.runId)/events?afterSequence=0" --output $partialPath
$partialExit = $LASTEXITCODE
if ($partialExit -notin @(0, 28)) { throw "主动断开 SSE 得到非预期退出码：$partialExit" }
$partialEvents = @(Read-Sequences $partialPath)
if ($partialEvents.Count -eq 0) { throw '主动断开前没有收到任何 SSE 事件' }
$cursor = [int](($partialEvents | Measure-Object sequence -Maximum).Maximum)
$remainingPath = Complete-Stream ([string]$first.runId) 'reconnect-remaining' $cursor
$remainingEvents = @(Read-Sequences $remainingPath)
if (@($remainingEvents | Where-Object { [int]$_.sequence -le $cursor }).Count -gt 0) {
    throw 'SSE 重连返回了不大于游标的重复事件'
}
$combinedPath = Join-Path $OutputRoot 'reconnect-combined.sse'
((Get-Content -Raw $partialPath) + (Get-Content -Raw $remainingPath)) | Set-Content -LiteralPath $combinedPath -Encoding UTF8
& (Join-Path $scriptRoot 'Assert-OperationsResult.ps1') -Kind Research -SsePath $combinedPath
if ($LASTEXITCODE -ne 0) { throw '断线续读后的研究结果不满足要求' }

& $AgentRestartScript
if ($LASTEXITCODE -ne 0) { throw "Agent 重启脚本失败：exit=$LASTEXITCODE" }
$healthDeadline = (Get-Date).AddSeconds(60)
do {
    try {
        $agentReady = (Invoke-WebRequest -Uri "$AgentBaseUrl/health/ready" -TimeoutSec 5).StatusCode -eq 200
    }
    catch { $agentReady = $false }
    if (-not $agentReady) { Start-Sleep -Milliseconds 500 }
} while (-not $agentReady -and (Get-Date) -lt $healthDeadline)
if (-not $agentReady) { throw 'Agent 重启后 Java 健康探测未恢复' }

$rewrite = Submit $conversationId '把这些热点写成公众号周更推文。' ([Guid]::NewGuid().ToString()) 'restart-rewrite'
$rewriteSse = Complete-Stream ([string]$rewrite.runId) 'restart-rewrite'
& (Join-Path $scriptRoot 'Assert-OperationsResult.ps1') -Kind Wechat -SsePath $rewriteSse
if ($LASTEXITCODE -ne 0) { throw 'Agent 重启后公众号续写失败' }

$cancelConversation = New-Conversation 'create-cancel-conversation'
$cancelRun = Submit ([string]$cancelConversation.conversationId) $message ([Guid]::NewGuid().ToString()) 'cancel-submit'
$cancelled = Invoke-Json 'POST' "$JavaBaseUrl/api/operations/runs/$($cancelRun.runId)/cancel" $null 'cancel-result'
$cancelDeadline = (Get-Date).AddSeconds(20)
$cancelPoll = 0
while ($cancelled.status -ne 'cancelled' -and (Get-Date) -lt $cancelDeadline) {
    if ($cancelled.status -notin @('queued', 'running')) {
        throw "取消接口返回非预期状态：$($cancelled.status)"
    }
    Start-Sleep -Milliseconds 200
    $cancelPoll++
    $cancelled = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/runs/$($cancelRun.runId)" $null "cancel-poll-$cancelPoll"
}
if ($cancelled.status -ne 'cancelled') { throw "取消接口未在期限内进入 cancelled：$($cancelled.status)" }
$cancelSse = Complete-Stream ([string]$cancelRun.runId) 'cancel-events'
& (Join-Path $scriptRoot 'Assert-OperationsResult.ps1') -Kind Cancelled -SsePath $cancelSse
if ($LASTEXITCODE -ne 0) { throw '取消事件流未形成 cancelled 终态' }
$cancelArtifacts = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/conversations/$($cancelConversation.conversationId)/artifacts" $null 'cancel-artifacts'
if (@($cancelArtifacts.artifacts).Count -gt 0) {
    throw '已取消 run 生成了制品'
}

$beforeInvalid = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/conversations/$conversationId/artifacts" $null 'invalid-before-artifacts'
$invalid = Submit $conversationId '把第 999 条写成小红书推文。' ([Guid]::NewGuid().ToString()) 'invalid-reference-submit'
$invalidSse = Complete-Stream ([string]$invalid.runId) 'invalid-reference'
$invalidEvents = @(Read-Sequences $invalidSse)
$invalidDone = @($invalidEvents | Where-Object { $_.event -eq 'stream_done' }) | Select-Object -Last 1
$invalidError = @($invalidEvents | Where-Object { $_.event -eq 'stream_error' }) | Select-Object -Last 1
if ($invalidDone.payload.status -ne 'failed' -or [string]::IsNullOrWhiteSpace([string]$invalidError.payload.code)) {
    throw '非法引用未返回稳定失败终态和错误码'
}
$afterInvalid = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/conversations/$conversationId/artifacts" $null 'invalid-after-artifacts'
if (@($afterInvalid.artifacts).Count -ne @($beforeInvalid.artifacts).Count) { throw '非法引用错误地产生了制品' }

$pattern = '(?-i:\bERROR\b)|(?i:Traceback|Caused by|SQLSyntaxError|Connection (refused|reset)|DATABASE_UNAVAILABLE|Unhandled)'
foreach ($entry in @(@{ Path = $JavaLogPath; Start = $javaLogStart }, @{ Path = $AgentLogPath; Start = $agentLogStart })) {
    $allLines = @(Get-Content -LiteralPath $entry.Path)
    $effectiveStart = if ($allLines.Count -lt $entry.Start) { 0 } else { $entry.Start }
    $delta = @($allLines | Select-Object -Skip $effectiveStart)
    $hits = @($delta | Select-String -Pattern $pattern -Context 2,2)
    if ($hits.Count -gt 0) {
        $hits | Out-String | Set-Content -LiteralPath (Join-Path $OutputRoot "$([IO.Path]::GetFileName($entry.Path)).errors.txt") -Encoding UTF8
        throw "韧性验收日志门禁失败：$($entry.Path)"
    }
}

[ordered]@{
    conversationId = $conversationId
    idempotentRunId = $first.runId
    reconnectCursor = $cursor
    restartRewriteRunId = $rewrite.runId
    cancelledRunId = $cancelRun.runId
    invalidReferenceRunId = $invalid.runId
    invalidReferenceCode = $invalidError.payload.code
} | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $OutputRoot 'summary.json') -Encoding UTF8

Write-Output "真实韧性验收通过，原始证据目录：$OutputRoot"
