import {
  AppstoreOutlined,
  BarChartOutlined,
  FileTextOutlined,
  InfoCircleFilled,
  TeamOutlined,
} from '@ant-design/icons';
import { Button, Drawer, Input, Select, Tag, Typography, message } from 'antd';
import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionTemplateLibraryPage.module.css';

type Template = {
  id: string;
  name: string;
  family: string;
  experience: string;
  skills: string[];
  used: number;
  verified?: string;
};
const templates: Template[] = [
  {
    id: 'backend',
    name: '后端开发工程师',
    family: '技术研发',
    experience: '3-6年',
    skills: ['Django', '系统设计', 'MySQL', 'Redis'],
    used: 18,
    verified: '一致率 91%',
  },
  {
    id: 'frontend',
    name: '前端开发工程师',
    family: '技术研发',
    experience: '3-6年',
    skills: ['JavaScript', 'Vue.js', 'HTML/CSS', '工程化'],
    used: 12,
  },
  {
    id: 'product',
    name: '产品经理',
    family: '产品',
    experience: '3-6年',
    skills: ['需求分析', '产品设计', '数据分析', '沟通协作'],
    used: 16,
    verified: '一致率 88%',
  },
  {
    id: 'visual',
    name: '视觉设计师',
    family: '设计',
    experience: '3-6年',
    skills: ['UI设计', '视觉规范', 'Figma', '动效设计'],
    used: 9,
  },
  {
    id: 'sales',
    name: '销售经理',
    family: '销售',
    experience: '3-6年',
    skills: ['销售管理', '客户开拓', '谈判技巧', '数据分析'],
    used: 14,
  },
  {
    id: 'hr',
    name: '人力资源专员',
    family: '职能支持',
    experience: '3-6年',
    skills: ['招聘配置', '员工关系', '绩效管理', '数据分析'],
    used: 17,
  },
];

export function PositionTemplateLibraryPage() {
  const navigate = useNavigate();
  const [keyword, setKeyword] = useState('');
  const [family, setFamily] = useState('全部岗位族');
  const [status, setStatus] = useState('已发布');
  const [applied, setApplied] = useState({ keyword: '', family: '全部岗位族', status: '已发布' });
  const [selected, setSelected] = useState<Template | null>(null);
  const [notice, context] = message.useMessage();
  const filtered = useMemo(
    () =>
      templates.filter(
        (item) =>
          item.name.includes(applied.keyword) &&
          (applied.family === '全部岗位族' || item.family === applied.family),
      ),
    [applied],
  );
  const reset = () => {
    setKeyword('');
    setFamily('全部岗位族');
    setStatus('已发布');
    setApplied({ keyword: '', family: '全部岗位族', status: '已发布' });
  };
  const applyTemplate = (template: Template) => {
    notice.success(`已带入“${template.name}”模板，可在向导中按实际岗位调整`);
    navigate('/ai-assistants/hr/positions/new');
  };
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.heading}>
        <div>
          <Typography.Title level={1}>岗位族模板库</Typography.Title>
          <Typography.Text>沉淀通用岗位要求，创建岗位时可快速引用</Typography.Text>
        </div>
        <div>
          <Button onClick={() => notice.info('岗位族管理将在模板配置完成后提供')}>
            管理岗位族
          </Button>
          <Button type="primary" onClick={() => notice.info('新建模板需要先从已配置岗位另存')}>
            ＋ 新建模板
          </Button>
        </div>
      </header>
      <div className={styles.layout}>
        <main>
          <div className={styles.metrics}>
            <Metric icon={<FileTextOutlined />} label="已发布模板" value="24" tone="blue" />
            <Metric icon={<TeamOutlined />} label="已被引用" value="86" tone="purple" />
            <Metric icon={<BarChartOutlined />} label="本月更新" value="5" tone="green" />
          </div>
          <section className={styles.contentPanel}>
            <div className={styles.filters}>
              <Input
                placeholder="搜索模板名称或关键词"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
              />
              <Select
                value={family}
                options={['全部岗位族', '技术研发', '产品', '设计', '销售', '职能支持'].map(
                  (value) => ({ value }),
                )}
                onChange={setFamily}
              />
              <Select
                value={status}
                options={[{ value: '已发布' }, { value: '全部状态' }]}
                onChange={setStatus}
              />
              <Button type="primary" onClick={() => setApplied({ keyword, family, status })}>
                查询
              </Button>
              <Button onClick={reset}>重置</Button>
            </div>
            <div className={styles.cards}>
              {filtered.map((template) => (
                <article className={styles.template} key={template.id}>
                  <div className={styles.templateHeader}>
                    <div>
                      <AppstoreOutlined />
                      <strong>{template.name}</strong>
                    </div>
                    <Tag color="blue">{template.family}</Tag>
                  </div>
                  <Typography.Text>
                    {template.family} · {template.experience}
                  </Typography.Text>
                  <div className={styles.skillTags}>
                    {template.skills.map((skill) => (
                      <Tag key={skill}>{skill}</Tag>
                    ))}
                    <Tag>…</Tag>
                  </div>
                  <div className={styles.weights}>
                    {[
                      ['专业技能', '40%'],
                      ['项目经验', '25%'],
                      ['工程能力', '20%'],
                      ['学习能力', '10%'],
                      ['文化匹配', '5%'],
                    ].map(([label, value]) => (
                      <span key={label}>
                        {label}
                        <b>{value}</b>
                      </span>
                    ))}
                  </div>
                  <div className={styles.templateMeta}>
                    <span>最近更新 09-01</span>
                    <span>已引用 {template.used} 次</span>
                  </div>
                  {template.verified && (
                    <span className={styles.verified}>已验证 · {template.verified}</span>
                  )}
                  <footer>
                    <Button type="link" onClick={() => setSelected(template)}>
                      查看详情
                    </Button>
                    <Button type="primary" onClick={() => applyTemplate(template)}>
                      使用此模板
                    </Button>
                  </footer>
                </article>
              ))}
            </div>
          </section>
        </main>
        <aside>
          <section className={styles.distribution}>
            <h2>岗位族分布</h2>
            {[
              ['技术研发', 8],
              ['产品', 4],
              ['设计', 3],
              ['运营', 3],
              ['销售', 3],
              ['职能支持', 3],
            ].map(([name, value]) => (
              <div key={String(name)}>
                <span>{name}</span>
                <i>
                  <b className={styles[`bar${value}`]} />
                </i>
                <strong>{value}</strong>
              </div>
            ))}
          </section>
          <section className={styles.tip}>
            <InfoCircleFilled />
            <div>
              <h2>模板使用提示</h2>
              <p>基于岗位族模板创建岗位，可大幅提升岗位要求的完整性。</p>
              <p>模板内容可在使用后按需自定义调整。</p>
              <p>定期更新模板，确保岗位要求与业务发展保持一致。</p>
            </div>
          </section>
        </aside>
      </div>
      <footer className={styles.disclaimer}>
        <InfoCircleFilled />
        <span>AI 生成内容仅供参考，请结合岗位实际需求与面试评估综合判断。</span>
        <Button type="link">查看使用说明</Button>
      </footer>
      <Drawer
        title={selected ? `${selected.name} · 模板详情` : '模板详情'}
        placement="right"
        open={selected !== null}
        onClose={() => setSelected(null)}
        size={460}
      >
        <Typography.Paragraph>
          核心技能候选池仅供参考，创建岗位时需要由招聘负责人逐项勾选确认。
        </Typography.Paragraph>
        {selected && (
          <>
            <Typography.Title level={5}>核心技能候选池</Typography.Title>
            {selected.skills.map((skill) => (
              <Tag color="blue" key={skill}>
                {skill}
              </Tag>
            ))}
            <Typography.Title level={5}>参考权重</Typography.Title>
            <Typography.Paragraph>
              专业技能 40% · 项目经验 25% · 工程能力 20% · 学习能力 10% · 文化匹配 5%
            </Typography.Paragraph>
            <Button type="primary" onClick={() => applyTemplate(selected)}>
              使用此模板
            </Button>
          </>
        )}
      </Drawer>
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
  tone: 'blue' | 'purple' | 'green';
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
