# 本机交付包操作记录

交付包只写入本机 `.local-acceptance/ui-delivery-20261103`；没有向外部服务器部署或修改共享数据库。

- 构建包仅含dist、deploy/nginx.conf、可选Node预览脚本、部署说明及VERSION/MANIFEST。
- 不包含.env、node_modules、测试fixture或日志；105个payload文件逐一SHA256核对，另有MANIFEST本身。
- Git工作区有用户既有未提交改动，VERSION显式workingTreeDirty=true；releaseId来自实际源指纹，不用HEAD冒充可复现版本。
- ZIP解包到新的unpacked目录，manifest每个文件校验通过。
- 共享assets先追加前一构建和候选构建，遇同名不同内容立即拒绝；不是清空后覆盖。
- 在隔离目录更新current.json表示版本指针，逐次重启仅本机5199生产预览，依次检查前版、候选、回退前版；每阶段根页与动态深链接为200、入口字节与对应版本一致。
- 回退前后index SHA256一致；从真实前一构建选择旧chunk，在候选和回退阶段均可HTTP读取。
- 这是静态版本/HTTP预览演练，不等同于已执行目标服务器Nginx切换或原子软链接操作；真实部署仍需目标环境参数、nginx -t与用户指令。

确切路径、包SHA256与文件清单以release-manifest.json为准；步骤与入口哈希见rollback-verification.json。最终206项组件、56项默认浏览器及生产专项3项通过，详见final-verification.md。
