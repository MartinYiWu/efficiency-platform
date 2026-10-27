import type { ReactNode } from 'react';

import styles from './AiCenter.module.css';

export function AiWorkspaceSection({
  title,
  children,
  className = '',
  compact = false,
}: {
  title: ReactNode;
  children: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <section
      className={`${styles.workspaceSection} ${compact ? styles.compactSection : ''} ${className}`}
    >
      <h3 className={styles.sectionHeading}>{title}</h3>
      {children}
    </section>
  );
}
