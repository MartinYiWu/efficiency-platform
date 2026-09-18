# R03 实施报告：RSS/Atom、GitHub Releases、HN 首批适配器

## 状态

**离线通过。**

本任务实现 RSS/Atom、GitHub Releases、Hacker News 三类离线来源适配器，以及租户/授权范围隔离的条件请求缓存端口；没有启用任何真实来源、没有发起公网请求、没有读取 Token，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_sources_v2.py`
- `src/efficiency_platform_agent/providers/research/_adapter_support.py`
- `src/efficiency_platform_agent/providers/research/cache.py`
- `src/efficiency_platform_agent/providers/research/feed.py`
- `src/efficiency_platform_agent/providers/research/github_releases.py`
- `src/efficiency_platform_agent/providers/research/hacker_news.py`
- `src/efficiency_platform_agent/providers/research/transport.py`
- `tests/fixtures/research_v2/providers/` 下 RSS、Atom、GitHub 与 HN 固定夹具
- R03 三组 Provider 契约测试、研究发现扩展契约测试、任务简报及本报告/审查

## 已实现边界

- `DiscoveryRequestV2` 必须携带服务端可信 tenant、run、lease 和 authorization scope digest；子请求继承该范围，模型不能通过 Provider 参数自行扩大来源权限。
- `DiscoveryBatchV2` 分离分页完整性与历史覆盖，并至少保存一次 `SourceAttemptV2`；成功空、失败空、截断与历史未知不再压成同一个空列表。
- Candidate 分开保存发布/创建/更新时间及时间语义、来源 item version、内容范围、内联内容和标签。平台发帖时间明确标为 `platform_posted`，不能冒充外链文章首发时间。
- Feed 保留 guid/link、published/updated；完整 Atom content 标为 `full`，description/summary 标为 `summary`，缺日期保持 `None`。HTML fragment 去标签并排除 script/style/noscript，重复/非法条目单独过滤。
- 最新 Feed 的历史覆盖固定为 `unknown`；只有配置已声明 archive/queryable 且当前快照未截断时，批次才可报告 complete。
- GitHub 只构造固定官方 origin + 构造时冻结的 owner/repository URL，不跟随响应提供的任意分页 URL；排除 draft，保留 release id/tag/body/html_url/published/created，显式标记 prerelease，并记录 Link 分页与剩余限额头。
- HN 列表和每个 item 分别计请求，item 请求受最大并发 10、默认最多 50 条约束；单 item 失败保留其他候选并标为 truncated。score/descendants 只记录为 HN 平台热度，HN text 标为 `platform_text`。
- ETag/Last-Modified 条件缓存以 tenant + source + URL + authorization digest + cache version 为键。只有同范围、未过期且存在验证器的缓存才能接受 304；裸 304、跨租户、跨授权范围和过期缓存均失败关闭。
- `FetchedContentV2.downloaded_bytes` 记录真实网络字节，不以缓存正文大小冒充下载用量；重定向体计入成功获取的累计字节。
- 403、429、408/5xx 的稳定原因分别保留为 forbidden、rate limited、temporary failure；适配器自身不重试。
- 三个适配器只依赖注入的 `ResearchDocumentFetcher`，没有导入 HTTPX/requests/socket 或构造可直接出网的客户端。

## 验证证据

```text
R03 定向（Feed/GitHub/HN）：12 passed
R01—R03 + contracts + Research V2 + architecture：166 passed, 124 subtests passed
Ruff（src tests）：All checks passed
mypy（全 src）：Success: no issues found in 243 source files
全量回归：1300 passed, 275 subtests passed, 2 existing dependency warnings in 45.82s
```

两条警告来自既有 Starlette 与 Polars 依赖，不由 R03 引入。

## 未宣称事项

- 官方 Feed、GitHub 与 HN 的真实许可、免费额度、Schema、可用性及历史能力仍未在 X04 核验；R01 配置继续全部 disabled/UNVERIFIED/unknown cost。
- `InMemoryResponseCache` 只用于离线测试/单进程开发，不是生产权威缓存；跨进程存储和恢复属于 X01。
- R03 不负责重试、429 退避、调用账本持久化或 Tool Runtime 注册，这些属于 R04。
- R03 只产出候选，不代表候选正文、发布时间、事实或证据已经通过 R05—R08 的质量门禁。
