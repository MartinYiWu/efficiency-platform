# R03 RSS/Atom、GitHub Releases、HN 适配器任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R03 |
| 状态 | 进行中 |
| 依赖 | R02 离线通过 |
| 范围 | Agent 侧离线 Provider 适配器与固定夹具 |
| 明确排除 | 真实来源启用、真实公网、缓存存储、自动重试、Tool 注册 |

## 核心契约

- `DiscoveryBatchV2` 同时保存分页完整性、历史覆盖与来源尝试，不能把成功空、失败空、截断和历史未知压成同一空列表。
- 三类适配器只依赖注入的文档获取端口，不自行创建 HTTP 客户端、不重试、不绕过 R01/R02。
- Feed 保留 guid/link、published/updated 和内容范围；缺日期保持缺失，绝不填当前时间。
- GitHub 只访问构造时冻结的 owner/repo，排除 draft，显式标记 prerelease，以受控页码分页，不跟随响应提供的任意 URL。
- HN 列表与每个 item 都计请求；score/descendants 只标记平台热度，item time 只表示平台发帖时间。
- 304 必须由上层缓存提供已授权内容；适配器收到裸 304 时失败关闭。

## 验证顺序

1. 先写成功、成功空、403/429、畸形 200、缺日期和截断红灯。
2. 实现共享失败映射和三个独立适配器。
3. 运行 R03 定向、R01/R02/contracts/architecture 组合、Ruff、mypy 和全量回归。
4. 规格/质量审查通过后才更新账本；所有真实来源继续 disabled/UNVERIFIED。
