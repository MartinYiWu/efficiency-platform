import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { AppRouter } from './AppRouter';

describe('AppRouter', () => {
  it('uses the HR workbench as the sole root route instead of rendering the legacy overview', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'AI 人事助手导航' })).toBeInTheDocument();
    expect(screen.queryByText('早上好，林晓。')).not.toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: '主导航' })).not.toBeInTheDocument();
  }, 15_000);

  it('renders the not found page for an unknown route', () => {
    render(
      <MemoryRouter initialEntries={['/missing']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '页面不存在' })).toBeInTheDocument();
  });

  it('renders the HR assistant workbench inside its dedicated platform shell', () => {
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/workbench']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '工作台' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'AI 人事助手导航' })).toHaveTextContent(
      '岗位管理',
    );
    expect(screen.getByPlaceholderText('搜索候选人、岗位')).toBeInTheDocument();
    expect(screen.getByText('上午好，沐白')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '上传简历' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新建岗位' })).toBeInTheDocument();
    expect(screen.getByText('新增简历')).toBeInTheDocument();
    expect(screen.getByText('完成匹配')).toBeInTheDocument();
    expect(screen.getByText('需要你处理')).toBeInTheDocument();
    expect(screen.getByText('岗位匹配进展')).toBeInTheDocument();
  }, 45_000);

  it('uses an expandable HR navigation tree and allows the desktop sidebar to collapse', () => {
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/workbench']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('menuitem', { name: /AI 人事助手/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /岗位管理/ })).toBeVisible();

    fireEvent.click(screen.getByRole('menuitem', { name: /AI 人事助手/ }));
    expect(screen.queryByRole('menuitem', { name: /岗位管理/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('menuitem', { name: /AI 人事助手/ }));
    expect(screen.getByRole('menuitem', { name: /岗位管理/ })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '收合左侧导航' }));
    expect(screen.getByRole('button', { name: '展开左侧导航' })).toBeInTheDocument();
  }, 45_000);

  it('starts the position configuration wizard from its designed basic-information step', () => {
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/positions/new']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '基本信息' })).toBeInTheDocument();
    expect(screen.getByLabelText('岗位名称')).toBeInTheDocument();
    expect(screen.getByText('保存草稿')).toBeInTheDocument();
    expect(screen.getByText('下一步：硬性条件')).toBeInTheDocument();
  }, 10_000);

  it('advances the position wizard to its designed weights-and-grades step', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/positions/new/soft-requirements']}>
        <AppRouter />
      </MemoryRouter>,
    );

    await user.click(screen.getByText('下一步：权重与分档'));

    expect(screen.getByRole('heading', { name: '权重与分档' })).toBeInTheDocument();
    expect(screen.getByText('合计 100%')).toBeInTheDocument();
  }, 20_000);

  it('renders only allowed hard-condition types on the second wizard step', () => {
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/positions/new/hard-conditions']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '硬性条件' })).toBeInTheDocument();
    expect(screen.getByText('必备技能')).toBeInTheDocument();
    expect(screen.queryByText('性别')).not.toBeInTheDocument();
    expect(screen.queryByText('年龄')).not.toBeInTheDocument();
  }, 20_000);

  it('shows the preview results before enabling a configured position', () => {
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/positions/new/preview']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '配置预演' })).toBeInTheDocument();
    expect(screen.getByText('分数分布')).toBeInTheDocument();
    expect(screen.getByText('一致率 80%（8/10）')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '配置无误，启用岗位' })).toBeEnabled();
  }, 20_000);

  it('renders the HR component-and-state specification page', () => {
    render(
      <MemoryRouter initialEntries={['/ai-assistants/hr/component-states']}>
        <AppRouter />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: /组件与状态规范/ })).toBeInTheDocument();
    expect(screen.getByText('AI人事助手 / 组件与状态规范')).toBeInTheDocument();
    expect(screen.getAllByText(/强烈推荐面试/)).not.toHaveLength(0);
    expect(
      screen.getByText(
        'AI 产出的匹配结果与建议仅供参考，请结合岗位实际需求与面试评估综合判断，最终决策由用人部门负责。',
      ),
    ).toBeInTheDocument();
  }, 20_000);
});

it('renders the HR position list with filters and configuration states', () => {
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/positions']}>
      <AppRouter />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: '岗位管理' })).toBeInTheDocument();
  expect(screen.getByText('启用中岗位')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('搜索岗位名称或编码')).toBeInTheDocument();
  expect(screen.getAllByText('配置待完善')).not.toHaveLength(0);
});

it('renders a position configuration detail page', () => {
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/positions/backend']}>
      <AppRouter />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: /后端开发工程师/ })).toBeInTheDocument();
  expect(screen.getByText('岗位基本信息')).toBeInTheDocument();
  expect(screen.getByText('配置健康度')).toBeInTheDocument();
});

it('renders the position-family template library', () => {
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/positions/templates']}>
      <AppRouter />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: '岗位族模板库' })).toBeInTheDocument();
  expect(screen.getByText('已发布模板')).toBeInTheDocument();
  expect(screen.getAllByText('使用此模板')).toHaveLength(6);
});

it('navigates from the HR menu to the resume upload page', async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/workbench']}>
      <AppRouter />
    </MemoryRouter>,
  );

  await user.click(screen.getByRole('menuitem', { name: /简历中心/ }));

  expect(screen.getByRole('heading', { name: '上传简历' })).toBeInTheDocument();
});

it('renders PAGE-07 resume upload with consent-gated parsing and all three upload sources', () => {
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/resumes/upload']}>
      <AppRouter />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: '上传简历' })).toBeInTheDocument();
  expect(screen.getByText('AI人事助手 / 简历中心 / 上传简历')).toBeInTheDocument();
  expect(screen.getByText('当前配置概览')).toBeInTheDocument();
  expect(screen.getByText('张伟_后端开发工程师.pdf')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('checkbox', { name: /已获得候选人授权/ }));
  expect(screen.getByRole('button', { name: '开始上传并解析' })).toBeDisabled();

  fireEvent.click(screen.getByRole('tab', { name: '粘贴文本' }));
  expect(screen.getByPlaceholderText(/粘贴简历文本内容/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('tab', { name: '从人才库选择' }));
  expect(screen.getByText('选择需要补充到本次处理批次的候选人')).toBeInTheDocument();

  expect(screen.getByRole('button', { name: '查看告知同意说明' })).toBeInTheDocument();
}, 30_000);

it('renders the HR intelligent conversation page and sends typed text', async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={['/ai-assistants/hr/chat']}>
      <AppRouter />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: 'AI 人事助手' })).toBeInTheDocument();
  const input = screen.getByRole('textbox', { name: '输入消息' });
  const send = screen.getByRole('button', { name: '发送消息' });
  expect(send).toBeDisabled();

  await user.type(input, '帮我梳理后端开发工程师的面试重点');
  await user.click(send);

  expect(screen.getByText('帮我梳理后端开发工程师的面试重点')).toBeInTheDocument();
  expect(input).toHaveValue('');
  expect(screen.queryByLabelText(/语音输入|表情|添加附件/)).not.toBeInTheDocument();
}, 30_000);

it('renders the operations intelligent conversation page with content-operations copy', async () => {
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={['/ai-assistants/operations/chat']}>
      <AppRouter />
    </MemoryRouter>,
  );

  expect(screen.getByRole('heading', { name: 'AI 内容运营助手' })).toBeInTheDocument();
  expect(screen.getByText('协助处理选题、内容创作、活动策划和复盘')).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'AI 内容运营助手导航' })).toBeInTheDocument();

  const input = screen.getByRole('textbox', { name: '输入消息' });
  await user.type(input, '帮我为新品发布准备三条内容选题');
  await user.click(screen.getByRole('button', { name: '发送消息' }));

  expect(screen.getByText('帮我为新品发布准备三条内容选题')).toBeInTheDocument();
}, 20_000);
