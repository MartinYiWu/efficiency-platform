import {
  CheckOutlined,
  CloseOutlined,
  DownOutlined,
  InfoCircleFilled,
  PlusOutlined,
  RightOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { Button, Checkbox, InputNumber, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import styles from './InterviewGeneratePage.module.css';

const rounds = ['首轮面试', '复试', '终面'];
const durations = ['30分钟', '45分钟', '60分钟', '90分钟'];
const roles = [
  ['HR 面试官', '动机、稳定性、协作'],
  ['技术面试官', '技术深度、方案设计'],
  ['用人经理', '综合能力、团队适配'],
] as const;
const dimensions = ['系统设计能力', '技术深度', '团队协作', '问题定位能力', '学习能力', '沟通表达'];
const questionLevels = [
  ['A', '简历深挖', 4],
  ['B', '缺口探查', 3],
  ['C', '疑点澄清', 2],
  ['D', '专业能力', 4],
  ['E', '行为协作', 3],
  ['F', '情景假设', 1],
] as const;

export function InterviewGeneratePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [notice, context] = message.useMessage();
  const [round, setRound] = useState('首轮面试');
  const [duration, setDuration] = useState('60分钟');
  const [role, setRole] = useState('技术面试官');
  const [selectedDimensions, setSelectedDimensions] = useState<string[]>([
    '系统设计能力',
    '技术深度',
    '团队协作',
  ]);
  const [expanded, setExpanded] = useState(false);
  const [saveTemplate, setSaveTemplate] = useState(false);
  const [counts, setCounts] = useState<number[]>(questionLevels.map(([, , count]) => count));
  const isBatch = params.get('batch') === '1';
  const total = counts.reduce((sum, count) => sum + count, 0);

  const close = () => navigate('/ai-assistants/hr/matching/zhang-wei');
  const toggleDimension = (dimension: string) => {
    setSelectedDimensions((current) =>
      current.includes(dimension)
        ? current.filter((item) => item !== dimension)
        : [...current, dimension],
    );
  };

  return (
    <section className={styles.stage} aria-label="生成面试题配置">
      {context}
      <div className={styles.backdrop} />
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="generate-title"
      >
        <header className={styles.dialogHeader}>
          <div>
            <Typography.Title id="generate-title" level={1}>
              生成面试题
            </Typography.Title>
            <p>基于简历与匹配结果生成，重点覆盖能力缺口与待核实点</p>
          </div>
          <Button type="text" aria-label="关闭" icon={<CloseOutlined />} onClick={close} />
        </header>

        {isBatch ? (
          <section className={styles.batchCandidate}>
            <span>已选 8 位候选人</span>
            <div className={styles.avatarGroup} aria-label="候选人头像组">
              {['张', '李', '王', '刘', '陈'].map((name) => (
                <i key={name}>{name}</i>
              ))}
              <i>+3</i>
            </div>
            <Button type="link">查看名单</Button>
            <p>
              批量生成时，各候选人的题目会基于各自的简历与匹配结果分别生成，通用题部分会保持一致。
            </p>
          </section>
        ) : (
          <section className={styles.candidate}>
            <i>张</i>
            <b>张伟</b>
            <span>后端开发工程师（P6）</span>
            <Tag color="green">强烈推荐面试　88.5</Tag>
          </section>
        )}

        <div className={styles.form}>
          <FormGroup title="面试轮次">
            <PillGroup options={rounds} value={round} onChange={setRound} />
          </FormGroup>
          <FormGroup title="面试时长" hint="时长包含开场介绍、核心提问、追问讨论与候选人提问环节。">
            <PillGroup options={durations} value={duration} onChange={setDuration} />
          </FormGroup>
          <FormGroup title="面试官角色">
            <div className={styles.roleGroup}>
              {roles.map(([name, hint]) => (
                <button
                  aria-pressed={role === name}
                  className={`${styles.roleCard} ${role === name ? styles.selected : ''}`}
                  key={name}
                  onClick={() => setRole(name)}
                  type="button"
                >
                  <TeamOutlined />
                  <span>
                    <b>{name}</b>
                    <small>偏重「{hint}」</small>
                  </span>
                  {role === name && <CheckOutlined className={styles.cornerCheck} />}
                </button>
              ))}
            </div>
          </FormGroup>
          <FormGroup title="重点考察维度" hint="可多选，也可留空。">
            <div className={styles.dimensionGroup}>
              {dimensions.map((dimension) => {
                const checked = selectedDimensions.includes(dimension);
                return (
                  <button
                    className={`${styles.dimension} ${checked ? styles.checked : ''}`}
                    key={dimension}
                    onClick={() => toggleDimension(dimension)}
                    type="button"
                  >
                    <span>{checked && <CheckOutlined />}</span>
                    {dimension}
                  </button>
                );
              })}
              <Button
                className={styles.custom}
                icon={<PlusOutlined />}
                onClick={() => notice.info('已进入自定义维度录入状态。')}
              >
                自定义维度
              </Button>
            </div>
          </FormGroup>
          <section className={styles.coverage}>
            <b>本次将重点覆盖</b>
            <CoverageRow
              title="简历亮点"
              count="4 项"
              description="订单系统重构、QPS提升、支付模块改造、5人小组管理"
              target="简历深挖题"
            />
            <CoverageRow
              title="能力缺口"
              count="2 项"
              description="Redis、Kubernetes"
              target="缺口探查题"
            />
            <CoverageRow
              title="待核实点"
              count="3 项"
              description="职责边界、Django使用深度、时间断档"
              target="疑点澄清题"
            />
          </section>
          <section className={styles.quantity}>
            <button
              className={styles.quantityHeader}
              type="button"
              onClick={() => setExpanded((current) => !current)}
            >
              <b>层级题量分配（{duration}）</b>
              {expanded ? <UpOutlined /> : <DownOutlined />}
            </button>
            {expanded && (
              <div className={styles.quantityGrid}>
                {questionLevels.map(([level, label], index) => (
                  <label key={level}>
                    <b>{level} 级</b>
                    <span>{label}</span>
                    <InputNumber
                      aria-label={`${label}题量`}
                      min={0}
                      max={20}
                      value={counts[index]}
                      onChange={(value) =>
                        setCounts((current) =>
                          current.map((count, position) =>
                            position === index ? Number(value ?? 0) : count,
                          ),
                        )
                      }
                    />
                    <small>题</small>
                  </label>
                ))}
                <p>
                  合计 {total} 题 · 预估 {total === 17 ? '58' : Math.max(5, total * 3)} 分钟
                </p>
              </div>
            )}
          </section>
          <section className={styles.insight}>
            <InfoCircleFilled /> B 层（缺口探查）和 C
            层（疑点澄清）来自匹配分析结果，是本次面试最需要确认的内容。
          </section>
        </div>
        <footer className={styles.dialogFooter}>
          <Checkbox
            checked={saveTemplate}
            onChange={(event) => setSaveTemplate(event.target.checked)}
          >
            同时保存为该岗位的题库模板
          </Checkbox>
          <div>
            <Button onClick={close}>取消</Button>
            <Button
              className={styles.generateButton}
              icon={<ThunderboltOutlined />}
              type="primary"
              onClick={() => {
                notice.success(
                  isBatch ? '已开始批量生成 8 份面试题。' : '已开始生成张伟的面试题。',
                );
                navigate('/ai-assistants/hr/interviews/questions');
              }}
            >
              {isBatch ? '批量生成（8 份）' : '开始生成'}
            </Button>
          </div>
        </footer>
      </div>
    </section>
  );
}

function FormGroup({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={styles.formGroup}>
      <h2>{title}</h2>
      {children}
      {hint && <p className={styles.hint}>{hint}</p>}
    </section>
  );
}

function PillGroup({
  options,
  value,
  onChange,
}: {
  options: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className={styles.pillGroup}>
      {options.map((option) => (
        <button
          aria-pressed={value === option}
          className={value === option ? styles.selected : ''}
          key={option}
          onClick={() => onChange(option)}
          type="button"
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function CoverageRow({
  title,
  count,
  description,
  target,
}: {
  title: string;
  count: string;
  description: string;
  target: string;
}) {
  return (
    <div className={styles.coverageRow}>
      <span>◎</span>
      <b>{title}</b>
      <strong>{count}</strong>
      <RightOutlined />
      <em>{target}</em>
      <small>{description}</small>
    </div>
  );
}
