import {
  AppstoreOutlined,
  ExclamationCircleFilled,
  FileTextOutlined,
  PlusOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Dropdown, Empty, Input, Select, Table, Tooltip, Typography, message } from 'antd';
import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionListPage.module.css';

type PositionStatus = '启用中' | '配置待完善' | '已停用';

type PositionRow = {
  id: string;
  name: string;
  family: string;
  department: string;
  level: string;
  hardConditions: number;
  weights: string;
  resumes: number;
  status: PositionStatus;
  updatedAt: string;
  hardWarning?: boolean;
  weightWarning?: boolean;
};

const positions: PositionRow[] = [
  {
    id: 'backend',
    name: '后端开发工程师',
    family: '技术研发',
    department: '技术中心',
    level: 'P6',
    hardConditions: 4,
    weights: '40/25/25/5/5',
    resumes: 47,
    status: '启用中',
    updatedAt: '09-01 09:30',
  },
  {
    id: 'frontend',
    name: '前端开发工程师',
    family: '技术研发',
    department: '技术中心',
    level: 'P5',
    hardConditions: 3,
    weights: '45/20/25/5/5',
    resumes: 32,
    status: '启用中',
    updatedAt: '08-28 14:20',
  },
  {
    id: 'product',
    name: '产品经理',
    family: '产品',
    department: '产品部',
    level: 'P6',
    hardConditions: 3,
    weights: '20/30/40/5/5',
    resumes: 28,
    status: '启用中',
    updatedAt: '08-25 10:15',
  },
  {
    id: 'visual',
    name: '视觉设计师',
    family: '设计',
    department: '设计部',
    level: 'P5',
    hardConditions: 2,
    weights: '30/20/45/5/0',
    resumes: 19,
    status: '启用中',
    updatedAt: '08-22 16:40',
  },
  {
    id: 'sales',
    name: '销售经理',
    family: '销售',
    department: '销售一部',
    level: 'M1',
    hardConditions: 3,
    weights: '合计 95%',
    resumes: 0,
    status: '配置待完善',
    updatedAt: '08-30 11:00',
    weightWarning: true,
  },
  {
    id: 'analyst',
    name: '数据分析师',
    family: '技术研发',
    department: '数据中心',
    level: 'P6',
    hardConditions: 6,
    weights: '35/30/25/5/5',
    resumes: 8,
    status: '配置待完善',
    updatedAt: '08-29 09:10',
    hardWarning: true,
  },
  {
    id: 'hr',
    name: '人力资源专员',
    family: '职能支持',
    department: '人力资源部',
    level: 'P4',
    hardConditions: 2,
    weights: '30/35/20/10/5',
    resumes: 15,
    status: '已停用',
    updatedAt: '08-15 15:30',
  },
  {
    id: 'test-development',
    name: '测试开发工程师',
    family: '技术研发',
    department: '技术中心',
    level: 'P5',
    hardConditions: 3,
    weights: '35/25/30/5/5',
    resumes: 21,
    status: '启用中',
    updatedAt: '08-12 14:20',
  },
  {
    id: 'interaction-designer',
    name: '交互设计师',
    family: '设计',
    department: '设计部',
    level: 'P5',
    hardConditions: 2,
    weights: '25/25/40/5/5',
    resumes: 16,
    status: '启用中',
    updatedAt: '08-11 10:05',
  },
  {
    id: 'recruiter',
    name: '招聘专员',
    family: '职能支持',
    department: '人力资源部',
    level: 'P4',
    hardConditions: 2,
    weights: '30/30/25/10/5',
    resumes: 14,
    status: '启用中',
    updatedAt: '08-09 16:40',
  },
  {
    id: 'product-operations',
    name: '产品运营专员',
    family: '运营',
    department: '产品部',
    level: 'P4',
    hardConditions: 2,
    weights: '25/30/30/10/5',
    resumes: 9,
    status: '已停用',
    updatedAt: '08-08 11:35',
  },
  {
    id: 'business-analyst',
    name: '业务分析师',
    family: '产品',
    department: '产品部',
    level: 'P5',
    hardConditions: 3,
    weights: '30/35/25/5/5',
    resumes: 11,
    status: '启用中',
    updatedAt: '08-06 09:15',
  },
];

const familyOptions = ['全部', '技术研发', '产品', '设计', '运营', '销售', '职能支持'].map(
  (value) => ({ value }),
);
const departmentOptions = [
  '全部',
  '技术中心',
  '产品部',
  '设计部',
  '销售一部',
  '数据中心',
  '人力资源部',
].map((value) => ({ value }));
const statusOptions = ['全部', '启用中', '停用'].map((value) => ({ value }));

export function PositionListPage() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState({
    keyword: '',
    family: '全部',
    department: '全部',
    status: '全部',
  });
  const [filters, setFilters] = useState(draft);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [notice, noticeContext] = message.useMessage();
  const rows = useMemo(
    () =>
      positions.filter((position) => {
        const textMatched = position.name.includes(filters.keyword);
        const familyMatched = filters.family === '全部' || position.family === filters.family;
        const departmentMatched =
          filters.department === '全部' || position.department === filters.department;
        const statusMatched =
          filters.status === '全部' ||
          (filters.status === '停用'
            ? position.status === '已停用'
            : position.status === filters.status);
        return textMatched && familyMatched && departmentMatched && statusMatched;
      }),
    [filters],
  );
  const setDraftField = <Key extends keyof typeof draft>(key: Key, value: (typeof draft)[Key]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const resetFilters = () => {
    const initial = { keyword: '', family: '全部', department: '全部', status: '全部' };
    setDraft(initial);
    setFilters(initial);
    setPage(1);
  };
  const applyIncompleteFilter = () => {
    const next = { ...draft, status: '配置待完善' };
    setDraft(next);
    setFilters(next);
    setPage(1);
  };

  return (
    <div className={styles.page}>
      {noticeContext}
      <header className={styles.heading}>
        <div>
          <Typography.Title level={1}>岗位管理</Typography.Title>
          <Typography.Text>配置岗位要求，作为简历匹配的评判依据</Typography.Text>
        </div>
        <div className={styles.headingActions}>
          <Button onClick={() => navigate('/ai-assistants/hr/positions/templates')}>
            从模板创建
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/ai-assistants/hr/positions/new')}
          >
            新建岗位
          </Button>
        </div>
      </header>
      <div className={styles.metrics}>
        <Metric icon={<AppstoreOutlined />} label="启用中岗位" value="12" tone="blue" />
        <Metric icon={<FileTextOutlined />} label="累计匹配简历" value="486" tone="purple" />
        <Metric icon={<TeamOutlined />} label="本月新增岗位" value="3" tone="green" />
        <button className={styles.metricButton} type="button" onClick={applyIncompleteFilter}>
          <Metric icon={<ExclamationCircleFilled />} label="待完善配置" value="2" tone="orange" />
        </button>
      </div>
      <section className={styles.filterPanel} aria-label="岗位筛选">
        <Input
          value={draft.keyword}
          onChange={(event) => setDraftField('keyword', event.target.value)}
          placeholder="搜索岗位名称或编码"
        />
        <label>
          岗位族
          <Select
            value={draft.family}
            options={familyOptions}
            onChange={(value) => setDraftField('family', value)}
          />
        </label>
        <label>
          部门
          <Select
            value={draft.department}
            options={departmentOptions}
            onChange={(value) => setDraftField('department', value)}
          />
        </label>
        <label>
          状态
          <Select
            value={draft.status}
            options={statusOptions}
            onChange={(value) => setDraftField('status', value)}
          />
        </label>
        <Button
          type="primary"
          onClick={() => {
            setFilters(draft);
            setPage(1);
          }}
        >
          查询
        </Button>
        <Button onClick={resetFilters}>重置</Button>
      </section>
      <section className={styles.tablePanel}>
        <Table<PositionRow>
          rowKey="id"
          pagination={{
            current: page,
            pageSize,
            total: rows.length,
            pageSizeOptions: [10, 20, 50],
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            },
          }}
          dataSource={rows}
          scroll={{ x: 1150, y: 'calc(100dvh - 510px)' }}
          columns={[
            { title: '岗位名称', dataIndex: 'name', width: 168 },
            { title: '岗位族', dataIndex: 'family', width: 108 },
            { title: '部门', dataIndex: 'department', width: 114 },
            { title: '职级', dataIndex: 'level', width: 74 },
            {
              title: '硬性条件',
              dataIndex: 'hardConditions',
              width: 100,
              render: (count: number, record) => (
                <span className={record.hardWarning ? styles.warningCell : undefined}>
                  {count} 条
                  {record.hardWarning && (
                    <Tooltip title="硬性条件偏多，建议不超过 5 条">
                      <ExclamationCircleFilled />
                    </Tooltip>
                  )}
                </span>
              ),
            },
            {
              title: '权重配置',
              dataIndex: 'weights',
              width: 140,
              render: (weight: string, record) => (
                <span className={record.weightWarning ? styles.warningCell : styles.configuredCell}>
                  {record.weightWarning && <ExclamationCircleFilled />}
                  {weight}
                </span>
              ),
            },
            {
              title: '匹配简历',
              dataIndex: 'resumes',
              width: 104,
              render: (count: number) => `${count} 份`,
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 118,
              render: (status: PositionStatus) => (
                <span
                  className={
                    status === '启用中'
                      ? styles.enabled
                      : status === '配置待完善'
                        ? styles.incomplete
                        : styles.disabled
                  }
                >
                  {status}
                </span>
              ),
            },
            { title: '更新时间', dataIndex: 'updatedAt', width: 132 },
            {
              title: '操作',
              key: 'actions',
              width: 182,
              render: (_, record) => (
                <div className={styles.actions}>
                  <Button
                    type="link"
                    onClick={() => navigate(`/ai-assistants/hr/positions/${record.id}`)}
                  >
                    查看
                  </Button>
                  <Button type="link" onClick={() => navigate('/ai-assistants/hr/positions/new')}>
                    编辑
                  </Button>
                  <Dropdown
                    menu={{
                      items: [
                        { key: 'copy', label: '复制岗位' },
                        { key: 'template', label: '另存为模板' },
                        { key: 'preview', label: '配置预演' },
                        { key: 'toggle', label: record.status === '已停用' ? '启用' : '停用' },
                        { type: 'divider' },
                        { key: 'delete', danger: true, label: '删除' },
                      ],
                      onClick: ({ key }) =>
                        notice.info(
                          `${record.name}：${key === 'copy' ? '已创建岗位副本' : key === 'template' ? '已保存为模板' : key === 'preview' ? '进入配置预演' : key === 'delete' ? '请在确认弹窗中删除' : '状态已更新'}`,
                        ),
                    }}
                  >
                    <Button type="link">更多⌄</Button>
                  </Dropdown>
                </div>
              ),
            },
          ]}
          locale={{
            emptyText: (
              <Empty description="还没有配置岗位" image={Empty.PRESENTED_IMAGE_SIMPLE}>
                <Typography.Paragraph className={styles.emptyDescription}>
                  岗位配置决定了简历如何被评判。建议先和用人经理一起，把最急招的 1-2
                  个岗位配置好，再开始批量上传简历。
                </Typography.Paragraph>
                <Button
                  type="primary"
                  onClick={() => navigate('/ai-assistants/hr/positions/templates')}
                >
                  从模板创建岗位
                </Button>
                <Button type="link">查看配置指南</Button>
              </Empty>
            ),
          }}
        />
      </section>
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  tone: 'blue' | 'purple' | 'green' | 'orange';
}) {
  return (
    <article className={styles.metric}>
      <span className={styles[tone]}>{icon}</span>
      <div>
        <Typography.Text>{label}</Typography.Text>
        <strong>{value}</strong>
      </div>
    </article>
  );
}
