import { DownloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Input, Pagination, Select, Table, Tag } from 'antd';
import { useState } from 'react';
import styles from './AuditPage.module.css';
const logs = [
  [
    '09-01 10:15',
    '沐白',
    '招聘负责人',
    '人工放行',
    '吴磊 · 后端开发工程师',
    '放行条件：必须掌握 Python。原因：候选人具备 4 年 Java 后端经验，主导过日活 20 万系统改造，技术栈可迁移，值得面试评估',
    '192.168.1.***',
  ],
  ['09-01 10:08', '沐白', '招聘负责人', '查看联系方式', '张伟', '查看手机号', '192.168.1.***'],
  [
    '09-01 09:50',
    '李娜',
    '招聘专员',
    '导出',
    '后端开发工程师 · 39 份',
    '导出匹配结果 XLSX',
    '192.168.1.***',
  ],
  [
    '09-01 09:30',
    '沐白',
    '招聘负责人',
    '配置修改',
    '后端开发工程师',
    '权重 v1.1 → v1.2，经验 25%→20%，项目 25%→30%',
    '192.168.1.***',
  ],
  [
    '08-31 16:20',
    '王敏',
    '技术面试官',
    '查看候选人',
    '刘敏',
    '面试官视角，未展示分数',
    '192.168.1.***',
  ],
  [
    '08-30 14:12',
    '李娜',
    '招聘专员',
    '删除',
    '某候选人',
    '删除候选人档案及全部匹配记录',
    '192.168.1.***',
  ],
];
const color = (type: string) =>
  type === '人工放行'
    ? 'orange'
    : type === '导出'
      ? 'green'
      : type === '配置修改'
        ? 'purple'
        : type === '删除'
          ? 'red'
          : 'blue';
export function AuditPage() {
  const [detail, setDetail] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 5;
  const visibleLogs = logs.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div className={styles.page}>
      <header>
        <div>
          <h1>操作审计</h1>
          <p>记录敏感操作，用于合规追溯</p>
        </div>
        <Button icon={<DownloadOutlined />}>导出日志</Button>
      </header>
      <p className={styles.info}>
        ⓘ　以下操作会被完整记录：查看完整联系方式、导出结果、人工放行硬性条件、删除候选人、修改岗位配置。记录不可修改、不可删除。
      </p>
      <section className={styles.filters}>
        <Input prefix={<SearchOutlined />} placeholder="搜索操作人或候选人" />
        <Select
          defaultValue="全部"
          options={[
            { value: '全部' },
            { value: '查看联系方式' },
            { value: '导出' },
            { value: '人工放行' },
          ]}
        />
        <Select
          defaultValue="全部"
          options={[{ value: '全部' }, { value: '沐白' }, { value: '李娜' }]}
        />
        <Input placeholder="开始日期　-　结束日期" />
        <Button type="primary">查询</Button>
        <Button>重置</Button>
      </section>
      <section className={styles.metrics}>
        {[
          ['本月操作', '128', '蓝'],
          ['查看联系方式', '46', '蓝'],
          ['导出', '12', '绿'],
          ['人工放行', '8', '橙'],
        ].map(([title, count, kind]) => (
          <article className={styles[kind]} key={title}>
            <span>{title}</span>
            <b>{count}</b>
            <small>较昨日　{title === '人工放行' ? '↑ 18%' : '↓ 12%'}</small>
          </article>
        ))}
      </section>
      <section className={styles.table}>
        <Table
          rowKey={(r) => r[0] + r[3]}
          pagination={false}
          scroll={{ x: 900 }}
          columns={[
            { title: '时间', dataIndex: 0 },
            { title: '操作人', dataIndex: 1 },
            { title: '角色', dataIndex: 2 },
            { title: '操作类型', dataIndex: 3, render: (v) => <Tag color={color(v)}>{v}</Tag> },
            { title: '对象', dataIndex: 4 },
            {
              title: '详情',
              dataIndex: 5,
              render: (v, r) => (
                <span>
                  {detail === r[0] ? (
                    v
                  ) : (
                    <>
                      {v.slice(0, 28)}…{' '}
                      <Button type="link" onClick={() => setDetail(detail === r[0] ? null : r[0])}>
                        {detail === r[0] ? '收起' : '展开'}
                      </Button>
                    </>
                  )}
                </span>
              ),
            },
            { title: 'IP', dataIndex: 6 },
          ]}
          dataSource={visibleLogs}
        />
        <div className={styles.pagination} aria-label="审计分页">
          <span>
            第 {page} 页 · 共 {logs.length} 条，每页 {pageSize} 条
          </span>
          <Pagination
            current={page}
            pageSize={pageSize}
            showSizeChanger={false}
            size="small"
            total={logs.length}
            onChange={setPage}
          />
        </div>
      </section>
      <footer>审计日志保留 3 年，超期自动归档。日志本身不参与保留期清理。</footer>
    </div>
  );
}
