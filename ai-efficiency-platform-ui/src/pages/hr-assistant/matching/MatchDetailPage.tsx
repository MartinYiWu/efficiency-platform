import { CheckCircleFilled, DownloadOutlined, LockOutlined } from '@ant-design/icons';
import { Button, Modal, Progress, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './MatchDetailPage.module.css';

const dimensions = [
  ['技能匹配', 92, 40],
  ['经验匹配', 85, 25],
  ['项目匹配', 90, 25],
  ['学历匹配', 80, 5],
  ['加分项', 60, 5],
];
const evidence = [
  '项目：分布式订单系统重构 — 技术栈 Python / Django / MySQL',
  '工作经历：主导系统重构，使用 Python 优化订单处理链路',
  '专业技能：Python、Django、MySQL、Git、Linux',
];
export function MatchDetailPage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [contact, setContact] = useState(false);
  const [highlight, setHighlight] = useState('点击左侧证据可在此处定位原文');
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div className={styles.person}>
          <i>张</i>
          <div>
            <Typography.Title level={1}>张伟</Typography.Title>
            <span>
              7年3个月 · 上海 · 138****5678　
              <LockOutlined />{' '}
              <Button type="link" onClick={() => setContact(true)}>
                查看完整联系方式
              </Button>
            </span>
          </div>
        </div>
        <div>
          <Button>上一位</Button>
          <Button>下一位</Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/interviews/generate')}>
            生成面试题
          </Button>
        </div>
      </header>
      <section className={styles.scoreCard}>
        <div>
          <b>88.5</b>
          <span>/ 100</span>
          <Tag color="green">强烈推荐面试</Tag>
          <p>高度匹配，建议优先安排面试</p>
        </div>
        <div className={styles.dimensionRow}>
          {dimensions.map(([label, score]) => (
            <span key={String(label)}>
              <Progress
                type="circle"
                percent={Number(score)}
                size={52}
                strokeColor={Number(score) > 85 ? '#16a34a' : '#2563eb'}
              />
              <small>{label}</small>
            </span>
          ))}
        </div>
        <aside>
          匹配于 2026-09-01 09:45
          <br />
          权重版本 v1.2
          <br />
          <Button type="link">查看权重快照</Button>
        </aside>
      </section>
      <div className={styles.ai}>
        ✦　本结果由 AI 辅助生成，仅供参考。最终判断请结合面试与人工评估。
      </div>
      <div className={styles.layout}>
        <nav>
          <b>硬性条件校验</b>
          <b>维度得分明细</b>
          {dimensions.map(([label]) => (
            <span key={String(label)}>├ {label}</span>
          ))}
          <b>匹配理由</b>
          <span>├ 匹配亮点</span>
          <span>├ 能力缺口</span>
          <span className={styles.active}>├ 面试需重点核实</span>
          <span>├ 简历质量提示</span>
          <b>结构化档案</b>
          <b>操作记录</b>
          <section>
            <strong>特殊标记</strong>
            <Tag color="gold">简历质量提示</Tag>
            <small>表述模板化程度较高</small>
          </section>
        </nav>
        <main>
          <section className={styles.block}>
            <h2>
              硬性条件校验 <Tag color="green">4 项全部通过</Tag>
            </h2>
            {[
              ['本科及以上学历', '实际：本科', '期望：本科及以上'],
              ['3年以上工作经验', '实际：7年3个月', '期望：≥36个月'],
              ['必须掌握 Python', '实际：已具备（3处证据）', '期望：Python'],
              ['工作地点：上海', '实际：当前上海', '期望：上海'],
            ].map((row) => (
              <p key={row[0]}>
                <CheckCircleFilled /> <b>{row[0]}</b>
                <span>{row[1]}</span>
                <span>{row[2]}</span>
              </p>
            ))}
          </section>
          <section className={styles.block}>
            <h2>
              维度得分明细 <Button type="link">展开全部证据</Button>
            </h2>
            <article className={styles.dimension}>
              <h3>
                技能匹配 <b>92.0</b> <Tag>40%</Tag> <span>命中 3/4</span>
              </h3>
              <Progress percent={92} strokeColor="#16a34a" />
              <h4>命中 3 项</h4>
              <strong>
                Python　<Tag color="green">强</Tag>　出现 3 处　重要度 10
              </strong>
              {evidence.map((item) => (
                <div className={styles.evidence} key={item}>
                  {item}
                  <Button type="link" onClick={() => setHighlight(item)}>
                    查看原文位置 →
                  </Button>
                </div>
              ))}
              <p className={styles.missing}>
                <b>缺失 1 项　Redis</b>　重要度 5　简历中未体现
                <br />
                <small>缺失不代表候选人不具备，建议在面试中确认</small>
              </p>
            </article>
            {dimensions.slice(1).map(([label, score, weight]) => (
              <article className={styles.fold} key={String(label)}>
                {label} <b>{score}.0</b>
                <Tag>{weight}%</Tag>
                <span>展开⌄</span>
              </article>
            ))}
          </section>
          <section className={styles.block}>
            <h2>
              匹配理由 <Tag color="purple">AI 生成</Tag>
            </h2>
            <Reason
              title="匹配亮点"
              kind="good"
              items={[
                '核心技能命中 3/4：Python、Django、MySQL。其中 Python 在 3 个不同位置出现，证据充分',
                '7年3个月后端开发经验，技术积累充分',
                '主导过分布式订单系统重构，QPS 从 2000 提升至 8000',
                '带过 5 人小组完成支付模块改造，具备技术负责人经验',
              ]}
              onLocate={setHighlight}
            />
            <Reason
              title="能力缺口"
              kind="gap"
              items={[
                '简历中未体现 Redis 相关经验（核心技能要求，重要度 5）',
                '简历中未体现 Kubernetes 经验（加分项）',
              ]}
              onLocate={setHighlight}
            />
            <Reason
              title="面试需重点核实"
              kind="focus"
              items={[
                '“主导系统重构”的具体职责边界',
                'Django 的实际使用深度',
                '2022年3月至6月的 3 个月时间断档',
              ]}
              onLocate={setHighlight}
            />
            <Reason
              title="简历质量提示"
              kind="quality"
              items={[
                '成果描述的量化比例较高，建议在面试中重点验证项目细节的真实性',
                '工作经历时间与教育经历时间存在 3 个月重叠，可能为在校实习期，建议确认',
              ]}
              onLocate={setHighlight}
            />
          </section>
        </main>
        <aside className={styles.resume}>
          <h2>
            原简历 <DownloadOutlined />
          </h2>
          <article>
            <h3>张伟</h3>
            <p>教育经历</p>
            <p>{highlight}</p>
            <p>工作经历：主导系统重构，QPS 从 2000 提升至 8000</p>
            <p>专业技能：Python、Django、MySQL、Git、Linux</p>
          </article>
          <small>点击左侧证据可在此处定位原文</small>
        </aside>
      </div>
      <footer>
        <span>本结果由 AI 辅助生成。AI 不做录用决策，最终判断由面试官和 HR 做出。</span>
        <div>
          <Button icon={<DownloadOutlined />}>导出此份报告</Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/interviews/generate')}>
            生成面试题
          </Button>
        </div>
      </footer>
      <Modal
        open={contact}
        title="查看联系方式"
        okText="确认继续"
        cancelText="取消"
        onCancel={() => setContact(false)}
        onOk={() => {
          setContact(false);
          notice.warning('联系方式查看已记录。');
        }}
      >
        查看联系方式将被记录，确认继续？
      </Modal>
    </div>
  );
}
function Reason({
  title,
  kind,
  items,
  onLocate,
}: {
  title: string;
  kind: string;
  items: string[];
  onLocate: (value: string) => void;
}) {
  return (
    <article className={`${styles.reason} ${styles[kind]}`}>
      <h3>{title}</h3>
      {items.map((item) => (
        <p key={item}>
          ●　{item}
          <Button type="link" onClick={() => onLocate(item)}>
            查看原文 →
          </Button>
        </p>
      ))}
      {kind === 'gap' && (
        <small>“未体现”不等于“不具备”。建议将缺口转化为面试问题，而非直接作为扣分依据。</small>
      )}
      {kind === 'quality' && (
        <small>以上仅为客观特征观察，不构成对候选人的负面评价，也不影响评分。</small>
      )}
    </article>
  );
}
