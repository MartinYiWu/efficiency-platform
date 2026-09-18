# R02 安全 HTTP 获取与离线解析任务简报

| 属性 | 内容 |
|---|---|
| 任务 | R02 |
| 状态 | 进行中 |
| 范围 | Agent 侧 URL 授权、受限传输端口、内存解析 |
| 明确排除 | 真实公网连接器、来源激活、部署、Java/UI、共享 DDL |

## 目标与不变量

1. URL 在每次连接和每次重定向前都重新解析并授权；任一解析地址不是公网地址时整跳拒绝，连接器调用次数保持为零。
2. `AuthorizedTarget` 只能由服务端策略生成，包含原始主机、核验 IP、选定连接 IP、TLS server name 和解析摘要。
3. 传输端口只接受能够绑定核验 IP、保留 TLS SNI、校验证书并禁用环境代理的连接器。R02 不实现真实连接器，生产真实出网继续关闭。
4. 自动重定向关闭；最多三跳。每跳受相同 host、scheme、port、DNS 与请求预算约束。
5. 压缩前和解压后分别执行流式上限；仅允许 HTML、XML、JSON、纯文本，拒绝 PDF、图片、可执行内容和不支持的压缩编码。
6. feedparser、Trafilatura 只接收已下载的字节或文本，不接收 URL。XML 在进入 feedparser 前执行 DTD/ENTITY、安全解析、深度和节点数门禁。
7. 对外稳定错误只使用 `CONTENT_REJECTED`、`CONTENT_UNAVAILABLE`、`SOURCE_SCHEMA_INVALID`；原始响应体和底层异常不外泄。

## 测试顺序

- URL 策略：私网、localhost、IPv6、IPv4 映射 IPv6、混合 DNS、云元数据、userinfo、HTTP、自定义端口、host 后缀混淆。
- 传输：公网成功、私网重定向零连接、DNS 重绑定、能力不足失败关闭、三跳上限、压缩炸弹、MIME、超时和预算。
- 提取：HTML/TXT/JSON/XML、DOCTYPE/ENTITY、过深 XML、feedparser/Trafilatura 离线入参、内容 hash 与实际 URL。
- 定向测试通过后执行 Ruff、mypy、相关组合回归和全量测试；规格与质量审查均通过后才更新账本为“离线通过”。

## 停止条件

- 无法用端口契约证明连接绑定与 TLS 属性：不实现真实出网。
- 无法在内存边界内安全解析：返回稳定拒绝，不以容错方式放宽。
- R02 通过只证明离线安全边界，不证明任何真实来源免费、可用或已获准。
