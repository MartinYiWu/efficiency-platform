import { DownloadOutlined, LockOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Button, Modal, Progress, Tabs, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './CandidateProfilePage.module.css';

const skills = [
  ['Python', '编程语言', '强', '3 处'],
  ['Django', '框架', '中', '2 处'],
  ['MySQL', '数据库', '中', '2 处'],
  ['Git', '工具', '弱', '1 处'],
  ['Linux', '工具', '弱', '1 处'],
  ['RabbitMQ', '中间件', '弱', '1 处'],
];

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.card}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function StructuredProfile({ onEdit }: { onEdit: () => void }) {
  return (
    <div className={styles.structured}>
      <Button type="link" className={styles.edit} onClick={onEdit}>
        修正档案信息
      </Button>
      <section className={styles.profileSection}>
        <h2>🎓　教育经历</h2>
        <div className={styles.timeline}>
          <b>2014.09 - 2018.06</b>
          <span>某大学　计算机科学与技术　本科　全日制</span>
        </div>
      </section>
      <section className={styles.profileSection}>
        <h2>💼　工作经历</h2>
        <div className={styles.timeline}>
          <b>2022.06 - 至今</b>
          <article>
            <h3>
              某科技公司 <Tag>互联网</Tag>
            </h3>
            <strong>高级后端开发工程师</strong>
            <p>负责核心业务系统后端服务设计与开发，主导系统架构优化与性能提升。</p>
            <p>
              带领 <em>5</em> 人小组完成支付模块改造，交易成功率提升至 <em>99.95%</em>。
            </p>
            <p>
              主导缓存架构调整，接口平均响应时间下降 <em>40%</em>。
            </p>
          </article>
        </div>
        <div className={styles.gap}>2022.03 - 2022.06 存在 3 个月断档</div>
        <div className={styles.timeline}>
          <b>2018.07 - 2022.03</b>
          <article>
            <h3>某互联网公司</h3>
            <strong>后端开发工程师</strong>
            <p>参与电商平台核心模块开发，负责订单、支付等关键链路后端实现。</p>
            <p>
              支撑大促期间订单峰值 QPS 从 <em>2000</em> 提升至 <em>8000</em>。
            </p>
          </article>
        </div>
      </section>
      <section className={styles.profileSection}>
        <h2>🗂　项目经历</h2>
        <article className={styles.project}>
          <h3>
            分布式订单系统重构 <Tag color="orange">职责边界待核实</Tag>
          </h3>
          <span>
            角色：主导　团队规模 8 人　规模指标 <em>QPS 2000 → 8000</em>
          </span>
          <p>针对订单系统性能瓶颈，重新设计分布式架构与数据存储方案。</p>
          <p>
            项目成果：订单系统吞吐量提升 <em>300%</em>，QPS 从 <em>2000</em> 提升至 <em>8000</em>。
          </p>
          <div>
            {['Python', 'Django', 'MySQL', 'RabbitMQ'].map((skill) => (
              <Tag key={skill}>{skill}</Tag>
            ))}
          </div>
        </article>
      </section>
      <section className={styles.profileSection}>
        <h2>⌘　技能</h2>
        <div className={styles.skillTable}>
          <b>技能名</b>
          <b>类别</b>
          <b>证据强度</b>
          <b>出现次数</b>
          <b>证据</b>
          {skills.flatMap(([name, type, strength, count]) => [
            <span key={`${name}-n`}>
              {name}
              {name === 'RabbitMQ' && <Tag color="orange">未归一</Tag>}
            </span>,
            <span key={`${name}-t`}>{type}</span>,
            <Tag
              key={`${name}-s`}
              color={strength === '强' ? 'green' : strength === '中' ? 'blue' : 'default'}
            >
              {strength}
            </Tag>,
            <span key={`${name}-c`}>{count}</span>,
            <Button key={`${name}-b`} type="link">
              展开⌄
            </Button>,
          ])}
        </div>
      </section>
      <section className={styles.derived}>
        <h2>
          衍生信息 <small>（由 AI 解析）</small>
        </h2>
        <span>
          工作年限 <b>7年3个月</b>
        </span>
        <span>
          行业经验 <b>互联网</b>
        </span>
        <span>
          职能方向 <b>后端开发</b>
        </span>
        <span>
          技术领域 <b>后端开发</b>
        </span>
        <span>
          项目规模 <b>中大型</b>
        </span>
        <span>
          团队规模 <b>4-10人</b>
        </span>
        <span>
          工作地点偏好 <b>上海</b>
        </span>
        <span>
          出差/驻场 <b>不明确</b>
        </span>
      </section>
      <section className={styles.profileSection}>
        <h2>
          证书与语言 <small>（由 AI 解析）</small>
        </h2>
        <p>证书：暂无识别到相关证书</p>
        <p>语言：英语（读写：良好）</p>
      </section>
    </div>
  );
}

export function CandidateProfilePage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [contactOpen, setContactOpen] = useState(false);
  const [contact, setContact] = useState<'phone' | 'email'>('phone');
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    if (!revealed) return undefined;
    const timer = window.setTimeout(() => setRevealed(false), 30_000);
    return () => window.clearTimeout(timer);
  }, [revealed]);
  const requestContact = (target: 'phone' | 'email') => {
    setContact(target);
    setContactOpen(true);
  };
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div className={styles.avatar}>张</div>
        <div className={styles.person}>
          <Typography.Title level={1}>张伟</Typography.Title>
          <Typography.Text>7年3个月经验　·　上海　·　首次入库 2026-09-01</Typography.Text>
        </div>
        <div className={styles.headerActions}>
          <Button onClick={() => notice.info('请选择岗位后发起匹配')}>匹配其他岗位</Button>
          <Button icon={<DownloadOutlined />} onClick={() => notice.success('原简历下载已开始')}>
            下载原简历
          </Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/matching')}>
            查看匹配结果
          </Button>
        </div>
      </header>
      <div className={styles.body}>
        <aside className={styles.sidebar}>
          <Card title="基本信息">
            <dl>
              <dt>姓名</dt>
              <dd>张伟</dd>
              <dt>手机</dt>
              <dd>
                <LockOutlined /> {revealed ? '13812345678' : '138****5678'}{' '}
                <Button type="link" onClick={() => requestContact('phone')}>
                  查看
                </Button>
              </dd>
              <dt>邮箱</dt>
              <dd>
                <LockOutlined /> {revealed ? 'zhangwei@example.com' : 'z***@example.com'}{' '}
                <Button type="link" onClick={() => requestContact('email')}>
                  查看
                </Button>
              </dd>
              <dt>当前城市</dt>
              <dd>上海</dd>
              <dt>期望城市</dt>
              <dd>上海</dd>
              <dt>当前状态</dt>
              <dd>
                <Tag color="green">在职看机会</Tag>
              </dd>
            </dl>
            <p className={styles.hint}>ⓘ 查看完整联系方式将被记录</p>
          </Card>
          <Card title="简历版本">
            <p>
              <b>v2（当前）</b>
              <span>2026-09-01</span>
              <Button type="link">查看</Button>
            </p>
            <p>
              <b>v1（历史）</b>
              <span>2026-08-15</span>
              <Button type="link">查看</Button>
              <Button type="link">对比</Button>
            </p>
            <small>同一候选人的多次投递会自动合并为版本</small>
          </Card>
          <Card title="匹配记录">
            <p>
              高级后端开发工程师（P6）<Tag color="green">强烈推荐</Tag>
              <b>88.5</b>
            </p>
            <p>
              后端开发工程师（P5）<Tag color="blue">推荐面试</Tag>
              <b>86.0</b>
            </p>
            <Button type="link" onClick={() => navigate('/ai-assistants/hr/matching')}>
              查看全部匹配记录
            </Button>
          </Card>
          <Card title="解析质量">
            <div className={styles.qualityScore}>
              <span>解析质量评分</span>
              <b>94%</b>
            </div>
            <Progress percent={94} showInfo={false} strokeColor="#16a34a" />
            <p>
              人工修正 <b>2 处</b>
              <Button type="link" onClick={() => notice.info('已打开修正记录')}>
                查看修正记录
              </Button>
            </p>
            <small>解析于 09-01 09:42</small>
          </Card>
        </aside>
        <main className={styles.main}>
          <Tabs
            defaultActiveKey="profile"
            items={[
              {
                key: 'profile',
                label: '结构化档案',
                children: (
                  <StructuredProfile
                    onEdit={() =>
                      navigate('/ai-assistants/hr/resumes/candidates/zhang-wei/confirm')
                    }
                  />
                ),
              },
              {
                key: 'original',
                label: '原简历',
                children: <div className={styles.empty}>原简历预览将在此处展示。</div>,
              },
              {
                key: 'matching',
                label: '匹配记录',
                children: <div className={styles.empty}>可查看候选人与不同岗位的匹配记录。</div>,
              },
              {
                key: 'audit',
                label: '操作日志',
                children: <div className={styles.empty}>档案查看、修正和导出操作均会被记录。</div>,
              },
            ]}
          />
        </main>
      </div>
      <footer className={styles.footer}>
        <span>
          ⓘ 档案信息由 AI 解析生成，含 2 处人工修正　<Button type="link">查看修正记录</Button>
        </span>
        <div>
          <Button icon={<DownloadOutlined />} onClick={() => notice.success('档案导出任务已创建')}>
            导出档案
          </Button>
          <Button type="primary" onClick={() => notice.info('请选择岗位后发起匹配')}>
            匹配其他岗位
          </Button>
        </div>
      </footer>
      <Modal
        open={contactOpen}
        title="查看完整联系方式"
        okText="确认查看"
        cancelText="取消"
        onCancel={() => setContactOpen(false)}
        onOk={() => {
          setContactOpen(false);
          setRevealed(true);
          notice.warning(
            `${contact === 'phone' ? '完整手机号' : '完整邮箱'}已展示 30 秒，查看行为已记录。`,
          );
        }}
      >
        <SafetyCertificateOutlined /> 查看完整联系方式将记录操作人、时间与字段名称，并在 30
        秒后恢复脱敏显示。
      </Modal>
    </div>
  );
}
