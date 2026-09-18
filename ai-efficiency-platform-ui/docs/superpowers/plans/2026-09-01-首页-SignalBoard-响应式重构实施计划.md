# 首页 Signal Board 响应式重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将首页交付为紧凑、连续、可在宽屏/中屏/窄屏自然收缩的 Signal Board 工作驾驶舱。

**Architecture:** 以 `AppShell` 的一体化 Grid 作为唯一页面骨架，导航、顶栏与内容区共享边界和间距。`pages/home` 继续只编排演示 ViewModel；`widgets/dashboard` 负责问候、指标、趋势和优先事项的呈现；图表保持经 `shared/ui/Chart` 懒加载。

**Tech Stack:** React 19、TypeScript、Ant Design 6、CSS Modules、ECharts 6、Vitest、React Testing Library、Playwright。

## 全局约束

- 保留 `pages → widgets → entities → shared` 单向依赖；页面不得直接调用 Axios 或 ECharts。
- 不新增运行时依赖，不接入接口、鉴权、数据筛选、任务编辑或新的导航目的地。
- 宽屏 `≥1280px` 使用 224px 导航、四列指标与 8:4 内容栅格；中屏 `768px–1279px` 使用 56px 图标导航、两列指标和纵向内容；窄屏 `<768px` 使用抽屉导航和单列内容。
- 主区不设置造成无意义留白的居中最大宽度；宽屏内边距 28px、中屏 20px、窄屏 16px，模块间距 12px。
- 通过先失败、后实现、再验证的方式修改；项目当前不是 Git 仓库，不执行提交。

---

## 文件结构

| 文件                                                               | 责任                                   |
| ------------------------------------------------------------------ | -------------------------------------- |
| `src/widgets/appShell/AppShell.tsx`                                | Shell 状态、顶栏、导航与内容区域的组合 |
| `src/widgets/appShell/SideNavigation.tsx`                          | 桌面/中屏导航项与移动端抽屉导航        |
| `src/widgets/appShell/AppShell.module.css`                         | 一体化 Grid、深色导航与三个断点        |
| `src/widgets/dashboard/DashboardHeader.tsx`                        | 情境问候、工作摘要与主操作             |
| `src/widgets/dashboard/MetricGrid.tsx`                             | 紧凑三层指标卡                         |
| `src/widgets/dashboard/MyTodosPanel.tsx`                           | “优先处理”事项列表与空状态             |
| `src/widgets/dashboard/Dashboard.module.css`                       | 首页栅格、卡片与各断点内容布局         |
| `src/entities/dashboardOverview/model/dashboardOverviewFixture.ts` | Signal Board 所需的演示文案            |
| `e2e/app.spec.ts`                                                  | 宽、中、窄三档浏览器验收               |

### Task 1: 先用失败测试定义连续的响应式应用壳

**Files:**

- Create: `src/widgets/appShell/SideNavigation.tsx`
- Modify: `src/widgets/appShell/AppShell.tsx`
- Modify: `src/widgets/appShell/AppShell.module.css`
- Modify: `src/widgets/appShell/AppShell.test.tsx`

**Interfaces:**

- Produces `SideNavigation({ open, onClose }: { open: boolean; onClose: () => void })`，桌面使用 `nav[aria-label="主导航"]`，移动端使用 Ant Design `Drawer`。
- Produces `AppShell({ children }: { children: ReactNode })`，渲染 `banner`、主导航、`main` 和 `button[aria-label="打开导航"]`。

- [x] **Step 1: 写出应用壳语义结构的失败测试**

```tsx
it('renders one shell with navigation, top bar and main content', () => {
  render(
    <AppShell>
      <p>工作内容</p>
    </AppShell>,
  );

  expect(screen.getByRole('banner')).toHaveTextContent('AI 效能平台');
  expect(screen.getByRole('navigation', { name: '主导航' })).toHaveTextContent('首页概览');
  expect(screen.getByRole('button', { name: '打开导航' })).toBeInTheDocument();
  expect(screen.getByRole('main')).toHaveTextContent('工作内容');
});
```

- [x] **Step 2: 运行测试确认失败**

Run: `pnpm test src/widgets/appShell/AppShell.test.tsx`

Expected: FAIL，原因是现有页面壳没有移动端导航触发器或 `main` 语义区域。

- [x] **Step 3: 实现一体化 Shell 和导航组件**

```tsx
// src/widgets/appShell/SideNavigation.tsx
export function SideNavigation({ open, onClose }: SideNavigationProps) {
  return (
    <>
      <nav className={styles.desktopNavigation} aria-label="主导航">
        <Menu mode="inline" selectedKeys={['dashboard']} items={menuItems} />
      </nav>
      <Drawer open={open} placement="left" title="AI 效能平台" onClose={onClose}>
        <nav aria-label="移动端主导航">
          <Menu mode="inline" selectedKeys={['dashboard']} items={menuItems} />
        </nav>
      </Drawer>
    </>
  );
}

// AppShell 的关键结构
<Layout className={styles.shell}>
  <aside className={styles.sider}>
    <SideNavigation open={navigationOpen} onClose={closeNavigation} />
  </aside>
  <Layout className={styles.workspace}>
    <header className={styles.topBar}>...</header>
    <Layout.Content className={styles.content}>
      <main>{children}</main>
    </Layout.Content>
  </Layout>
</Layout>;
```

在 CSS 中用 `grid-template-columns: 224px minmax(0, 1fr)` 管理宽屏；1279px 以下切换为 `56px minmax(0, 1fr)`；767px 以下隐藏 `sider` 并显示触发器。导航为 `#121b2b`，当前项为 `#263d63`，主区为 `#f5f7fb`。

- [x] **Step 4: 运行组件测试确认通过**

Run: `pnpm test src/widgets/appShell/AppShell.test.tsx`

Expected: PASS，断言 `banner`、主导航、移动触发器和 `main` 均存在。

### Task 2: 用失败测试重建首页问候与紧凑指标层级

**Files:**

- Modify: `src/entities/dashboardOverview/model/dashboardOverviewFixture.ts`
- Modify: `src/widgets/dashboard/DashboardHeader.tsx`
- Modify: `src/widgets/dashboard/MetricGrid.tsx`
- Modify: `src/widgets/dashboard/Dashboard.module.css`
- Modify: `src/widgets/dashboard/Dashboard.test.tsx`

**Interfaces:**

- `DashboardHeader({ rangeLabel }: { rangeLabel: string })` 显示“早上好，林晓。”、工作摘要和“新建工作”。
- `MetricGrid({ metrics }: { metrics: readonly DashboardMetric[] })` 维持既有 ViewModel 输入，但视觉固定为“标签 → 主值 → 变化”三层。
- Fixture 的四项文案依次为“本周已完成”“待优先处理”“AI 协作产出”“累计节省时间”。

- [x] **Step 1: 写出文案和指标层级的失败测试**

```tsx
it('renders the signal board greeting and compact metrics', () => {
  render(<HomePage />);

  expect(screen.getByRole('heading', { name: '早上好，林晓。' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '新建工作' })).toBeInTheDocument();
  expect(screen.getByText('本周已完成')).toBeInTheDocument();
  expect(screen.getByText('待优先处理')).toBeInTheDocument();
});
```

- [x] **Step 2: 运行测试确认失败**

Run: `pnpm test src/widgets/dashboard/Dashboard.test.tsx`

Expected: FAIL，原因是现有标题为“工作概览”，指标文案仍为旧驾驶舱命名。

- [x] **Step 3: 实现问候区、演示文案和指标卡视觉**

```tsx
<section className={styles.header} aria-labelledby="dashboard-greeting">
  <div>
    <Typography.Title id="dashboard-greeting" level={1} className={styles.pageTitle}>
      早上好，林晓。
    </Typography.Title>
    <Typography.Text className={styles.headerSummary}>
      今天有 3 项需要你推进的关键工作，AI 已为你整理好上下文。
    </Typography.Text>
  </div>
  <Button type="primary">新建工作</Button>
</section>
```

将 `.metricGrid` 设为 `repeat(4, minmax(0, 1fr))`、间距 `12px`；`.metricCard` 最小高度 `108px`、圆角 `10px`；主值 24px；趋势说明 9px。不得在页面中引入新数据字段或新依赖。

- [x] **Step 4: 运行测试确认通过**

Run: `pnpm test src/widgets/dashboard/Dashboard.test.tsx`

Expected: PASS，问候、主操作与四项 Signal Board 指标均可访问。

### Task 3: 重构趋势与待办为高密度的工作节奏/优先处理区

**Files:**

- Modify: `src/widgets/dashboard/EfficiencyTrendPanel.tsx`
- Modify: `src/widgets/dashboard/MyTodosPanel.tsx`
- Modify: `src/widgets/dashboard/Dashboard.module.css`
- Modify: `src/widgets/dashboard/Dashboard.test.tsx`

**Interfaces:**

- `EfficiencyTrendPanel({ trend })` 以 `Typography.Title level={2}` 输出“工作节奏”，保留懒加载 `Chart`、时间范围和趋势摘要。
- `MyTodosPanel({ todos })` 以 `Typography.Title level={2}` 输出“优先处理”，列表项显示标题、截止/来源元信息和期限标签；空数组显示“暂无优先处理事项”。

- [x] **Step 1: 写出面板重命名和空状态的失败测试**

```tsx
it('renders work rhythm and priority tasks', () => {
  render(<HomePage />);

  expect(screen.getByRole('heading', { name: '工作节奏' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '优先处理' })).toBeInTheDocument();
  expect(screen.getByText('确认本周招聘候选人面试安排')).toBeInTheDocument();
});

it('renders an explicit empty priority state', () => {
  render(<MyTodosPanel todos={[]} />);
  expect(screen.getByText('暂无优先处理事项')).toBeInTheDocument();
});
```

- [x] **Step 2: 运行测试确认失败**

Run: `pnpm test src/widgets/dashboard/Dashboard.test.tsx`

Expected: FAIL，原因是当前模块标题为“工作效能趋势”和“我的待办”，空状态文案不同。

- [x] **Step 3: 实现高密度面板布局**

```tsx
<Card
  className={styles.panel}
  title={
    <Typography.Title level={2} className={styles.panelTitle}>
      优先处理
    </Typography.Title>
  }
  extra={<Typography.Link>全部待办 →</Typography.Link>}
>
  {todos.length === 0 ? (
    <Typography.Text type="secondary">暂无优先处理事项</Typography.Text>
  ) : (
    <Listy
      items={[...todos]}
      rowKey="id"
      itemRender={(todo) => (
        <div className={styles.priorityTask}>
          <div>
            <Typography.Text strong>{todo.title}</Typography.Text>
            <span>
              {todo.dueText} · {todo.sourceLabel}
            </span>
          </div>
          <Tag className={styles.priorityTag}>{todo.dueText.split(' ')[0]}</Tag>
        </div>
      )}
    />
  )}
</Card>
```

将内容面板设置为 `grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr)`，头部高度 48px、正文 16px；待办项纵向内边距 14px、使用细分隔线。图表保持 `aria-label="按日工作效能趋势图"`，不改变 Chart 的释放逻辑。

- [x] **Step 4: 运行测试确认通过**

Run: `pnpm test src/widgets/dashboard/Dashboard.test.tsx`

Expected: PASS，工作节奏、优先处理、任务文本与空状态均通过。

### Task 4: 完成三档响应式验收和项目说明

**Files:**

- Modify: `src/widgets/appShell/AppShell.module.css`
- Modify: `src/widgets/dashboard/Dashboard.module.css`
- Modify: `e2e/app.spec.ts`
- Modify: `README.md`

**Interfaces:**

- CSS 在 `1279px`、`767px` 两个断点完成导航、指标和内容区的结构切换。
- 首页浏览器验收覆盖 1440px、1024px、390px；未知路由仍显示 404。

- [x] **Step 1: 写出三档视口的失败浏览器断言**

```ts
test('adapts the shell across desktop, tablet and mobile', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible();
  await expect(page.getByText('本周已完成')).toBeVisible();

  await page.setViewportSize({ width: 1024, height: 900 });
  await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '工作节奏' })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: '打开导航' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '早上好，林晓。' })).toBeVisible();
});
```

- [x] **Step 2: 运行浏览器测试确认失败**

Run: `pnpm test:e2e`

Expected: FAIL，原因是现有页面不提供移动端导航触发器，也没有新的问候标题。

- [x] **Step 3: 完成断点样式与 README 更新**

```css
@media (max-width: 1279px) {
  .shell {
    grid-template-columns: 56px minmax(0, 1fr);
  }
  .metricGrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .contentGrid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 767px) {
  .shell {
    display: block;
  }
  .sider {
    display: none;
  }
  .content {
    padding: 16px;
  }
  .metricGrid {
    grid-template-columns: 1fr;
  }
}
```

README 增加首页的 Signal Board 布局和三档响应式行为说明，保留演示数据仅可由实体层替换的约束。

- [x] **Step 4: 执行完整验证**

Run: `pnpm format && pnpm lint && pnpm typecheck && pnpm test:coverage && pnpm build && pnpm test:e2e`

Expected: 所有命令退出码为 0；Vitest 覆盖率命令显示全部测试通过；Playwright 显示首页三档视口和 404 场景通过。

## 计划自检

- Spec 的一体化 Shell、宽/中/窄三档断点分别由 Task 1 和 Task 4 实现与验证。
- 问候、紧凑指标、工作节奏与优先事项分别由 Task 2 和 Task 3 覆盖。
- 未引入接口、业务写操作或新依赖；Chart 懒加载边界在 Task 3 中明确保留。
- 已执行占位符扫描；计划内的组件名称、可访问名称、断点和命令在各任务间一致。
