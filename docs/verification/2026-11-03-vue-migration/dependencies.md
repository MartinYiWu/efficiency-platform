# Vue 迁移依赖记录

运行时技术栈采用用户明确指定的旧工程 Vue 体系；版本以本项目 pnpm 锁文件为准。

| 依赖 | 固定版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| @ant-design/icons-vue | 7.0.1 | MIT | 替换React图标 |
| ant-design-vue | 4.2.6 | MIT | 替换React基础UI |
| axios | 1.20.0 | MIT | 保留既有HTTP工厂 |
| markdown-it | 14.1.0 | MIT | 替换React Markdown的安全正文展示 |
| pinia | 3.0.4 | MIT | 统一Vue应用状态插件 |
| vue | 3.5.26 | MIT | Vue运行时 |
| vue-router | 4.6.4 | MIT | 当前47条路由与懒加载 |
| zod | 4.5.4 | MIT | 保留全部业务契约校验 |

Vue生态与Markdown替代库使用当前锁定稳定版本，已完成安装、全业务严格类型检查和生产构建；未引入第二UI/状态库或与当前业务无关的旧版库。当前未复用依赖Tailwind工具类的整页，因此没有引入Tailwind；ECharts也未因旧工程安装而额外引入。

开发依赖新增Vue插件/vue-tsc、Vue Test Utils/Vue Testing Library/Vue ESLint，用来替换React专属工具；直接补充@testing-library/dom 10用于满足jest-dom的peer要求，安装时该冲突已消失。

生产构建按44个页面懒加载，入口包含Ant Design Vue全局注册，当前主JS约1.56MB、gzip约484KB，有Vite默认500KB分块提示。没有调高阈值掩盖。图标和UI替换成本限定在Vue组件层，业务API/schema不依赖这些UI库。

生产依赖清单不包含react、react-dom、react-router、antd、react-markdown或TanStack React Query；开发测试树可存在工具自身的react-is类型识别包，不是React运行时。
