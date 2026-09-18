import { CheckCircleFilled, CopyOutlined, EditOutlined, EyeOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Modal,
  Progress,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import styles from './PositionDetailPage.module.css';

const hardConditions = [
  {
    key: 'skill',
    type: '必备技能',
    condition: '熟练掌握 Python',
    tolerance: '不适用',
    release: '不允许放行',
  },
  {
    key: 'experience',
    type: '工作年限',
    condition: '3 年以上相关后端开发经验',
    tolerance: '向下放宽 3 个月',
    release: '允许人工放行',
  },
  {
    key: 'education',
    type: '学历层次',
    condition: '本科及以上学历',
    tolerance: '最多向下放宽 1 级',
    release: '允许人工放行',
  },
  {
    key: 'location',
    type: '工作地域',
    condition: '工作地点：上海',
    tolerance: '不适用',
    release: '允许人工放行',
  },
];

const weights = [
  ['技能匹配', 40, '#16a34a', '核心技能的覆盖与证据强度'],
  ['经验匹配', 25, '#2563eb', '年限拟合、行业与职能相关性'],
  ['项目匹配', 25, '#2563eb', '项目关键词、规模、角色层级'],
  ['学历匹配', 5, '#f59e0b', '学历层次与专业相关性'],
  ['加分项', 5, '#f59e0b', '加分技能、证书、语言'],
] as const;

const versionRows = [
  {
    key: 'v1.2',
    version: 'v1.2',
    time: '2026-09-01 09:30',
    summary: '经验期望调整为 3-6 年；补充微服务架构为加分技能',
    matches: '47 份',
    current: true,
  },
  {
    key: 'v1.1',
    version: 'v1.1',
    time: '2026-08-28 14:20',
    summary: '项目权重 20% → 25%，经验权重 30% → 25%',
    matches: '32 份',
    current: false,
  },
  {
    key: 'v1.0',
    version: 'v1.0',
    time: '2026-08-20 10:00',
    summary: '创建岗位配置并启用',
    matches: '0 份',
    current: false,
  },
];

const previewExamples = [
  {
    rows: [
      ['技能', '88 × 40%', '35.2'],
      ['经验', '85 × 25%', '21.3'],
      ['项目', '78 × 25%', '19.5'],
      ['学历', '80 × 5%', '4.0'],
      ['加分', '40 × 5%', '2.0'],
    ],
    total: '82.0',
    tier: '推荐面试',
  },
  {
    rows: [
      ['技能', '72 × 40%', '28.8'],
      ['经验', '76 × 25%', '19.0'],
      ['项目', '80 × 25%', '20.0'],
      ['学历', '70 × 5%', '3.5'],
      ['加分', '100 × 5%', '5.0'],
    ],
    total: '76.3',
    tier: '推荐面试',
  },
];

export function PositionDetailPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState('overview');
  const [versionDiffOpen, setVersionDiffOpen] = useState(false);
  const [notice, context] = message.useMessage();

  return (
    <div className={styles.page} data-testid="position-detail-page">
      {context}
      <header className={styles.hero}>
        <div>
          <Typography.Title level={1}>后端开发工程师（P6）</Typography.Title>
          <span className={styles.tags}>
            <Tag color="blue">技术研发</Tag>
            <Tag color="green">启用中</Tag>
          </span>
          <Typography.Text>
            技术中心 · 编码 JOB-20260901 · 最近更新 2026-09-01 09:30
          </Typography.Text>
        </div>
        <div className={styles.actions}>
          <Button
            icon={<EyeOutlined />}
            onClick={() => navigate('/ai-assistants/hr/positions/new/preview')}
          >
            配置预演
          </Button>
          <Button icon={<CopyOutlined />} onClick={() => notice.info('已复制岗位，草稿已创建')}>
            复制岗位
          </Button>
          <Button
            type="primary"
            icon={<EditOutlined />}
            onClick={() => navigate('/ai-assistants/hr/positions/new')}
          >
            编辑配置
          </Button>
        </div>
      </header>
      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          { key: 'overview', label: '配置概览', children: <OverviewPanel /> },
          { key: 'hard', label: '硬性条件', children: <HardConditionsPanel /> },
          { key: 'soft', label: '软性要求', children: <SoftRequirementsPanel /> },
          { key: 'weights', label: '权重与分档', children: <WeightsPanel /> },
          {
            key: 'versions',
            label: '版本记录',
            children: <VersionsPanel onCompare={() => setVersionDiffOpen(true)} />,
          },
        ]}
      />
      <Modal
        open={versionDiffOpen}
        title="版本差异"
        width={680}
        footer={<Button onClick={() => setVersionDiffOpen(false)}>关闭</Button>}
        onCancel={() => setVersionDiffOpen(false)}
      >
        <Typography.Paragraph type="secondary">
          v1.2 相比 v1.1 仅展示发生变更的配置分组，历史快照不会受当前配置影响。
        </Typography.Paragraph>
        <div className={styles.diffList}>
          <DiffRow label="经验期望" before="3 年以上" after="3-6 年" />
          <DiffRow
            label="加分技能"
            before="Docker、Kubernetes"
            after="Docker、Kubernetes、微服务架构"
          />
          <DiffRow label="配置版本" before="v1.1" after="v1.2" />
        </div>
      </Modal>
    </div>
  );
}

function OverviewPanel() {
  return (
    <div className={styles.grid}>
      <main>
        <Card title="岗位基本信息">
          <dl className={styles.info}>
            <dt>岗位族</dt>
            <dd>技术研发类</dd>
            <dt>所属部门</dt>
            <dd>技术中心 / 后端开发部</dd>
            <dt>岗位级别</dt>
            <dd>P6</dd>
            <dt>岗位职责概述</dt>
            <dd>
              负责后端服务的设计、开发与维护，确保系统的高性能、高可用与可扩展性；参与技术方案设计与系统优化，保障业务稳定交付。
            </dd>
          </dl>
        </Card>
        <Card title="硬性条件">
          <Typography.Text type="secondary">
            硬性条件需人工审核，不参与自动评分，仅用于初步筛选。
          </Typography.Text>
          <Table
            pagination={false}
            size="small"
            dataSource={hardConditions}
            columns={[
              { title: '序号', render: (_, __, index) => index + 1, width: 58 },
              { title: '条件项', dataIndex: 'type', width: 120 },
              { title: '条件描述', dataIndex: 'condition' },
              { title: '匹配规则', render: () => '必须满足', width: 120 },
            ]}
          />
        </Card>
        <Card title="软性要求">
          <SoftRequirementSummary />
        </Card>
      </main>
      <aside>
        <WeightSummary />
        <ThresholdSummary />
        <HealthSummary />
      </aside>
      <Alert
        className={styles.gridAlert}
        type="info"
        showIcon
        title="AI 仅提供辅助分析，最终判断请结合岗位实际需求与人工评估。"
      />
    </div>
  );
}

function HardConditionsPanel() {
  return (
    <div className={styles.tabGrid}>
      <main>
        <Card title="一票否决条件">
          <Alert
            type="info"
            showIcon
            title="共 4 条硬性条件，未通过且未被人工放行的简历不会进入评分环节。"
          />
          <div className={styles.tableWrap}>
            <Table
              pagination={false}
              size="middle"
              dataSource={hardConditions}
              columns={[
                { title: '条件类型', dataIndex: 'type', width: 140 },
                { title: '条件要求', dataIndex: 'condition', width: 280 },
                { title: '容差', dataIndex: 'tolerance', width: 190 },
                {
                  title: '人工放行',
                  dataIndex: 'release',
                  width: 150,
                  render: (value: string) => (
                    <Tag color={value === '允许人工放行' ? 'blue' : 'default'}>{value}</Tag>
                  ),
                },
                { title: '匹配规则', render: () => '必须满足', width: 120 },
              ]}
            />
          </div>
        </Card>
      </main>
      <aside>
        <Card title="条件说明">
          <Space direction="vertical" size={14}>
            <Typography.Text>数值型条件允许向下放宽，临界通过会被单独标记。</Typography.Text>
            <Typography.Text>
              必备技能、工作地域不提供容差，技能缺失默认不可人工放行。
            </Typography.Text>
          </Space>
        </Card>
        <Card title="配置校验">
          <CheckList
            items={[
              '同类型条件仅保留一条',
              '硬性条件数量在建议范围内',
              '不包含禁止作为条件的敏感信息',
            ]}
          />
        </Card>
      </aside>
    </div>
  );
}

function SoftRequirementsPanel() {
  const skills: Array<[string, number]> = [
    ['Python', 10],
    ['Django', 8],
    ['MySQL', 6],
    ['Redis', 5],
    ['消息队列', 4],
  ];
  return (
    <div className={styles.tabGrid}>
      <main>
        <Card title="核心技能与重要度">
          <Alert type="info" showIcon title="软性要求仅影响得分，不构成否决。" />
          <Typography.Paragraph type="secondary">
            共 5 项核心技能，重要度为相对值，无需凑成 100。
          </Typography.Paragraph>
          <div className={styles.skillImportance}>
            {skills.map(([name, importance]) => (
              <div key={name}>
                <b>{name}</b>
                <Progress percent={importance * 10} showInfo={false} strokeColor="#2563eb" />
                <span>重要度 {importance}</span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="加分技能">
          <Tag color="blue">Docker</Tag>
          <Tag color="blue">Kubernetes</Tag>
          <Tag color="blue">微服务架构</Tag>
          <Typography.Paragraph className={styles.helperText} type="secondary">
            加分项缺失不构成负面，仅用于候选人差距较小时提供区分度。
          </Typography.Paragraph>
        </Card>
        <Card title="经验与项目期望">
          <div className={styles.requirementGrid}>
            <Definition label="理想年限区间" value="3-6 年" />
            <Definition label="偏好行业" value="互联网、金融科技" />
            <Definition label="偏好职能关键词" value="后端、服务端、平台" />
            <Definition label="管理经历" value="不要求" />
            <Definition label="项目关键词" value="高并发、分布式、微服务、系统重构" />
            <Definition label="规模期望" value="日活十万级以上" />
            <Definition label="团队规模期望" value="5 人以上" />
            <Definition label="角色层级要求" value="需主导过" />
          </div>
        </Card>
        <Card title="学历专业期望">
          <Tag color="gold">相关专业优先</Tag>
          <Typography.Text type="secondary">
            学历专业相关性只影响学历维度得分，不构成一票否决。
          </Typography.Text>
        </Card>
      </main>
      <aside>
        <Card title="配置提示">
          <Typography.Paragraph>
            核心技能缺失会进入能力缺口；加分技能缺失不会形成负面评价。
          </Typography.Paragraph>
        </Card>
        <Card title="模板参考值">
          <dl className={styles.compactInfo}>
            <dt>核心技能</dt>
            <dd>建议 5-7 项</dd>
            <dt>年限区间</dt>
            <dd>3-6 年</dd>
            <dt>项目关键词</dt>
            <dd>建议 3-5 个</dd>
            <dt>管理经历</dt>
            <dd>中级岗通常不要求</dd>
          </dl>
        </Card>
        <Card title="配置进度">
          <Progress percent={100} size="small" strokeColor="#16a34a" />
          <CheckList
            items={['核心技能已配置（5 项）', '经验期望已配置', '加分技能已配置（3 项）']}
          />
        </Card>
      </aside>
    </div>
  );
}

function WeightsPanel() {
  const [previewIndex, setPreviewIndex] = useState(0);
  const preview = previewExamples[previewIndex];
  const flags = [
    ['需人工复核', '解析置信度低或关键字段缺失时标记'],
    ['硬条件临界', '有条件落在容差区间内时标记'],
    ['简历质量提示', '表述模板化、时间矛盾时标记'],
    ['疑似重复', '与库内简历高度相似时标记'],
    ['特殊背景值得关注', '非典型路径且分数不高时标记'],
  ];
  return (
    <div className={styles.tabGrid}>
      <main>
        <Card title="维度权重">
          {weights.map(([name, value, color, detail]) => (
            <div className={styles.weightSetting} key={name}>
              <b>{name}</b>
              <Progress percent={value} showInfo={false} strokeColor={color} />
              <strong>{value}%</strong>
              <Typography.Text type="secondary">{detail}</Typography.Text>
            </div>
          ))}
          <div className={styles.totalWeight}>
            <CheckCircleFilled />
            合计 100%
          </div>
        </Card>
        <Card title="岗位族权重参考">
          <div className={styles.tableWrap}>
            <Table
              pagination={false}
              size="small"
              rowClassName={(record) => (record.family === '技术研发' ? styles.activeRow : '')}
              dataSource={[
                {
                  key: 'tech',
                  family: '技术研发',
                  skill: '40%',
                  exp: '25%',
                  project: '25%',
                  edu: '5%',
                  bonus: '5%',
                },
                {
                  key: 'product',
                  family: '产品',
                  skill: '20%',
                  exp: '30%',
                  project: '40%',
                  edu: '5%',
                  bonus: '5%',
                },
                {
                  key: 'design',
                  family: '设计',
                  skill: '30%',
                  exp: '20%',
                  project: '45%',
                  edu: '5%',
                  bonus: '0%',
                },
                {
                  key: 'sales',
                  family: '销售',
                  skill: '15%',
                  exp: '40%',
                  project: '35%',
                  edu: '5%',
                  bonus: '5%',
                },
                {
                  key: 'support',
                  family: '职能支持',
                  skill: '30%',
                  exp: '35%',
                  project: '20%',
                  edu: '10%',
                  bonus: '5%',
                },
                {
                  key: 'campus',
                  family: '校招应届',
                  skill: '25%',
                  exp: '5%',
                  project: '35%',
                  edu: '30%',
                  bonus: '5%',
                },
              ]}
              columns={[
                { title: '岗位族', dataIndex: 'family' },
                { title: '技能', dataIndex: 'skill' },
                { title: '经验', dataIndex: 'exp' },
                { title: '项目', dataIndex: 'project' },
                { title: '学历', dataIndex: 'edu' },
                { title: '加分', dataIndex: 'bonus' },
              ]}
            />
          </div>
          <Typography.Paragraph className={styles.helperText} type="secondary">
            以上为模板初始参考值，不是终值。同一岗位族内应按岗位实际判断重点调整。
          </Typography.Paragraph>
        </Card>
        <Card title="分档阈值">
          <ThresholdRows />
          <div className={styles.scoreRail} aria-label="分档阈值色条">
            <span className={styles.scoreMuted} />
            <span className={styles.scoreReview} />
            <span className={styles.scoreRecommend} />
            <span className={styles.scoreStrong} />
          </div>
          <div className={styles.scoreScale}>
            <span>0</span>
            <span>50</span>
            <span>65</span>
            <span>80</span>
            <span>100</span>
          </div>
        </Card>
        <Card title="特殊标记">
          <div className={styles.flagList}>
            {flags.map(([name, detail]) => (
              <div key={name}>
                <span>
                  <b>{name}</b>
                  <Typography.Text type="secondary">{detail}</Typography.Text>
                </span>
                <Switch checked aria-label={name} />
              </div>
            ))}
          </div>
        </Card>
      </main>
      <aside>
        <Card title="权重设置提示">
          <Typography.Paragraph>
            偏架构的高级岗应提高项目权重；偏业务的中级岗应更关注技能覆盖。
          </Typography.Paragraph>
        </Card>
        <Card title="实时预览">
          <Typography.Text strong>一个示例候选人在当前权重下的得分</Typography.Text>
          <div className={styles.scorePreview}>
            {preview.rows.map(([name, formula, score]) => (
              <div key={name}>
                <span>{name}</span>
                <span>{formula}</span>
                <b>{score}</b>
              </div>
            ))}
            <div className={styles.previewTotal}>
              <b>总分</b>
              <strong>{preview.total}</strong>
              <Tag color="blue">{preview.tier}</Tag>
            </div>
          </div>
          <Button
            type="link"
            className={styles.linkButton}
            onClick={() => setPreviewIndex((index) => (index + 1) % previewExamples.length)}
          >
            换一个示例
          </Button>
        </Card>
      </aside>
    </div>
  );
}

function VersionsPanel({ onCompare }: { onCompare: () => void }) {
  return (
    <div className={styles.tabGrid}>
      <main>
        <Card title="配置版本历史">
          <Alert
            type="info"
            showIcon
            title="配置修改不会影响历史匹配结果；每次匹配均保存当时完整配置快照。"
          />
          <div className={styles.tableWrap}>
            <Table
              pagination={false}
              dataSource={versionRows}
              columns={[
                {
                  title: '版本',
                  dataIndex: 'version',
                  width: 130,
                  render: (value: string, record) => (
                    <Space>
                      <b>{value}</b>
                      {record.current && <Tag color="green">当前版本</Tag>}
                    </Space>
                  ),
                },
                { title: '生效时间', dataIndex: 'time', width: 180 },
                { title: '变更摘要', dataIndex: 'summary' },
                { title: '匹配结果', dataIndex: 'matches', width: 110 },
                {
                  title: '操作',
                  width: 110,
                  render: () => (
                    <Button type="link" onClick={onCompare}>
                      查看差异
                    </Button>
                  ),
                },
              ]}
            />
          </div>
        </Card>
      </main>
      <aside>
        <Card title="当前版本">
          <Typography.Title level={3} className={styles.versionTitle}>
            v1.2
          </Typography.Title>
          <Typography.Paragraph type="secondary">生效于 2026-09-01 09:30</Typography.Paragraph>
          <Tag color="green">启用中</Tag>
        </Card>
        <Card title="版本规则">
          <Timeline
            items={[
              { children: '硬性条件变更，主版本加 1' },
              { children: '技能、权重、阈值变更，次版本加 1' },
              { children: '历史记录不可删除，匹配结果保留快照' },
            ]}
          />
        </Card>
      </aside>
    </div>
  );
}

function SoftRequirementSummary() {
  return (
    <div className={styles.skills}>
      {[
        ['核心技能', ['Python', 'Django', 'MySQL', 'Redis', '消息队列']],
        ['加分技能', ['Docker', 'Kubernetes', '微服务']],
        ['期望经验', ['3-6 年']],
        ['项目经验', ['高并发系统开发', '分布式系统设计', '微服务架构实践', '性能优化项目']],
      ].map(([name, values]) => (
        <div key={String(name)}>
          <span>{name}</span>
          <p>
            {(values as string[]).map((value) => (
              <Tag color="blue" key={value}>
                {value}
              </Tag>
            ))}
          </p>
        </div>
      ))}
    </div>
  );
}

function WeightSummary() {
  return (
    <Card title="权重配置">
      {weights.map(([name, value, color]) => (
        <div className={styles.weight} key={name}>
          <span>{name}</span>
          <Progress percent={value} showInfo={false} strokeColor={color} />
          <b>{value}%</b>
        </div>
      ))}
    </Card>
  );
}

function ThresholdSummary() {
  return (
    <Card title="分档阈值">
      <ThresholdRows />
    </Card>
  );
}

function ThresholdRows() {
  return (
    <>
      {[
        ['强烈推荐面试', '≥ 80 分', 'strong'],
        ['推荐面试', '≥ 65 分', 'recommend'],
        ['建议复核', '≥ 50 分', 'review'],
        ['暂不推荐', '< 50 分', 'muted'],
      ].map(([name, value, tone]) => (
        <div className={styles.threshold} key={name}>
          <span className={styles[tone]}>{name}</span>
          <b>{value}</b>
        </div>
      ))}
    </>
  );
}

function HealthSummary() {
  return (
    <Card title="配置健康度">
      <div className={styles.health}>
        <Progress type="circle" percent={100} strokeColor="#16a34a" format={() => '100%'} />
        <CheckList
          items={['硬性条件已配置', '软性要求已配置', '权重配置已完成', '分档阈值已设置']}
        />
      </div>
    </Card>
  );
}

function CheckList({ items }: { items: string[] }) {
  return (
    <div className={styles.checkList}>
      {items.map((item) => (
        <p key={item}>
          <CheckCircleFilled />
          {item}
        </p>
      ))}
    </div>
  );
}
function Definition({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
function DiffRow({ label, before, after }: { label: string; before: string; after: string }) {
  return (
    <div>
      <b>{label}</b>
      <span>{before}</span>
      <span>→</span>
      <strong>{after}</strong>
    </div>
  );
}
function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.card}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
