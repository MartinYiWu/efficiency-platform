[CmdletBinding()]
param(
    [string]$JavaBaseUrl = 'http://127.0.0.1:8080',
    [string]$OutputRoot,
    [string]$JavaLogPath,
    [string]$AgentLogPath,
    [ValidateSet('Research', 'All')]
    [string]$Scenario = 'All',
    [int]$StreamTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $repositoryRoot = Resolve-Path (Join-Path $scriptRoot '../../..')
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $OutputRoot = Join-Path $repositoryRoot ".local-acceptance/operations-mvp/$stamp"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

function Save-Json([string]$Name, [object]$Value) {
    $Value | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath (Join-Path $OutputRoot $Name) -Encoding UTF8
}

function Invoke-Json([string]$Method, [string]$Uri, [object]$Body, [string]$Name) {
    $parameters = @{
        Method = $Method
        Uri = $Uri
        ContentType = 'application/json; charset=utf-8'
        TimeoutSec = 60
    }
    if ($null -ne $Body) {
        $parameters.Body = $Body | ConvertTo-Json -Depth 100 -Compress
        Save-Json "$Name.request.json" $Body
    }
    try {
        $response = Invoke-WebRequest @parameters
    }
    catch {
        $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'NO_RESPONSE' }
        $body = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
        Set-Content -LiteralPath (Join-Path $OutputRoot "$Name.error.txt") -Value "HTTP=$status`n$body" -Encoding UTF8
        throw "真实接口调用失败：$Method $Uri，HTTP=$status，详情已保存到 $OutputRoot"
    }
    Set-Content -LiteralPath (Join-Path $OutputRoot "$Name.response.json") -Value $response.Content -Encoding UTF8
    return $response.Content | ConvertFrom-Json -Depth 100
}

function Submit-Message([string]$ConversationId, [string]$TemplateName, [string]$ResultName, [string]$Kind) {
    $template = Get-Content -Raw -LiteralPath (Join-Path $scriptRoot "requests/$TemplateName.json") | ConvertFrom-Json
    $request = @{
        content = [string]$template.content
        clientRequestId = [Guid]::NewGuid().ToString()
    }
    $submission = Invoke-Json 'POST' "$JavaBaseUrl/api/operations/conversations/$ConversationId/messages" $request $ResultName
    $runId = if ($submission.runId) { [string]$submission.runId } else { [string]$submission.run_id }
    if ([string]::IsNullOrWhiteSpace($runId)) { throw "提交响应缺少 runId：$ResultName" }
    $ssePath = Join-Path $OutputRoot "$ResultName.sse"
    & curl.exe --silent --show-error --fail-with-body --no-buffer --max-time $StreamTimeoutSeconds `
        -H 'Accept: text/event-stream' `
        "$JavaBaseUrl/api/operations/runs/$runId/events?afterSequence=0" `
        --output $ssePath
    if ($LASTEXITCODE -ne 0) { throw "SSE 调用失败：runId=$runId，curlExit=$LASTEXITCODE" }
    & (Join-Path $scriptRoot 'Assert-OperationsResult.ps1') -Kind $Kind -SsePath $ssePath
    if ($LASTEXITCODE -ne 0) { throw "返回语义不满足要求：$ResultName" }
    return @{ runId = $runId; ssePath = $ssePath }
}

$health = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/platform/ping" -TimeoutSec 10
Set-Content -LiteralPath (Join-Path $OutputRoot 'java-health.txt') -Value $health.Content -Encoding UTF8

$conversation = Invoke-Json 'POST' "$JavaBaseUrl/api/operations/conversations" @{} 'create-conversation'
$conversationId = if ($conversation.conversationId) { [string]$conversation.conversationId } else { [string]$conversation.id }
if ([string]::IsNullOrWhiteSpace($conversationId)) { throw '创建会话响应缺少 conversationId' }

$summary = [ordered]@{ conversationId = $conversationId }
$research = Submit-Message $conversationId 'research' 'research' 'Research'
$summary.researchRunId = $research.runId

if ($Scenario -eq 'All') {
    $wechat = Submit-Message $conversationId 'wechat' 'wechat' 'Wechat'
    $summary.wechatRunId = $wechat.runId
    $xiaohongshu = Submit-Message $conversationId 'xiaohongshu' 'xiaohongshu' 'Xiaohongshu'
    $summary.xiaohongshuRunId = $xiaohongshu.runId
}

$logPattern = 'ERROR|Exception|Traceback|Caused by|SQLSyntaxError|Connection refused'
foreach ($log in @($JavaLogPath, $AgentLogPath)) {
    if ([string]::IsNullOrWhiteSpace($log)) { continue }
    if (-not (Test-Path -LiteralPath $log)) { throw "日志文件不存在：$log" }
    $matches = @(Select-String -Path $log -Pattern $logPattern -Context 2,2)
    if ($matches.Count -gt 0) {
        $name = [IO.Path]::GetFileName($log)
        $matches | Out-String | Set-Content -LiteralPath (Join-Path $OutputRoot "$name.errors.txt") -Encoding UTF8
        throw "日志门禁失败：$name 命中 $($matches.Count) 处错误，详情已保存"
    }
}

Save-Json 'summary.json' $summary
Write-Output "真实接口验收通过，原始证据目录：$OutputRoot"
