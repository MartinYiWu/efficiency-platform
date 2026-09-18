import { Button, Space } from 'antd';

import type { NextActionV2 } from '../../entities/operation-deliverable';

interface OperationNextActionsProps {
  actions: NextActionV2[];
  onSubmit: (message: string) => void;
  onShowSources?: () => void;
}

const allowedActionTypes = new Set<NextActionV2['action_type']>([
  'rewrite_for_platform',
  'expand_item',
  'generate_script',
  'replace_candidates',
  'show_sources',
  'refine_constraints',
]);

export function OperationNextActions({
  actions,
  onShowSources,
  onSubmit,
}: OperationNextActionsProps) {
  const visibleActions = actions.filter((action) => allowedActionTypes.has(action.action_type));
  if (visibleActions.length === 0) return null;

  return (
    <section aria-label="后续动作">
      <Space wrap>
        {visibleActions.map((action) => {
          const isSourceAction = action.action_type === 'show_sources';
          return (
            <Button
              disabled={isSourceAction && !onShowSources}
              key={action.action_id}
              onClick={() => {
                if (isSourceAction) {
                  onShowSources?.();
                  return;
                }
                onSubmit(action.label);
              }}
            >
              {action.label}
            </Button>
          );
        })}
      </Space>
    </section>
  );
}
