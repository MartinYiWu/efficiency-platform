# R02 实施报告：安全 HTTP 获取与离线解析边界

## 状态

**离线通过。**

本任务实现 URL/DNS 授权、逐跳重定向复核、受限连接器端口、双重流式字节上限、允许 MIME 门禁、离线文档/Feed 解析与第三方解析器进程级硬超时；后续已补充安全 IP pinning 连接器和 X04 冻结端点探针的离线实现与契约测试，但尚无已准入来源或公网请求，所有来源仍未启用，未修改 Java/UI/部署/共享 DDL，未执行 Git 操作。

## 交付文件

- `src/efficiency_platform_agent/contracts/research_transport_v2.py`
- `src/efficiency_platform_agent/security/url_policy.py`
- `src/efficiency_platform_agent/providers/research/__init__.py`
- `src/efficiency_platform_agent/providers/research/transport.py`
- `src/efficiency_platform_agent/providers/research/live_connector.py`
- `src/efficiency_platform_agent/providers/research/extraction.py`
- `src/efficiency_platform_agent/providers/research/feed.py`
- `src/efficiency_platform_agent/providers/research/_xml_safety.py`
- `src/efficiency_platform_agent/providers/research/_process_isolation.py`
- R02 三组测试、任务简报及本报告/审查

## 已实现边界

- `UrlPolicy` 在 DNS 前先验证 URL：仅 HTTPS/443、禁止 userinfo、反斜杠、控制字符、localhost、IP literal、未授权 host 与后缀混淆；精确 host 与显式 `*.` host 语义分开。
- 全部 DNS 结果必须是公网单播地址；任一私网、loopback、link-local、reserved、unspecified、multicast、IPv4-mapped IPv6 或混合公网/私网结果均拒绝。授权目标固定原 host、全部核验 IP、选定连接 IP、TLS server name 与解析摘要。
- Provider 不反向依赖 Security。授权目标/来源策略是中立契约，组合根注入 `UrlPolicy`；现有架构依赖矩阵保持不变。
- `SafeHttpTransport` 只接受声明 IP pinning、原 host TLS SNI、证书校验、禁用环境代理的连接器；能力缺失在 DNS 前失败关闭。后续加入的 `AsyncioPinnedHttpConnector` 只连接 `UrlPolicy` 已授权的公网 IP，同时使用原 host 做 TLS SNI 与证书校验，拒绝环境代理、伪造目标、歧义响应帧和超限响应；它尚未绑定来源运行时，因此当前仍不存在可误启用的普通 HTTPX 出网路径。
- 自动重定向关闭，由传输层最多逐跳执行三次；每跳重新做 URL、host、DNS 和公网校验。DNS 重绑定及公网跳私网均在下一次连接前拒绝。
- 连接超时上限 3 秒、请求上限 10 秒，并与剩余 deadline/HTTP 次数预算取更严值；解析器异常、DNS/连接异常与超时映射为稳定错误，不泄露底层异常。
- 压缩前和解压后分别做 2 MiB 默认流式上限；gzip/deflate 截断、拼接流、未知编码、非法 Content-Length、过大重定向体均拒绝。只允许 HTML/XML/JSON/TXT 及明确 `+xml`/`+json` MIME。
- Trafilatura/feedparser 仅接收已下载文本/字节，默认在可 terminate/kill 的 spawn 子进程运行并受 3 秒硬超时；自定义进程内解析器必须显式标记为测试专用。
- XML 在 feedparser 前由 defusedxml 及 DOCTYPE/ENTITY、深度、节点数、2 MiB 门禁检查；提取结果保存最终 URL、正文原始字节 SHA-256 与提取器版本，MIME 保留在 `FetchedContentV2`。

## 验证证据

```text
R02 定向：43 passed
R02 + contracts + Research V2 + architecture：149 passed, 124 subtests passed
Ruff（src tests）：All checks passed
mypy（全 src）：Success: no issues found in 239 source files
全量回归：1283 passed, 275 subtests passed, 2 existing dependency warnings in 34.23s
```

两条警告来自既有 Starlette 与 Polars 依赖，不由 R02 引入。

补充执行过 `ruff check .`；该命令会扫描 `docs/superpowers/sdd` 下既有历史源码快照并报告 53 项快照格式债务。正式源码与测试门禁 `ruff check src tests` 为绿色，本任务没有修改历史快照，也没有用自动修复改写审计材料。

## 未宣称事项

- 没有真实公网连接器，因此未宣称真实 IP pinning/TLS SNI/证书行为已验收；X04 若无法提供并证明相应连接能力，真实出网继续关闭。
- 没有准入或访问任何真实 RSS/API/网页；来源许可、费用、Schema、历史覆盖、可用性和公网冒烟仍归 X04。
- 子进程解析已做离线 Windows/Python 3.13 验证，但尚未在真实 Worker/容器资源限制下验收；不兼容时会失败关闭，集成能力归 X03/X04。
- R02 只冻结安全获取/解析边界；缓存、304、重试/429、调用账本、来源适配器分别属于 R03/R04。
