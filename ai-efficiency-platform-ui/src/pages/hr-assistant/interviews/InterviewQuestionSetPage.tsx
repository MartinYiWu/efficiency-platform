import {
  DeleteOutlined,
  DragOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Button, Input, Modal, Popconfirm, Tag, message } from 'antd';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './InterviewQuestionSetPage.module.css';

type Question = {
  id: string;
  level: string;
  dimension: string;
  source: string;
  minutes: number;
  text: string;
  purpose: string;
};
const initialQuestions: Question[] = [
  {
    id: 'A1',
    level: 'A',
    dimension: '系统设计能力',
    source: '来源：简历亮点',
    minutes: 8,
    text: '你提到主导了订单系统重构，把 QPS 从 2000 提升到 8000。能讲讲当时是怎么定位性能瓶颈的吗？你是怎么判断问题出在哪一层的？',
    purpose: '验证候选人是否真正参与性能优化的分析过程，重点观察其定位问题的方法论。',
  },
  {
    id: 'A2',
    level: 'A',
    dimension: '性能优化',
    source: '来源：简历亮点',
    minutes: 4,
    text: 'QPS 提升过程中，你采用了哪些具体手段？',
    purpose: '核实量化结果的来源与技术决策。',
  },
  {
    id: 'A3',
    level: 'A',
    dimension: '技术决策',
    source: '来源：简历亮点',
    minutes: 4,
    text: '支付模块改造中，你如何处理一致性与可用性的权衡？',
    purpose: '了解候选人复杂系统的决策能力。',
  },
  {
    id: 'B1',
    level: 'B',
    dimension: '技术广度',
    source: '来源：能力缺口 · Redis',
    minutes: 3,
    text: '岗位需要用到 Redis 做缓存。你在订单系统中处理高并发读的时候，有没有用过缓存方案？如果用过，是怎么设计缓存更新策略的？',
    purpose:
      '简历中未体现 Redis 经验。此题用于确认候选人是否有相关实践，或是否具备快速上手的基础认知。未使用过不等于不能用。',
  },
  {
    id: 'B2',
    level: 'B',
    dimension: '云原生',
    source: '来源：能力缺口 · Kubernetes',
    minutes: 3,
    text: '你对容器化部署的接触程度如何？',
    purpose: '核实 Kubernetes 能力缺口。',
  },
  {
    id: 'C1',
    level: 'C',
    dimension: '职责真实性',
    source: '来源：待核实点 · 职责边界',
    minutes: 2,
    text: '你提到“主导”了这次重构。能具体说说架构方案是谁定的？你承担哪些决策？',
    purpose: '确认是架构设计、方案决策还是执行落地。',
  },
];
const structure = [
  ['A', '简历深挖题', '4题 · 16分钟'],
  ['B', '缺口探查题', '3题 · 9分钟'],
  ['C', '疑点澄清题', '2题 · 4分钟'],
  ['D', '专业能力题', '4题 · 16分钟'],
  ['E', '行为协作题', '3题 · 9分钟'],
  ['F', '情景假设题', '1题 · 4分钟'],
];

export function InterviewQuestionSetPage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [questions, setQuestions] = useState(initialQuestions);
  const [expanded, setExpanded] = useState<string[]>(['A1']);
  const [filter, setFilter] = useState('全部');
  const [editing, setEditing] = useState<Question | null>(null);
  const [draft, setDraft] = useState('');
  const shown = useMemo(
    () => questions.filter((question) => filter === '全部' || question.level === filter),
    [filter, questions],
  );
  const toggle = (id: string) =>
    setExpanded((items) =>
      items.includes(id) ? items.filter((item) => item !== id) : [...items, id],
    );
  const saveEdit = () => {
    if (!editing || !draft.trim()) return;
    setQuestions((items) =>
      items.map((item) => (item.id === editing.id ? { ...item, text: draft.trim() } : item)),
    );
    setEditing(null);
    notice.success('题目已保存，修改会保留在当前题集。');
  };
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div>
          <h1>面试题集</h1>
          <b>张伟</b>
          <span>后端开发工程师（P6）</span>
          <p>首轮面试 · 60 分钟 · 技术面试官 · 生成于 09-01 10:20</p>
        </div>
        <div className={styles.headerActions}>
          <Button icon={<ReloadOutlined />}>重新生成</Button>
          <Button onClick={() => navigate('/ai-assistants/hr/interviews/guide')}>预览指南</Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/interviews/guide')}>
            导出面试指南
          </Button>
        </div>
      </header>
      <p className={styles.ai}>
        ✦　AI 辅助生成，请面试官按实际情况调整。评价结论以面试官判断为准。
      </p>
      <div className={styles.layout} data-layout="editor-first" data-testid="question-workspace">
        <aside className={styles.tree}>
          <h2>
            题目结构 <Tag color="blue">17 题 · 58 分钟</Tag>
          </h2>
          {structure.map(([level, name, count]) => (
            <section key={level}>
              <b>
                {level}　{name}
              </b>
              <small>{count}</small>
              {questions
                .filter((q) => q.level === level)
                .map((q) => (
                  <button
                    key={q.id}
                    className={expanded.includes(q.id) ? styles.treeActive : ''}
                    onClick={() => toggle(q.id)}
                  >
                    {q.id}　{q.text.slice(0, 16)}…
                  </button>
                ))}
              {level === 'B' && <Tag color="blue">来自能力缺口</Tag>}
              {level === 'C' && <Tag color="orange">来自待核实点</Tag>}
            </section>
          ))}
          <div className={styles.time}>
            <b>时长分配</b>
            <span>设定 60 分钟 / 当前 58 分钟</span>
            <i>
              <em />
            </i>
            <strong>时长合理</strong>
          </div>
        </aside>
        <main className={styles.questions}>
          <div className={styles.toolbar}>
            <Button
              type="link"
              onClick={() => setExpanded(expanded.length ? [] : questions.map((q) => q.id))}
            >
              {expanded.length ? '折叠全部' : '展开全部'}
            </Button>
            <div>
              {['全部', 'A', 'B', 'C', 'D', 'E', 'F'].map((item) => (
                <button
                  className={filter === item ? styles.filterActive : ''}
                  key={item}
                  onClick={() => setFilter(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <Button type="link">调整顺序</Button>
          </div>
          {shown.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              open={expanded.includes(question.id)}
              onToggle={toggle}
              onEdit={() => {
                setEditing(question);
                setDraft(question.text);
              }}
              onDelete={() =>
                setQuestions((items) => items.filter((item) => item.id !== question.id))
              }
            />
          ))}
          <div className={styles.add}>
            <Button
              icon={<PlusOutlined />}
              onClick={() => {
                const added = {
                  id: `A${questions.length + 1}`,
                  level: 'A',
                  dimension: '自定义',
                  source: '来源：手动添加',
                  minutes: 3,
                  text: '请补充新的面试问题',
                  purpose: '由面试官手动设定考察目的。',
                };
                setQuestions((items) => [...items, added]);
                setExpanded((items) => [...items, added.id]);
              }}
            >
              手动添加题目
            </Button>
            <Button type="link">从题库选择</Button>
          </div>
        </main>
        <aside className={styles.settings}>
          <Setting title="生成设置">
            <p>面试轮次：首轮面试</p>
            <p>面试时长：60 分钟</p>
            <p>面试官角色：技术面试官</p>
            <p>重点维度：系统设计能力 / 技术深度 / 团队协作</p>
          </Setting>
          <Setting title="层级配置">
            {structure.map(([level, name]) => (
              <p key={level}>
                {level} {name}
                <span>
                  {level === 'A' || level === 'D'
                    ? '4'
                    : level === 'F'
                      ? '1'
                      : level === 'C'
                        ? '2'
                        : '3'}
                  　建议 {level === 'F' ? '1-2' : '2-4'}
                </span>
              </p>
            ))}
            <strong>各层级题量均在建议范围内</strong>
          </Setting>
          <Setting title="难度分布">
            <p>基础理解　30%</p>
            <i className={styles.bar}>
              <em />
            </i>
            <p>应用实践　53%</p>
            <i className={styles.bar}>
              <em />
            </i>
            <p>深度设计　17%</p>
            <i className={styles.bar}>
              <em />
            </i>
          </Setting>
          <Setting title="操作">
            <Button
              block
              type="primary"
              onClick={() => navigate('/ai-assistants/hr/interviews/guide')}
            >
              导出面试指南
            </Button>
            <Button block>保存为岗位题库模板</Button>
            <Button block type="link">
              重新生成全部题目
            </Button>
          </Setting>
        </aside>
      </div>
      <footer className={styles.footer}>
        <span>已编辑 2 题 · 最后保存 10:24</span>
        <div>
          <Button>保存草稿</Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/interviews/guide')}>
            导出面试指南
          </Button>
        </div>
      </footer>
      <Modal
        open={Boolean(editing)}
        title="编辑面试题"
        okText="保存"
        cancelText="取消"
        onOk={saveEdit}
        onCancel={() => setEditing(null)}
      >
        <Input.TextArea rows={5} value={draft} onChange={(event) => setDraft(event.target.value)} />
      </Modal>
    </div>
  );
}

function QuestionCard({
  question,
  open,
  onToggle,
  onEdit,
  onDelete,
}: {
  question: Question;
  open: boolean;
  onToggle: (id: string) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <article className={styles.question}>
      <header>
        <DragOutlined />
        <Tag
          color={question.level === 'C' ? 'orange' : question.level === 'B' ? 'blue' : 'geekblue'}
        >
          {question.level}
        </Tag>
        <button onClick={() => onToggle(question.id)}>
          {question.id}　{question.text}
        </button>
        <Tag>{question.dimension}</Tag>
        <Tag
          color={question.level === 'C' ? 'orange' : question.level === 'B' ? 'blue' : 'default'}
        >
          {question.source}
        </Tag>
        <span>{question.minutes} 分钟</span>
        <Button
          type="text"
          aria-label={`编辑${question.id}`}
          icon={<EditOutlined />}
          onClick={onEdit}
        />
      </header>
      {open && (
        <div className={styles.detail}>
          <p className={styles.source}>
            ⌁ 简历原文：主导系统重构，QPS 从 2000 提升至 8000{' '}
            <Button type="link">查看原文 →</Button>
          </p>
          <section className={styles.purpose}>
            <b>考察目的</b>
            {question.purpose}
          </section>
          <section className={styles.expect}>
            <b>
              期望回答要点　<small>4 条</small>
            </b>
            <ul>
              <li>能说清使用的性能分析工具或手段</li>
              <li>能定位到具体瓶颈层并说明数据依据</li>
              <li>能说明排除了其他可能性的原因</li>
              <li>能给出优化前后的对比数据来源</li>
            </ul>
          </section>
          <section className={styles.follow}>
            <b>
              追问方向　<small>3 条</small>
            </b>
            <p>如果当时 QPS 只提升到 4000，你下一步会怎么做？</p>
            <p>优化后有没有引入新的问题？</p>
          </section>
          <div className={styles.rubric}>
            <section>
              <b>优秀</b>
              <p>完整描述定位过程，说明工具、数据依据与方案权衡。</p>
            </section>
            <section>
              <b>合格</b>
              <p>能说清瓶颈层和采取手段，但分析过程较笼统。</p>
            </section>
            <section>
              <b>需警惕</b>
              <p>只能复述结果数字，或将团队成果表述为个人成果。</p>
            </section>
          </div>
          <footer>
            <Button type="link" icon={<ReloadOutlined />}>
              重新生成此题
            </Button>
            <Button type="link" onClick={onEdit}>
              编辑
            </Button>
            <Button type="link">上移</Button>
            <Button type="link">下移</Button>
            <Popconfirm
              title="删除后不可恢复，确认删除此题？"
              okText="删除"
              cancelText="取消"
              onConfirm={onDelete}
            >
              <Button danger type="link" icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </footer>
        </div>
      )}
    </article>
  );
}
function Setting({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.setting}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
