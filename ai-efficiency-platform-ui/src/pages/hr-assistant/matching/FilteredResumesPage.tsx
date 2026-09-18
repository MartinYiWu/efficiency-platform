import { CheckCircleFilled, ExclamationCircleFilled, LockOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, Modal, Progress, Select, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './FilteredResumesPage.module.css';

const entries = [
  {
    name: '吴磊',
    age: '6年2个月 · 上海',
    letter: '吴',
    condition: '必须掌握 Python',
    actual: '未体现',
    skills: 'Java、Spring Boot、MySQL、Redis、Kafka',
    hint: '具备 Java 后端开发能力，技术栈方向相近',
    pass: '3年以上工作经验、本科及以上学历',
    type: 'normal',
  },
  {
    name: '郑晓',
    age: '2年11个月 · 上海',
    letter: '郑',
    condition: '3年以上工作经验',
    actual: '2年11个月',
    skills: 'Spring Boot、MySQL、Redis',
    hint: '差 1 个月。当前容差设置为 0，如设为 3 个月则可通过',
    pass: '必须掌握 Python、本科及以上学历',
    type: 'borderline',
  },
  {
    name: '何静',
    age: '4年5个月 · 上海',
    letter: '何',
    condition: '必须掌握 Python；本科及以上学历',
    actual: '未具备；大专',
    skills: 'Java、Spring Boot、MySQL',
    hint: '候选人有 4 年 Java 开发经验，主导过日活 20 万系统改造',
    pass: '3年以上工作经验、工作地点：上海',
    type: 'multiple',
  },
  {
    name: '刘洋',
    age: '3年8个月 · 成都',
    letter: '刘',
    condition: '工作地点：上海',
    actual: '当前成都',
    skills: 'Java、MySQL、Docker',
    hint: '具备后端开发经验，可在面试中确认地点意愿',
    pass: 'Python、3年以上工作经验、本科及以上学历',
    type: 'normal',
  },
];
function ReleaseModal({
  open,
  onClose,
  name,
}: {
  open: boolean;
  onClose: () => void;
  name: string;
}) {
  const [reason, setReason] = useState('');
  const [join, setJoin] = useState(true);
  const [notice, context] = message.useMessage();
  return (
    <>
      <Modal
        width={560}
        open={open}
        title="人工放行硬性条件"
        okText="确认放行并重新评分"
        cancelText="取消"
        okButtonProps={{ disabled: !reason.trim() }}
        onCancel={onClose}
        onOk={() => {
          notice.success('已记录放行原因，重新评分任务已提交');
          onClose();
        }}
      >
        {context}
        <Typography.Text type="secondary">
          放行后将重新计算匹配分数，此操作会被完整记录
        </Typography.Text>
        <div className={styles.candidateBar}>
          <i>{name[0]}</i>
          <b>{name}</b>
          <span>6年2个月 · 上海　后端开发工程师（P6）</span>
        </div>
        <h3>选择要放行的条件</h3>
        <div className={styles.releaseLine}>
          <Checkbox defaultChecked>必须掌握 Python</Checkbox>
          <p>
            实际：未具备　|　期望：Python　<Tag color="green">允许放行</Tag>
          </p>
          <small>候选人技能：Java、Spring Boot、MySQL、Redis、Kafka</small>
        </div>
        <div className={`${styles.releaseLine} ${styles.disabled}`}>
          <Checkbox disabled>必须持有 XX 执业资格证</Checkbox>
          <p>
            实际：未具备　|　期望：持有　
            <Tag>
              <LockOutlined /> 不允许放行
            </Tag>
          </p>
          <small>该条件在岗位配置中设置为不可放行</small>
        </div>
        <h3>
          放行原因 <em>*</em>
        </h3>
        <Input.TextArea
          value={reason}
          maxLength={500}
          rows={4}
          onChange={(e) => setReason(e.target.value)}
          placeholder="请说明放行理由，例如：候选人具备 4 年 Java 后端经验，主导过日活 20 万系统改造，技术栈可迁移，值得面试评估"
          showCount
        />
        <div className={styles.warning}>
          放行原因将记录在操作日志中，并在匹配详情页展示。如后续出现招聘争议，此记录是判断依据。
        </div>
        <div className={styles.impact}>
          <b>放行后的预计变化</b>
          <span>
            放行前　<Tag>暂不推荐</Tag>　总分：—
          </span>
          <strong>→</strong>
          <span>
            放行后（预计）　<Tag color="orange">建议复核</Tag>　总分：约 58 分
          </span>
          <small>实际分数以重新计算结果为准</small>
        </div>
        <Checkbox checked={join} onChange={(e) => setJoin(e.target.checked)}>
          同时将该候选人加入人才库
        </Checkbox>
      </Modal>
    </>
  );
}
export function FilteredResumesPage() {
  const navigate = useNavigate();
  const [release, setRelease] = useState<string | null>(null);
  const [notice, context] = message.useMessage();
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div>
          <Typography.Title level={1}>被硬性条件过滤的简历</Typography.Title>
          <Typography.Text>后端开发工程师（P6） · 共 8 份</Typography.Text>
        </div>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/matching')}>返回匹配结果</Button>
          <Button type="primary" onClick={() => notice.info('已打开岗位硬性条件配置')}>
            调整硬性条件
          </Button>
        </div>
      </header>
      <div className={styles.top}>
        <section className={styles.explain}>
          <b>ⓘ　为什么要有这个页面</b>
          <p>
            硬性条件是一票否决，配错一条就会挡掉一批合格候选人。而被挡掉的人根本不会出现在匹配列表中，HR
            往往发现不了。这个页面让你能看到“被挡在门外的人”，判断是否存在误伤。
          </p>
        </section>
        <section className={styles.distribution}>
          <h2>过滤原因统计</h2>
          {[
            ['必须掌握 Python', 4, 50],
            ['3年以上工作经验', 2, 25],
            ['本科及以上学历', 1, 12.5],
            ['工作地点：上海', 1, 12.5],
          ].map(([label, count, percent]) => (
            <div key={String(label)}>
              <span>{label}</span>
              <Progress percent={Number(percent)} showInfo={false} />
              <b>{count} 人</b>
              <small>{percent}%</small>
            </div>
          ))}
        </section>
      </div>
      <section className={styles.tip}>
        “必须掌握 Python”过滤了 50%
        的被挡简历。请确认该条件是否确实为“不满足就不能做这个工作”的硬性要求，还是可以转为软性要求（缺失只扣分、不否决）。
        <Button type="link" onClick={() => notice.success('已转为软性要求，等待重新评分')}>
          转为软性要求
        </Button>
      </section>
      <section className={styles.filters}>
        <Input placeholder="搜索候选人姓名" />
        <Select
          placeholder="过滤原因"
          mode="multiple"
          options={['必须掌握 Python', '3年以上工作经验', '本科及以上学历', '工作地点：上海'].map(
            (value) => ({ value, label: value }),
          )}
        />
        <Select
          defaultValue="按未通过条数"
          options={['按未通过条数', '按上传时间'].map((value) => ({ value, label: value }))}
        />
      </section>
      <div className={styles.list}>
        {entries.map((item) => (
          <article className={`${styles.card} ${styles[item.type]}`} key={item.name}>
            <div className={styles.person}>
              <i>{item.letter}</i>
              <div>
                <h2>{item.name}</h2>
                <span>{item.age}</span>
                <p>后端开发工程师</p>
              </div>
            </div>
            <div className={styles.failure}>
              <b>不满足的硬性条件</b>
              <p>
                <ExclamationCircleFilled />　{item.condition}
                <span>实际：{item.actual}</span>
              </p>
              <small>相似技能：{item.skills}</small>
              <em>{item.hint}</em>
              {item.type === 'borderline' && (
                <Button type="link" onClick={() => notice.info('请在岗位条件中设置容差')}>
                  设置容差
                </Button>
              )}
            </div>
            <div className={styles.passed}>
              <b>通过情况（满足的硬性条件）</b>
              <p>
                <CheckCircleFilled /> {item.pass}
              </p>
            </div>
            <div className={styles.actions}>
              <Button onClick={() => setRelease(item.name)}>人工放行此条件并评分</Button>
              <Button type="link" onClick={() => navigate('/ai-assistants/hr/talent/zhang-wei')}>
                查看简历
              </Button>
              <Button type="link" onClick={() => notice.success('已加入人才库')}>
                加入人才库
              </Button>
            </div>
          </article>
        ))}
      </div>
      <footer>
        ⓘ　所有被过滤的简历都保留在系统中，不会被删除。你可以随时人工放行某个条件后重新评分，或将候选人加入人才库供其他岗位使用。
      </footer>
      <ReleaseModal open={!!release} name={release ?? ''} onClose={() => setRelease(null)} />
    </div>
  );
}
