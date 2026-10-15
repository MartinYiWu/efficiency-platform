[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Research', 'Wechat', 'Xiaohongshu', 'Cancelled')]
    [string]$Kind,
    [Parameter(Mandatory = $true)]
    [string]$SsePath
)

$ErrorActionPreference = 'Stop'

function Fail([string]$Message) {
    throw "ACCEPTANCE_FAILED: $Message"
}

if (-not (Test-Path -LiteralPath $SsePath)) {
    Fail "SSE 文件不存在：$SsePath"
}

$raw = Get-Content -Raw -LiteralPath $SsePath -Encoding UTF8
$blocks = $raw -split "(?:`r?`n){2,}"
$events = @()
foreach ($block in $blocks) {
    $dataLines = @($block -split "`r?`n" | Where-Object { $_ -like 'data:*' })
    if ($dataLines.Count -eq 0) { continue }
    $json = (($dataLines | ForEach-Object { $_.Substring(5).TrimStart() }) -join "`n")
    try {
        $event = $json | ConvertFrom-Json -Depth 100
    }
    catch {
        Fail "存在无法解析的 SSE data：$($_.Exception.Message)"
    }
    $events += $event
}

if ($events.Count -eq 0) { Fail '没有收到业务 SSE 事件' }

$sequences = @($events | ForEach-Object { [int]$_.sequence })
for ($index = 1; $index -lt $sequences.Count; $index++) {
    if ($sequences[$index] -le $sequences[$index - 1]) {
        Fail 'SSE sequence 不是严格递增'
    }
}

$done = @($events | Where-Object { $_.event -eq 'stream_done' }) | Select-Object -Last 1
if ($null -eq $done) { Fail '缺少 stream_done 终态事件' }
$status = [string]$done.payload.status

if ($Kind -eq 'Cancelled') {
    if ($status -ne 'cancelled') { Fail "取消场景终态不是 cancelled，而是 $status" }
    Write-Output '取消场景语义检查通过'
    exit 0
}

if ($status -ne 'succeeded') {
    $errors = @($events | Where-Object { $_.event -eq 'stream_error' } | ForEach-Object { $_.payload.safe_message })
    Fail "运行终态不是 succeeded，而是 $status；错误：$($errors -join '; ')"
}

$deliveryEvent = @($events | Where-Object { $_.event -eq 'deliverable' }) | Select-Object -Last 1
if ($null -eq $deliveryEvent -or $null -eq $deliveryEvent.payload.deliverable_set) {
    Fail '缺少 deliverable_set'
}
$set = $deliveryEvent.payload.deliverable_set

if ($Kind -eq 'Research') {
    $delivery = @($set.deliverables | Where-Object { $_.deliverable_kind -eq 'ranked_digest' }) | Select-Object -First 1
    if ($null -eq $delivery) { Fail '研究结果缺少 ranked_digest' }
    $items = @($delivery.content.items)
    if ($items.Count -lt 1 -or $items.Count -gt 10) { Fail "热点条目数不在 1..10：$($items.Count)" }
    for ($index = 0; $index -lt $items.Count; $index++) {
        $item = $items[$index]
        if ([int]$item.rank -ne ($index + 1)) { Fail '热点排名不连续' }
        if ([string]::IsNullOrWhiteSpace([string]$item.title)) { Fail "第 $($index + 1) 条标题为空" }
        if ([string]::IsNullOrWhiteSpace([string]$item.summary)) { Fail "第 $($index + 1) 条摘要为空" }
        if (@($item.source_refs).Count -lt 1) { Fail "第 $($index + 1) 条没有来源引用" }
    }
    $citationIds = @($delivery.citations | ForEach-Object { [string]$_.citation_id })
    $domains = @()
    foreach ($citation in @($delivery.citations)) {
        $uri = $null
        if (-not [Uri]::TryCreate([string]$citation.url, [UriKind]::Absolute, [ref]$uri)) {
            Fail "来源 URL 不是绝对地址：$($citation.url)"
        }
        if ($uri.Scheme -notin @('http', 'https')) { Fail "来源 URL 协议不合法：$($citation.url)" }
        $domains += $uri.Host.ToLowerInvariant()
    }
    foreach ($item in $items) {
        foreach ($ref in @($item.source_refs)) {
            if ($ref -notin $citationIds) { Fail "热点引用不存在：$ref" }
        }
    }
    if (@($domains | Sort-Object -Unique).Count -lt 2) { Fail '研究结果少于两个独立来源域名' }
    Write-Output "研究结果语义检查通过：$($items.Count) 条，$(@($domains | Sort-Object -Unique).Count) 个来源域名"
    exit 0
}

$article = @($set.deliverables | Where-Object { $_.deliverable_kind -eq 'platform_content' }) | Select-Object -First 1
if ($null -eq $article) { Fail '成稿结果缺少 platform_content' }
$markdown = [string]$article.content.body_markdown
if ([string]::IsNullOrWhiteSpace($markdown)) { Fail '成稿 Markdown 为空' }

if ($Kind -eq 'Wechat') {
    if ($markdown.Length -lt 1000) { Fail "公众号成稿过短：$($markdown.Length) 字符" }
    if ($markdown -notmatch '(?m)^#\s+.+') { Fail '公众号成稿缺少一级标题' }
    if ($markdown -notmatch '(?m)^##\s+.+') { Fail '公众号成稿缺少二级标题' }
    if ($markdown -notmatch '(?s)##\s+.+\n.+') { Fail '公众号成稿缺少章节正文' }
    Write-Output "公众号成稿语义检查通过：$($markdown.Length) 字符"
    exit 0
}

if ($markdown.Length -gt 5000) { Fail "小红书成稿过长：$($markdown.Length) 字符" }
if (@($article.content.hashtags).Count -lt 1) { Fail '小红书成稿缺少话题标签' }
if (($markdown -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count -lt 3) {
    Fail '小红书成稿缺少分段'
}
Write-Output "小红书成稿语义检查通过：$($markdown.Length) 字符，$(@($article.content.hashtags).Count) 个标签"
