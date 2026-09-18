import type { VisibleOperationPhase } from './types';

interface OperationProgressProps {
  value: VisibleOperationPhase;
}

export function OperationProgress({ value }: OperationProgressProps) {
  const hasProgress = typeof value.completed === 'number' && typeof value.target === 'number';

  return (
    <div role="status" aria-live="polite">
      <span>{value.label}</span>
      {hasProgress && <span>{`（${value.completed}/${value.target}）`}</span>}
    </div>
  );
}
