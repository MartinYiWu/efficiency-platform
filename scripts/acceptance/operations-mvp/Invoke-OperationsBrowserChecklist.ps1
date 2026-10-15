[CmdletBinding()]
param(
    [string]$FrontendUrl = 'http://127.0.0.1:5173/ai-assistants/operations/chat',
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $repositoryRoot = Resolve-Path (Join-Path $scriptRoot '../../..')
    $OutputRoot = Join-Path $repositoryRoot ".local-acceptance/operations-browser/$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

try {
    $response = Invoke-WebRequest -Uri $FrontendUrl -TimeoutSec 10
}
catch {
    throw "前端真实地址不可访问：$FrontendUrl；$($_.Exception.Message)"
}
if ($response.StatusCode -ne 200) { throw "前端真实地址返回 HTTP $($response.StatusCode)" }

$checklist = @"
# OA-09 真实浏览器验收清单

- 前端地址：$FrontendUrl
- 证据目录：$OutputRoot
- 创建时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')

## 必须由真实浏览器完成

- [ ] 发起真实热点研究，Network 中 Java POST、SSE 均为真实请求且最终成功。
- [ ] 同一会话生成公众号和小红书，页面正文符合各平台排版。
- [ ] 记录刷新前 URL 的 conversationId；刷新后该 ID 不变。
- [ ] 刷新后历史用户消息、助手消息、制品操作均恢复，数据库 run 数未增加。
- [ ] 运行中断开 SSE 后按 Last-Event-ID/afterSequence 恢复；事件 sequence 严格递增且消息不重复。
- [ ] 公众号复制正文、下载 Markdown 与制品 bodyMarkdown 完全一致。
- [ ] 微信 HTML 预览与制品 bodyHtml 完全一致，且无 script/javascript/on* 内容。
- [ ] 小红书段落和 5～10 个 #话题标签正确显示。
- [ ] 保存页面全屏截图、公众号预览截图、Network 关键请求截图。
- [ ] 导出或记录浏览器 Console；不存在未处理异常。

## 证据文件约定

- `01-research.png`
- `02-wechat-preview.png`
- `03-xiaohongshu.png`
- `04-refresh-restored.png`
- `05-network.png`
- `console.txt`
- `browser-result.json`

不得用 Playwright route、MSW、fixture 或静态截图替代以上真实交互。
"@
$checklist | Set-Content -LiteralPath (Join-Path $OutputRoot 'checklist.md') -Encoding UTF8

[ordered]@{
    frontendUrl = $FrontendUrl
    outputRoot = $OutputRoot
    preparedAt = (Get-Date).ToString('o')
    status = 'awaiting_real_browser_evidence'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputRoot 'browser-result.json') -Encoding UTF8

Write-Output "浏览器验收目录已准备：$OutputRoot"
