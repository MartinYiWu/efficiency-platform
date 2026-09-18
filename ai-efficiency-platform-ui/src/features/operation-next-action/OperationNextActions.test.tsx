import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { NextActionV2 } from '../../entities/operation-deliverable';
import { OperationNextActions } from './OperationNextActions';

function action(
  actionType: NextActionV2['action_type'],
  label: string,
  intentPatch: Record<string, unknown> = {},
): NextActionV2 {
  return {
    action_id: `action-${actionType}`,
    action_type: actionType,
    label,
    target_deliverable_id: actionType === 'show_sources' ? null : 'deliverable-1',
    target_item_ids: [],
    intent_patch: intentPatch,
    requires_user_input: false,
  };
}

describe('OperationNextActions', () => {
  it('点击改写动作只提交一条可见的下一轮消息', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(
      <OperationNextActions
        actions={[action('rewrite_for_platform', '把第 1 条写成小红书文案')]}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole('button', { name: '把第 1 条写成小红书文案' }));
    expect(onSubmit).toHaveBeenCalledWith('把第 1 条写成小红书文案');
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('show_sources 只展开来源，不提交或暴露 intent_patch', async () => {
    const onSubmit = vi.fn();
    const onShowSources = vi.fn();
    const user = userEvent.setup();
    render(
      <OperationNextActions
        actions={[action('show_sources', '查看来源', { credential: '不得展示' })]}
        onShowSources={onShowSources}
        onSubmit={onSubmit}
      />,
    );

    await user.click(screen.getByRole('button', { name: '查看来源' }));
    expect(onShowSources).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.queryByText('不得展示')).not.toBeInTheDocument();
  });

  it('只显示六种允许动作，忽略未知动作', () => {
    const allowedActions: NextActionV2[] = [
      action('rewrite_for_platform', '改写'),
      action('expand_item', '展开'),
      action('generate_script', '生成脚本'),
      action('replace_candidates', '替换候选'),
      action('show_sources', '查看来源'),
      action('refine_constraints', '补充约束'),
      {
        ...action('rewrite_for_platform', '未知动作'),
        action_type: 'server_command' as NextActionV2['action_type'],
      },
    ];
    render(<OperationNextActions actions={allowedActions} onSubmit={vi.fn()} />);

    expect(screen.getAllByRole('button')).toHaveLength(6);
    expect(screen.queryByRole('button', { name: '未知动作' })).not.toBeInTheDocument();
  });
});
