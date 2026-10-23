import { Descriptions, Drawer, Typography } from 'antd';
import type { Citation } from '../../entities/customer-service/model';

export function CitationDrawer({ citation, onClose }: { citation?: Citation; onClose(): void }) {
  return (
    <Drawer title="引用详情" open={Boolean(citation)} onClose={onClose} width={560}>
      {citation && (
        <>
          <Descriptions
            column={1}
            bordered
            items={[
              { key: 'title', label: '文档', children: citation.documentTitle },
              { key: 'version', label: '版本', children: `V${citation.versionNo}` },
              { key: 'section', label: '章节', children: citation.sectionPath ?? '-' },
              { key: 'page', label: '页码', children: citation.pageNo ?? '-' },
              {
                key: 'type',
                label: '引用类型',
                children:
                  citation.citationType === 'EXTRACTED_SPANS'
                    ? '原文节选'
                    : citation.citationType === 'FULL_PARENT'
                      ? '完整原文'
                      : '该版本未记录',
              },
              {
                key: 'spans',
                label: '原文偏移',
                children: citation.originalSpans?.length
                  ? citation.originalSpans.map((span) => (
                      <div key={`${span.start_offset}-${span.end_offset}`}>
                        [{span.start_offset}, {span.end_offset})
                      </div>
                    ))
                  : '该版本未记录',
              },
            ]}
          />
          <Typography.Title level={5}>引用原文</Typography.Title>
          <Typography.Paragraph>{citation.quotedText}</Typography.Paragraph>
        </>
      )}
    </Drawer>
  );
}
