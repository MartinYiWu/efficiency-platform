# 本轮独立交付审查

审查对象：stateful知识/管理/客服用例、默认请求隔离、生产dist服务与代理、Nginx模板及部署回退说明。未执行真实业务API或付费调用。

## 发现与修复

1. P2：只保留旧版本目录不能让旧页面继续访问旧hash。先增加旧chunk实际HTTP断言并观测404，再修为明确的共享追加式assets目录；Nginx与Node预览均支持，文档要求先校验追加、保留旧文件、禁止异内容同名覆盖。release三项重新通过；隔离版本切换实测真实旧构建chunk可访问。
2. P2：默认fixture只阻断fetch/xhr与API，不能覆盖外源script/img/font/document/EventSource。新增各资源类型测试后，通过精确baseURL origin与API/fetch/xhr/eventsource分类统一拒绝；默认全量56项通过。
3. 产品验收发现：知识创建/上传/任务Drawer的固定宽度令390px关闭按钮不可达。先通过viewport和真实点击复现，再改min(原宽度,100vw)，1440/390完整事务及知识15项组件通过。

## 复核

独立复核确认两P2有效修复，未发现新重要缺陷。stateful fixture对请求载荷和状态转换有实质断言，未见无条件成功；Prompt现有API读回与UI恢复编辑边界诚实记录。静态文件realpath边界、HEAD/缓存、API不回退HTML、SSE即时透传及下载保留通过定向HTTP验收。

Nginx未在本机/真实服务器运行；真实服务持久化、真实解析/索引和模型质量仍未验证。最终结果见final-verification.md。
