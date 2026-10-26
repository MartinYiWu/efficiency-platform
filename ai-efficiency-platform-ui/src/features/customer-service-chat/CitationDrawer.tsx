import { Drawer } from 'antd';
import ReactMarkdown from 'react-markdown';

import type { Citation } from '../../entities/customer-service/model';
import styles from './CitationDrawer.module.css';

export function CitationDrawer({ citation, onClose }: { citation?: Citation; onClose(): void }) {
  return (
    <Drawer title="引用来源" open={Boolean(citation)} onClose={onClose} size="large">
      {citation && (
        <div className={styles.content}>
          <div className={styles.documentLabel}>来源文档</div>
          <h2>{citation.documentTitle}</h2>
          <div className={styles.meta}>
            <span>版本 V{citation.versionNo}</span>
            {citation.pageNo && <span>第 {citation.pageNo} 页</span>}
            {citation.citationType === 'FULL_PARENT' && <span>完整原文</span>}
            {citation.citationType === 'EXTRACTED_SPANS' && <span>原文节选</span>}
          </div>
          {citation.sectionPath && <div className={styles.section}>{citation.sectionPath}</div>}
          <div className={styles.divider} />
          <h3>引用原文</h3>
          <div className={styles.excerpt}>
            <ReactMarkdown>{citation.quotedText}</ReactMarkdown>
          </div>
        </div>
      )}
    </Drawer>
  );
}
