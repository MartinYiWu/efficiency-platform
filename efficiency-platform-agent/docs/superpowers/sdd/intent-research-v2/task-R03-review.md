# R03 规格与质量审查

## 审查过程

1. 状态语义轮：分别验证成功非空、成功空、失败空、截断与历史未知，禁止“空数组即无结果”。
2. Feed 轮：验证 RSS/Atom、guid/link、published/updated、full/summary、缺日期不补 now、HTML script/style 清除及 cursor 截断。
3. GitHub 轮：验证固定 owner/repo、draft 排除、prerelease 标记、release tag 分离、Link 页码与 rate limit 记录、畸形 200/403/429。
4. HN 轮：验证列表 + item 全部计账、并发上限、最多 item 数、部分 item 失败隔离、平台时间与平台热度语义。
5. 缓存轮：初版只处理裸 304 不足以满足租户隔离，补充 tenant/source/URL/authorization/cache-version 复合键、有效期和验证器门禁；跨租户与过期缓存均拒绝。
6. 用量轮：发现缓存正文长度不能代表真实下载量，新增 `downloaded_bytes`，304 重验证记录 0 正文字节，重定向体累计计入。
7. 分层轮：三适配器均只调用注入端口；扫描确认没有直接网络客户端，真实来源配置仍全部关闭。

## 最终确认

| 检查项 | 结果 |
|---|---|
| 成功空/失败空/截断/历史未知分离 | 通过 |
| RSS 与 Atom 元数据/内容范围保真 | 通过 |
| 缺日期不填 fetched_at/now | 通过 |
| GitHub 仓库白名单、draft/prerelease、分页/限额 | 通过 |
| HN 双层请求计账、并发与平台语义 | 通过 |
| ETag/Last-Modified 同租户同授权缓存门禁 | 通过 |
| 304、403、429、畸形 200 原因保真 | 通过 |
| Provider 零直接网络客户端 | 通过 |
| contracts/Research/architecture/全量回归 | 通过 |
| 真实来源免费性与公网可用性 | 未执行，按计划保持关闭 |

## 结论

**PASS。** R03 可标记为“离线通过”。未发现遗留 Critical、Important 或 Minor 实现问题；本结论仅代表离线适配和契约边界，不代表任何真实来源已获准、已联网或可用于生产。
