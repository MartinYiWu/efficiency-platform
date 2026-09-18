import type { ReactNode } from 'react';

import styles from './PageContainer.module.css';

interface PageContainerProps {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

export function PageContainer({ title, actions, children }: PageContainerProps) {
  return (
    <main className={styles.page}>
      {(title || actions) && (
        <header className={styles.header}>
          {title && <h1 className={styles.title}>{title}</h1>}
          {actions && (
            <div className={styles.actions} data-sticky="true" data-testid="page-container-actions">
              {actions}
            </div>
          )}
        </header>
      )}
      <div className={styles.content}>{children}</div>
    </main>
  );
}
