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
    $decoded = $response.Content | ConvertFrom-Json -Depth 100
    if ($decoded.code -ne 'SUCCESS' -or $null -eq $decoded.data) {
        throw "Java API 响应封装不是成功状态：$Name，code=$($decoded.code)，message=$($decoded.message)"
    }
    return $decoded.data
}

function Assert-Artifact([string]$ConversationId, [string]$RunId, [string]$Kind, [string]$ResultName) {
    $list = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/conversations/$ConversationId/artifacts" $null "$ResultName-artifacts"
    $expectedType = if ($Kind -eq 'Research') { 'ranked_digest' } else { 'platform_content' }
    $expectedPlatform = switch ($Kind) {
        'Wechat' { 'wechat_official_account' }
        'Xiaohongshu' { 'xiaohongshu' }
        default { $null }
    }
    $artifact = @($list.artifacts | Where-Object {
        $_.artifactType -eq $expectedType -and
        ($null -eq $expectedPlatform -or $_.platform -eq $expectedPlatform)
    } | Sort-Object version -Descending) | Select-Object -First 1
    if ($null -eq $artifact) { throw "未找到预期制品：kind=$Kind，runId=$RunId" }
    $artifactId = [string]$artifact.artifactId
    $detail = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/artifacts/$artifactId" $null "$ResultName-artifact-detail"
    if ($detail.runId -ne $RunId) { throw "制品所属 runId 不匹配：artifactId=$artifactId" }
    if ([string]::IsNullOrWhiteSpace([string]$detail.bodyMarkdown)) { throw "制品正文为空：artifactId=$artifactId" }
    if ($detail.PSObject.Properties.Name -contains 'internalMetadata') { throw '公开制品响应泄露了内部元数据' }

    $copy = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/operations/artifacts/$artifactId/copy" -TimeoutSec 30
    Set-Content -LiteralPath (Join-Path $OutputRoot "$ResultName.copy.md") -Value $copy.Content -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($copy.Content)) { throw "复制接口返回空正文：artifactId=$artifactId" }

    $download = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/operations/artifacts/$artifactId/download" -TimeoutSec 30
    Set-Content -LiteralPath (Join-Path $OutputRoot "$ResultName.download.md") -Value $download.Content -Encoding UTF8
    if ($download.Headers.'Content-Disposition' -notmatch 'attachment') { throw '下载接口缺少 attachment 响应头' }

    if ($Kind -eq 'Wechat') {
        $html = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/operations/artifacts/$artifactId/wechat-html" -TimeoutSec 30
        Set-Content -LiteralPath (Join-Path $OutputRoot "$ResultName.preview.html") -Value $html.Content -Encoding UTF8
        if ($html.Content -match '(?i)<script|javascript:|\son\w+\s*=') { throw '微信 HTML 预览包含危险内容' }
        if ($html.Content -notmatch '(?i)<h1|<h2|<p') { throw '微信 HTML 预览缺少文章结构标签' }
    }
    return $artifactId
}

function Submit-Message([string]$ConversationId, [string]$TemplateName, [string]$ResultName, [string]$Kind) {
    $template = Get-Content -Raw -LiteralPath (Join-Path $scriptRoot "requests/$TemplateName.json") | ConvertFrom-Json
    $request = @{
        message = [string]$template.content
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
    $run = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/runs/$runId" $null "$ResultName-run"
    if ($run.status -notin @('succeeded', 'degraded_succeeded')) {
        throw "Java 运行记录不是成功终态：runId=$runId，status=$($run.status)，failure=$($run.failureMessage)"
    }
    $artifactId = Assert-Artifact $ConversationId $runId $Kind $ResultName
    return @{ runId = $runId; ssePath = $ssePath; artifactId = $artifactId }
}

$health = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/platform/ping" -TimeoutSec 10
Set-Content -LiteralPath (Join-Path $OutputRoot 'java-health.txt') -Value $health.Content -Encoding UTF8

$conversation = Invoke-Json 'POST' "$JavaBaseUrl/api/operations/conversations" @{} 'create-conversation'
$conversationId = if ($conversation.conversationId) { [string]$conversation.conversationId } else { [string]$conversation.id }
if ([string]::IsNullOrWhiteSpace($conversationId)) { throw '创建会话响应缺少 conversationId' }

$summary = [ordered]@{ conversationId = $conversationId }
$research = Submit-Message $conversationId 'research' 'research' 'Research'
$summary.researchRunId = $research.runId
$summary.researchArtifactId = $research.artifactId

if ($Scenario -eq 'All') {
    $wechat = Submit-Message $conversationId 'wechat' 'wechat' 'Wechat'
    $summary.wechatRunId = $wechat.runId
    $summary.wechatArtifactId = $wechat.artifactId
    $xiaohongshu = Submit-Message $conversationId 'xiaohongshu' 'xiaohongshu' 'Xiaohongshu'
    $summary.xiaohongshuRunId = $xiaohongshu.runId
    $summary.xiaohongshuArtifactId = $xiaohongshu.artifactId
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
