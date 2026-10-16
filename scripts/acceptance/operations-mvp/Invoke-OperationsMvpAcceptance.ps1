[CmdletBinding()]
param(
    [string]$JavaBaseUrl = 'http://127.0.0.1:8080',
    [string]$OutputRoot,
    [string]$JavaLogPath,
    [string]$AgentLogPath,
    [string]$JavaMySqlContainer = 'efficiency-platform-java-mysql',
    [string]$AgentMySqlContainer = 'efficiency-platform-mysql',
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

if ([string]::IsNullOrWhiteSpace($JavaLogPath) -or [string]::IsNullOrWhiteSpace($AgentLogPath)) {
    throw '真实验收必须同时提供 JavaLogPath 和 AgentLogPath'
}
foreach ($log in @($JavaLogPath, $AgentLogPath)) {
    if (-not (Test-Path -LiteralPath $log)) { throw "日志文件不存在：$log" }
}
$javaLogStartLine = @(Get-Content -LiteralPath $JavaLogPath).Count
$agentLogStartLine = @(Get-Content -LiteralPath $AgentLogPath).Count

function Get-LogDelta([string]$Path, [int]$StartLine) {
    $allLines = @(Get-Content -LiteralPath $Path)
    $effectiveStart = if ($allLines.Count -lt $StartLine) { 0 } else { $StartLine }
    return @($allLines | Select-Object -Skip $effectiveStart)
}

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
    if ([string]$copy.Content -cne [string]$detail.bodyMarkdown) { throw '复制正文与制品 Markdown 不一致' }

    $download = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/operations/artifacts/$artifactId/download" -TimeoutSec 30
    Set-Content -LiteralPath (Join-Path $OutputRoot "$ResultName.download.md") -Value $download.Content -Encoding UTF8
    if ($download.Headers.'Content-Disposition' -notmatch 'attachment') { throw '下载接口缺少 attachment 响应头' }
    if ([string]$download.Content -cne [string]$detail.bodyMarkdown) { throw '下载正文与制品 Markdown 不一致' }

    if ($Kind -eq 'Wechat') {
        $html = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/operations/artifacts/$artifactId/wechat-html" -TimeoutSec 30
        Set-Content -LiteralPath (Join-Path $OutputRoot "$ResultName.preview.html") -Value $html.Content -Encoding UTF8
        if ($html.Content -match '(?i)<script|javascript:|\son\w+\s*=') { throw '微信 HTML 预览包含危险内容' }
        if ($html.Content -notmatch '(?i)<h1|<h2|<p') { throw '微信 HTML 预览缺少文章结构标签' }
        if ([string]$html.Content -cne [string]$detail.bodyHtml) { throw 'HTML 预览与制品 HTML 不一致' }
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
    $agentRunId = if ($submission.agentRunId) { [string]$submission.agentRunId } else { [string]$submission.agent_run_id }
    if ([string]::IsNullOrWhiteSpace($runId)) { throw "提交响应缺少 runId：$ResultName" }
    $ssePath = Join-Path $OutputRoot "$ResultName.sse"
    & curl.exe --silent --show-error --fail-with-body --no-buffer --max-time $StreamTimeoutSeconds `
        -H 'Accept: text/event-stream' `
        "$JavaBaseUrl/api/operations/runs/$runId/events?afterSequence=0" `
        --output $ssePath
    if ($LASTEXITCODE -ne 0) { throw "SSE 调用失败：runId=$runId，curlExit=$LASTEXITCODE" }
    $modelCalls = -1
    if ($Kind -eq 'Research') {
        if ([string]::IsNullOrWhiteSpace($agentRunId)) { throw '研究提交响应缺少 agentRunId' }
        $modelLines = @(Get-LogDelta $AgentLogPath $agentLogStartLine | Where-Object {
            $_ -match 'event=research_model_succeeded' -and $_ -match [regex]::Escape("run_id=$agentRunId")
        })
        foreach ($promptId in @('research.v2.relevance', 'research.v2.cluster', 'research.v2.claims')) {
            if (@($modelLines | Where-Object { $_ -match [regex]::Escape("prompt_id=$promptId") }).Count -lt 1) {
                throw "研究未完成必需的真实模型阶段：$promptId"
            }
        }
        $modelCalls = 0
        foreach ($line in $modelLines) {
            if ($line -match 'total_model_calls=(\d+)') {
                $modelCalls = [Math]::Max($modelCalls, [int]$Matches[1])
            }
        }
        if ($modelCalls -lt 1) { throw '研究运行没有真实模型成功日志' }
    }
    $semanticOutput = @(& (Join-Path $scriptRoot 'Assert-OperationsResult.ps1') -Kind $Kind -SsePath $ssePath -MinimumModelCalls $modelCalls)
    $semanticOutput | Set-Content -LiteralPath (Join-Path $OutputRoot "$ResultName.semantic.txt") -Encoding UTF8
    $run = Invoke-Json 'GET' "$JavaBaseUrl/api/operations/runs/$runId" $null "$ResultName-run"
    if ($run.status -notin @('succeeded', 'degraded_succeeded')) {
        throw "Java 运行记录不是成功终态：runId=$runId，status=$($run.status)，failure=$($run.failureMessage)"
    }
    $artifactId = Assert-Artifact $ConversationId $runId $Kind $ResultName
    return @{ runId = $runId; agentRunId = $agentRunId; ssePath = $ssePath; artifactId = $artifactId; modelCalls = $modelCalls }
}

function Export-MySqlEvidence([string]$Container, [string]$Database, [string]$Sql, [string]$Name) {
    $running = (& docker.exe inspect -f '{{.State.Running}}' $Container 2>$null) -eq 'true'
    if (-not $running) { throw "MySQL 容器未运行：$Container" }
    $safeDatabase = $Database -replace '[^a-zA-Z0-9_]', ''
    if ($safeDatabase -ne $Database) { throw "数据库名不合法：$Database" }
    $escapedSql = $Sql.Replace('"', '\"')
    $command = 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --batch --raw -uroot -D ' + $safeDatabase + ' -e "' + $escapedSql + '"'
    $output = & docker.exe exec $Container sh -lc $command
    if ($LASTEXITCODE -ne 0) { throw "数据库证据查询失败：$Container/$Database" }
    $output | Set-Content -LiteralPath (Join-Path $OutputRoot $Name) -Encoding UTF8
}

function Get-DeliverableSetFromSse([string]$Path) {
    $latest = $null
    $raw = Get-Content -Raw -LiteralPath $Path -Encoding UTF8
    foreach ($block in @($raw -split "(?:`r?`n){2,}")) {
        $data = @($block -split "`r?`n" | Where-Object { $_ -like 'data:*' })
        if ($data.Count -eq 0) { continue }
        $event = (($data | ForEach-Object { $_.Substring(5).TrimStart() }) -join "`n") | ConvertFrom-Json -Depth 100
        if ($event.event -eq 'deliverable' -and $null -ne $event.payload.deliverable_set) {
            $latest = $event.payload.deliverable_set
        }
    }
    if ($null -eq $latest) { throw "SSE 缺少 deliverable_set：$Path" }
    return $latest
}

$health = Invoke-WebRequest -Method GET -Uri "$JavaBaseUrl/api/platform/ping" -TimeoutSec 10
Set-Content -LiteralPath (Join-Path $OutputRoot 'java-health.txt') -Value $health.Content -Encoding UTF8

$conversation = Invoke-Json 'POST' "$JavaBaseUrl/api/operations/conversations" @{} 'create-conversation'
$conversationId = if ($conversation.conversationId) { [string]$conversation.conversationId } else { [string]$conversation.id }
if ([string]::IsNullOrWhiteSpace($conversationId)) { throw '创建会话响应缺少 conversationId' }

$summary = [ordered]@{ conversationId = $conversationId }
$research = Submit-Message $conversationId 'research' 'research' 'Research'
$summary.researchRunId = $research.runId
$summary.researchAgentRunId = $research.agentRunId
$summary.researchArtifactId = $research.artifactId
$summary.researchModelCalls = $research.modelCalls

$wechat = $null
$xiaohongshu = $null
if ($Scenario -eq 'All') {
    $wechat = Submit-Message $conversationId 'wechat' 'wechat' 'Wechat'
    $summary.wechatRunId = $wechat.runId
    $summary.wechatArtifactId = $wechat.artifactId
    $xiaohongshu = Submit-Message $conversationId 'xiaohongshu' 'xiaohongshu' 'Xiaohongshu'
    $summary.xiaohongshuRunId = $xiaohongshu.runId
    $summary.xiaohongshuArtifactId = $xiaohongshu.artifactId

    $researchSet = Get-DeliverableSetFromSse $research.ssePath
    $xiaohongshuSet = Get-DeliverableSetFromSse $xiaohongshu.ssePath
    $firstItem = @($researchSet.deliverables | Where-Object {
        $_.deliverable_kind -eq 'ranked_digest' -or $_.content.kind -eq 'ranked_digest'
    } | ForEach-Object { $_.content.items } | Where-Object { [int]$_.rank -eq 1 }) | Select-Object -First 1
    $xiaohongshuDelivery = @($xiaohongshuSet.deliverables | Where-Object {
        ($_.deliverable_kind -eq 'platform_content' -or $_.content.kind -eq 'platform_content') -and
        (($_.platform -eq 'xiaohongshu') -or ($_.content.platform -eq 'xiaohongshu'))
    }) | Select-Object -First 1
    if ($null -eq $firstItem -or $null -eq $xiaohongshuDelivery) {
        throw '小红书第 1 条热点改写缺少研究条目或成稿'
    }
    if ($researchSet.contract_version -eq 'deliverable-set/2') {
        $expectedRefs = @($firstItem.source_refs | Sort-Object -Unique)
        $actualRefs = @($xiaohongshuDelivery.citations | ForEach-Object { $_.citation_id } | Sort-Object -Unique)
        if (($expectedRefs -join ',') -cne ($actualRefs -join ',')) {
            throw "小红书引用未严格闭合到第 1 条热点：expected=$($expectedRefs -join ',') actual=$($actualRefs -join ',')"
        }
    } else {
        $referenceLoads = @(Get-LogDelta $AgentLogPath $agentLogStartLine | Where-Object {
            $_ -match 'event=ranked_reference_snapshot_loaded' -and
            $_ -match [regex]::Escape("source_run_id=$($research.agentRunId)")
        })
        if ($referenceLoads.Count -lt 2) {
            throw '公众号/小红书成稿未均从真实研究快照加载来源闭包'
        }
    }
}

$javaSql = "SELECT COUNT(*) AS conversations FROM ai_operation_conversation WHERE id='$conversationId'; SELECT COUNT(*) AS messages FROM ai_operation_message WHERE conversation_id='$conversationId'; SELECT status,COUNT(*) AS runs FROM ai_operation_run WHERE conversation_id='$conversationId' GROUP BY status; SELECT artifact_type,platform,source_research_run_id,COUNT(*) AS artifacts FROM ai_operation_artifact WHERE conversation_id='$conversationId' GROUP BY artifact_type,platform,source_research_run_id;"
$agentRunIds = @($research.agentRunId, $wechat.agentRunId, $xiaohongshu.agentRunId) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
if ($conversationId -notmatch '^[A-Za-z0-9_-]+$' -or @($agentRunIds | Where-Object { $_ -notmatch '^[A-Za-z0-9_-]+$' }).Count -gt 0) {
    throw '数据库证据查询标识格式不合法'
}
$quotedAgentRuns = ($agentRunIds | ForEach-Object { "'$_'" }) -join ','
$agentSql = "SELECT status,COUNT(*) AS runs FROM agent_run WHERE run_id IN ($quotedAgentRuns) GROUP BY status; SELECT COUNT(*) AS events FROM agent_run_event WHERE run_id IN ($quotedAgentRuns); SELECT source_run_id,content_hash FROM agent_ranked_reference_snapshot WHERE source_run_id IN ($quotedAgentRuns);"
Export-MySqlEvidence $JavaMySqlContainer 'ai_efficiency_platform' $javaSql 'java-db-evidence.txt'
Export-MySqlEvidence $AgentMySqlContainer 'ai_efficiency_platform_agent' $agentSql 'agent-db-evidence.txt'

$logPattern = '(?-i:\bERROR\b)|(?i:Traceback|Caused by|SQLSyntaxError|Connection (refused|reset)|DATABASE_UNAVAILABLE|Unhandled)'
$logInputs = @(
    @{ Path = $JavaLogPath; Start = $javaLogStartLine },
    @{ Path = $AgentLogPath; Start = $agentLogStartLine }
)
$requestBodies = @(@('research', 'wechat', 'xiaohongshu') | ForEach-Object {
    [string]((Get-Content -Raw -LiteralPath (Join-Path $scriptRoot "requests/$_.json") | ConvertFrom-Json).content)
})
foreach ($input in $logInputs) {
    $delta = @(Get-LogDelta $input.Path $input.Start)
    $matches = @($delta | Select-String -Pattern $logPattern -Context 2,2)
    if ($matches.Count -gt 0) {
        $name = [IO.Path]::GetFileName($input.Path)
        $matches | Out-String | Set-Content -LiteralPath (Join-Path $OutputRoot "$name.errors.txt") -Encoding UTF8
        throw "日志门禁失败：$name 命中 $($matches.Count) 处错误，详情已保存"
    }
    foreach ($body in $requestBodies) {
        if (@($delta | Select-String -SimpleMatch $body).Count -gt 0) {
            throw "日志泄露了用户正文：$([IO.Path]::GetFileName($input.Path))"
        }
    }
    $delta | Set-Content -LiteralPath (Join-Path $OutputRoot "$([IO.Path]::GetFileName($input.Path)).delta.log") -Encoding UTF8
}

Save-Json 'summary.json' $summary
Write-Output "真实接口验收通过，原始证据目录：$OutputRoot"
