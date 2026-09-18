# R01 实施任务简报：来源目录、免费准入与策略配置

## 目标与边界

建立默认关闭的来源配置、显式 adapter 目录、确定性 SourceAdmission 与 SourceRegistry 门禁，使 paid/unknown/过期/未核验/无凭据/无真实剩余额度/历史不足来源在 Provider 调用前被排除。R01 不实现 HTTP、不调用真实来源、不读取 Token 值。

## 文件白名单

- 新增 `configuration/research.py`
- 新增 `capabilities/research/v2/sources.py`、`source_admission.py` 及必要 `__init__.py`
- 必要扩展 `contracts/research_sources_v2.py`
- 新增 `config/research_sources.toml`、`config/research_policies.toml`
- 新增 R01 三组单元测试
- 完成后新增 R01 report/review，并更新账本

## 冻结规则

1. 只允许 enabled、VERIFIED、Schema/权限已核验、用途匹配且 cost=free 或可硬停止 free_quota 的来源。
2. 费用证据和准入记录均有独立 TTL；paid、unknown、charge、未知超额行为、未来核验时间全部拒绝。
3. 需要认证的来源必须由可信运行时声明对应 source credential 已就绪；配置不得保存 Token。
4. free_quota 必须有账户级真实剩余额度快照且大于0；配置 quota_limit 不是实时余额。
5. 用户 allowed/excluded、语言/地区/primary、历史模式和 max_lookback 全部先过滤再排序；未知历史不能声称覆盖。
6. adapter_id 只允许显式注册集合；配置中的模块路径或未知字段拒绝，禁止动态加载。
7. 第一批候选配置均 disabled+UNVERIFIED，使用保留测试 host，不猜真实 RSS/API 地址，不产生外网调用。

## 验收

paid、unknown、过期、证据缺失、Token 缺失、quota 未知、Schema/权限/用途不符、enabled=false、adapter 未注册、历史不足全部红测；实现后运行定向、contracts/architecture、Ruff、mypy 和全量回归。
