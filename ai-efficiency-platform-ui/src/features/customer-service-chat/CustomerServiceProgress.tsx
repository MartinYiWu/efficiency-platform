import type { PublicProgress } from '../../entities/customer-service/model';

import styles from '../../pages/customer-service/CustomerServiceChatPage.module.css';

export function CustomerServiceProgress({
  steps,
  status,
  pending = false,
}: {
  steps: PublicProgress[];
  status: string;
  pending?: boolean;
}) {
  if (pending && steps.length === 0) return <div className={styles.progressPending}>请求提交中…</div>;
  const outcome = status === 'FAILED' || status === 'TIMED_OUT'
    ? '本次回答未完成，请重试'
    : status === 'CANCELLED' ? '已停止生成' : null;
  if (steps.length === 0 && !outcome) return null;
  const current = new Map<string, PublicProgress>();
  for (const step of steps) current.set(step.stage, step);
  const finished = ['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(status);
  return (
    <>
      {steps.length > 0 && (
        <details className={styles.progress} open={!finished}>
          <summary>处理过程</summary>
          <ol>
            {[...current.values()].map((step) => (
              <li key={step.stage}>{step.summary}</li>
            ))}
          </ol>
        </details>
      )}
      {outcome && <div className={styles.progressOutcome}>{outcome}</div>}
    </>
  );
}
