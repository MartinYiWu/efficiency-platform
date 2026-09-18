import {
  CheckCircleFilled,
  CloseCircleFilled,
  CloudUploadOutlined,
  ExclamationCircleOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  LoadingOutlined,
  PauseCircleFilled,
  StopOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { Button, Modal, Progress, Segmented, Switch, Tag, Typography, message } from 'antd';
import { Fragment, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import styles from './ResumeProgressPage.module.css';

type Filter = '全部(19)' | '成功(10)' | '待确认(2)' | '失败(1)';

const rows = [
  {
    key: '1',
    file: '张伟_后端开发工程师_P6.pdf',
    name: '张伟',
    kind: 'done',
    confidence: '94%',
    score: '88.5',
    tier: '强烈推荐面试',
    time: '18.2s',
  },
  {
    key: '2',
    file: '李静_后端开发工程师_P6.pdf',
    name: '李静',
    kind: 'done',
    confidence: '91%',
    score: '82.0',
    tier: '强烈推荐面试',
    time: '16.4s',
  },
  {
    key: '3',
    file: '王强_后端开发工程师_P6.pdf',
    name: '王强',
    kind: 'confirm',
    confidence: '68%',
    score: '72.3',
    tier: '推荐面试',
    time: '22.6s',
  },
  {
    key: '4',
    file: '刘敏简历.png',
    name: '—',
    kind: 'working',
    confidence: '—',
    score: '—',
    tier: '—',
    time: '—',
  },
  {
    key: '5',
    file: '陈浩.pdf',
    name: '—',
    kind: 'failed',
    confidence: '—',
    score: '—',
    tier: '—',
    time: '5.1s',
  },
  {
    key: '6',
    file: '赵磊_产品经理.pdf',
    name: '赵磊',
    kind: 'done',
    confidence: '89%',
    score: '—',
    tier: '疑似重复',
    time: '11s',
    detail: 'merge',
  },
];

const logs = [
  ['10:24:31', '解析成功', '张伟_后端开发工程师_P6.pdf   置信度 94%｜耗时 18.2s'],
  ['10:24:28', '解析中', '刘敏_后端开发工程师_P6.jpg   第 2 页 / 共 3 页｜预计剩余 67%'],
  ['10:24:25', '待人工确认', '王强_后端开发工程师_P6.pdf   置信度 68%｜耗时 22.6s'],
  ['10:24:22', '解析成功', '李静_后端开发工程师_P6.pdf   置信度 91%｜耗时 16.4s'],
  ['10:24:19', '解析失败', '陈浩_后端开发工程师_P6.pdf   格式异常｜耗时 5.1s'],
  ['10:24:15', '排队中', '赵磊_后端开发工程师_P6.pdf   等待解析…'],
];

function Status({ kind, label }: { kind: string; label?: string }) {
  const data = {
    done: ['解析成功', <CheckCircleFilled />],
    confirm: ['待人工确认', <UserOutlined />],
    working: ['解析中', <LoadingOutlined spin />],
    failed: ['解析失败', <CloseCircleFilled />],
    waiting: ['排队中（疑似重复）', <PauseCircleFilled />],
  }[kind] ?? ['—', null];
  return (
    <span className={styles[`status${kind[0].toUpperCase()}${kind.slice(1)}`]}>
      {data[1]} {label ?? data[0]}
    </span>
  );
}

export function ResumeProgressPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [filter, setFilter] = useState<Filter>('全部(19)');
  const [autoScroll, setAutoScroll] = useState(true);
  const [abortOpen, setAbortOpen] = useState(false);
  const [notice, context] = message.useMessage();
  const isCompleted = searchParams.get('state') === 'completed';
  const visibleRows =
    filter === '全部(19)'
      ? rows
      : filter.startsWith('成功')
        ? rows.filter((r) => r.kind === 'done')
        : filter.startsWith('待确认')
          ? rows.filter((r) => r.kind === 'confirm')
          : rows.filter((r) => r.kind === 'failed');
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div>
          <Typography.Title level={1}>解析进度</Typography.Title>
          <Typography.Text>批次 20260901-001　·　目标岗位：后端开发工程师（P6）</Typography.Text>
        </div>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/resumes/upload')}>返回列表</Button>
          <Button
            aria-label="中止解析"
            danger
            icon={<StopOutlined />}
            onClick={() => setAbortOpen(true)}
          >
            中止解析
          </Button>
          <Button
            aria-label="继续上传"
            type="primary"
            icon={<CloudUploadOutlined />}
            onClick={() => navigate('/ai-assistants/hr/resumes/upload')}
          >
            继续上传
          </Button>
        </div>
      </header>
      {isCompleted ? (
        <section className={styles.completedCard} aria-label="批次解析完成">
          <CheckCircleFilled />
          <div>
            <Typography.Title level={2}>解析完成</Typography.Title>
            <Typography.Text>
              共 19 份 · 成功 16 · 待确认 2 · 失败 1 · 总耗时 4 分 12 秒
            </Typography.Text>
          </div>
          <div>
            <Button
              onClick={() => navigate('/ai-assistants/hr/resumes/candidates/wang-qiang/confirm')}
            >
              处理待确认项（2）
            </Button>
            <Button type="primary" onClick={() => navigate('/ai-assistants/hr/matching')}>
              查看匹配结果
            </Button>
          </div>
        </section>
      ) : (
        <section className={styles.progressCard}>
          <div className={styles.mainProgress}>
            <strong aria-label="解析进度 12 / 19">
              12 <small>/ 19　份已完成</small>
            </strong>
            <Progress percent={63} strokeColor="#1677ff" />
            <span>预计剩余 2 分 30 秒</span>
          </div>
          {[
            ['解析成功', '10', 'done'],
            ['待人工确认', '2', 'confirm'],
            ['解析中', '5', 'working'],
            ['排队中', '1', 'waiting'],
            ['失败', '1', 'failed'],
          ].map(([label, value, kind]) => (
            <div className={styles.stat} key={label}>
              <Status kind={kind} />
              <b>{value}</b>
            </div>
          ))}
        </section>
      )}
      <section className={styles.log}>
        <div>
          <b>实时解析日志</b>
          <span>
            自动滚动 <Switch size="small" checked={autoScroll} onChange={setAutoScroll} />
          </span>
        </div>
        {logs.map(([time, kind, text]) => (
          <p key={time}>
            <time>{time}</time>
            <Status
              kind={
                kind === '解析成功'
                  ? 'done'
                  : kind === '待人工确认'
                    ? 'confirm'
                    : kind === '解析中'
                      ? 'working'
                      : kind === '解析失败'
                        ? 'failed'
                        : 'waiting'
              }
            />{' '}
            {text}
          </p>
        ))}
      </section>
      <section className={styles.details}>
        <div className={styles.detailsHead}>
          <Typography.Title level={2}>文件明细</Typography.Title>
          <Segmented<Filter>
            value={filter}
            options={['全部(19)', '成功(10)', '待确认(2)', '失败(1)']}
            onChange={setFilter}
          />
        </div>
        <div className={styles.tableWrap} role="table" aria-label="解析文件明细">
          <div className={styles.tableRow} role="row">
            <b>文件名</b>
            <b>候选人</b>
            <b>状态</b>
            <b>置信度</b>
            <b>匹配得分</b>
            <b>分档</b>
            <b>耗时</b>
            <b>操作</b>
          </div>
          {visibleRows.map((r) => (
            <Fragment key={r.key}>
              <div className={styles.tableRow} role="row">
                <span className={styles.file}>
                  {r.file.endsWith('.jpg') ? <FileImageOutlined /> : <FilePdfOutlined />}
                  {r.file}
                </span>
                <span>{r.name}</span>
                <Status
                  kind={r.kind}
                  label={r.kind === 'done' ? '已完成' : r.kind === 'working' ? '识别中' : undefined}
                />
                <span>{r.confidence}</span>
                <span>{r.score}</span>
                <span>
                  {r.tier === '—' ? (
                    '—'
                  ) : (
                    <Tag color={r.tier.includes('强烈') ? 'green' : 'blue'}>{r.tier}</Tag>
                  )}
                </span>
                <span>{r.time}</span>
                <span>
                  {r.kind === 'confirm' ? (
                    <Button
                      type="link"
                      onClick={() =>
                        navigate('/ai-assistants/hr/resumes/candidates/wang-qiang/confirm')
                      }
                    >
                      去确认
                    </Button>
                  ) : r.kind === 'failed' ? (
                    <>
                      <Button type="link" onClick={() => notice.info('已加入重试队列')}>
                        重试
                      </Button>
                      <Button
                        type="link"
                        onClick={() => notice.error('文件已加密或损坏，无法提取文本内容。')}
                      >
                        查看原因
                      </Button>
                    </>
                  ) : r.detail === 'merge' ? (
                    <>
                      <Button type="link" onClick={() => notice.info('已打开重复档案对比')}>
                        查看合并建议
                      </Button>
                    </>
                  ) : r.kind === 'working' ? (
                    '第 2 页 / 共 3 页'
                  ) : (
                    <Button
                      type="link"
                      onClick={() => navigate('/ai-assistants/hr/talent/zhang-wei')}
                    >
                      查看详情
                    </Button>
                  )}
                </span>
              </div>
              {r.kind === 'confirm' ? (
                <div className={`${styles.tableDetail} ${styles.confirmBar}`}>
                  <ExclamationCircleOutlined /> 4
                  个字段需要确认：期望城市、团队规模、项目角色、技能归一
                </div>
              ) : r.kind === 'failed' ? (
                <div className={`${styles.tableDetail} ${styles.failBar}`}>
                  失败原因：文件已加密或损坏，无法提取文本内容。建议：请候选人重新提供未加密的文件，或手动录入。
                </div>
              ) : r.detail === 'merge' ? (
                <div className={`${styles.tableDetail} ${styles.mergeBar}`}>
                  与人才库中「赵磊」（上传于
                  08-15）的手机号一致，已自动合并为同一候选人，本次简历记为 v2 版本。
                </div>
              ) : null}
            </Fragment>
          ))}
        </div>
      </section>
      <footer>
        <ExclamationCircleOutlined />{' '}
        解析完成后会自动与目标岗位匹配。待确认项不会阻塞其他简历的处理，你可以稍后集中处理。
      </footer>
      <Modal
        open={abortOpen}
        title="中止解析"
        okText="确认中止"
        cancelText="继续解析"
        onCancel={() => setAbortOpen(false)}
        onOk={() => {
          setAbortOpen(false);
          notice.warning('解析已中止，已完成文件不会受到影响。');
        }}
      >
        中止后，未开始处理的文件将保留在当前批次中；已完成与待人工确认的结果不受影响。
      </Modal>
    </div>
  );
}
