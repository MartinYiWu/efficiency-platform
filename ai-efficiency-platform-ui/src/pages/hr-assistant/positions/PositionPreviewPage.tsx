import { CheckCircleFilled, InfoCircleFilled, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Progress, Select, Table, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionPreviewPage.module.css';

const results = [
  ['张**', '88.5', '强烈推荐面试', '92', '85', '90', '4/4 通过'],
  ['李**', '79.0', '推荐面试', '85', '78', '76', '4/4 通过'],
  ['王**', '72.5', '推荐面试', '80', '70', '72', '4/4 通过'],
  ['刘**', '68.0', '推荐面试', '75', '68', '62', '3/4 通过 1 临界'],
  ['陈**', '58.0', '建议复核', '62', '55', '58', '4/4 通过'],
  ['周**', '—', '暂不推荐', '—', '—', '—', '2/4 通过'],
];
const gradeClass = (grade: string) =>
  grade.includes('强烈')
    ? styles.strong
    : grade === '推荐面试'
      ? styles.recommend
      : grade === '建议复核'
        ? styles.review
        : styles.muted;

export function PositionPreviewPage() {
  const navigate = useNavigate();
  const [notice, contextHolder] = message.useMessage();
  const [sampleSize, setSampleSize] = useState('10');
  const [judgements, setJudgements] = useState([
    '强烈推荐面试',
    '推荐面试',
    '推荐面试',
    '推荐面试',
    '推荐面试',
    '暂不推荐',
  ]);
  const agreement = judgements.filter((item, index) => item === results[index][2]).length;
  const enable = () => notice.success('岗位已启用。本地展示交互不产生真实匹配记录。');
  return (
    <div className={styles.page}>
      {contextHolder}
      <section className={styles.header}>
        <div>
          <Typography.Title level={1}>配置预演</Typography.Title>
          <Typography.Text>
            后端开发工程师（P6）· 用库内已有简历试跑，验证配置是否符合预期
          </Typography.Text>
        </div>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/positions/new/weights')}>
            返回编辑配置
          </Button>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={() => notice.success('已使用当前编辑中的配置重新试跑')}
          >
            重新试跑
          </Button>
        </div>
      </section>
      <Card className={styles.guide}>
        <Typography.Title level={2}>
          <InfoCircleFilled /> 为什么要预演
        </Typography.Title>
        <p>
          配置好的规则是否合理，看文档说明不如直接试跑一遍。建议在批量使用前，先用 10
          份已知质量的简历校准一次。
        </p>
      </Card>
      <Card>
        <div className={styles.settings}>
          <label>
            简历来源
            <Select
              defaultValue="人才库随机 10 份"
              options={['人才库随机 10 份', '指定候选人', '上传新简历'].map((value) => ({
                value,
                label: value,
              }))}
            />
          </label>
          <label>
            样本数量
            <Select
              value={sampleSize}
              onChange={setSampleSize}
              options={['10', '20', '50'].map((value) => ({ value, label: value }))}
            />
          </label>
          <Button type="primary" onClick={() => notice.success(`已完成 ${sampleSize} 份简历试跑`)}>
            开始试跑
          </Button>
        </div>
      </Card>
      <Card title="分数分布" extra="共 10 份 · 试跑于 09-01 10:02">
        <div className={styles.distribution}>
          <span className={styles.strong}>强烈推荐 1</span>
          <span className={styles.recommend}>推荐 3</span>
          <span className={styles.review}>建议复核 4</span>
          <span className={styles.muted}>暂不推荐 2</span>
        </div>
        <div className={styles.diagnosis}>
          <CheckCircleFilled />
          <div>
            <strong>分布合理</strong>
            <p>
              推荐区间（强烈推荐+推荐）占
              40%，符合预期。建议复核区间偏大，可考虑略微下调“建议复核”阈值。
            </p>
          </div>
        </div>
      </Card>
      <Card title="硬性条件过滤情况">
        <Table
          size="small"
          pagination={false}
          rowKey="name"
          dataSource={[
            ['本科及以上学历', 9, 1, 0, '10%'],
            ['3年以上工作经验', 7, 2, 1, '20%'],
            ['必须掌握 Python', 6, 4, 0, '40%'],
            ['工作地点：上海', 8, 2, 0, '20%'],
          ].map(([name, pass, fail, border, rate]) => ({ name, pass, fail, border, rate }))}
          columns={[
            { title: '条件', dataIndex: 'name' },
            { title: '通过', dataIndex: 'pass' },
            { title: '未通过', dataIndex: 'fail' },
            { title: '临界', dataIndex: 'border' },
            {
              title: '过滤率',
              dataIndex: 'rate',
              render: (value) =>
                value === '40%' ? <Tag color="orange">过滤率偏高 40%</Tag> : value,
            },
          ]}
        />
      </Card>
      <Card title="逐份结果">
        <Table
          size="small"
          pagination={false}
          rowKey="key"
          dataSource={results.map((item, index) => ({
            key: index,
            name: item[0],
            score: item[1],
            grade: item[2],
            skill: item[3],
            experience: item[4],
            project: item[5],
            hard: item[6],
          }))}
          columns={[
            { title: '候选人', dataIndex: 'name' },
            { title: '总分', dataIndex: 'score' },
            {
              title: '分档',
              dataIndex: 'grade',
              render: (value) => <Tag className={gradeClass(value)}>{value}</Tag>,
            },
            { title: '技能', dataIndex: 'skill' },
            { title: '经验', dataIndex: 'experience' },
            { title: '项目', dataIndex: 'project' },
            { title: '硬条件', dataIndex: 'hard' },
            { title: '操作', render: () => <Button type="link">查看详情</Button> },
          ]}
        />
      </Card>
      <Card
        className={styles.calibration}
        title="你的判断"
        extra="对比 AI 结果与你的判断，用于校准配置"
      >
        <Typography.Text type="secondary">
          请对上面简历给出自己的分档判断，系统会计算一致率
        </Typography.Text>
        {results.map((result, index) => (
          <div className={styles.judgement} key={result[0]}>
            <strong>{result[0]}</strong>
            <Tag className={gradeClass(result[2])}>{result[2]}</Tag>
            <Select
              value={judgements[index]}
              onChange={(value) =>
                setJudgements((current) =>
                  current.map((item, itemIndex) => (itemIndex === index ? value : item)),
                )
              }
              options={['强烈推荐面试', '推荐面试', '建议复核', '暂不推荐'].map((value) => ({
                value,
                label: value,
              }))}
            />
            <span>{judgements[index] === result[2] ? '✓ 一致' : '✕ 不一致'}</span>
          </div>
        ))}
        <div className={styles.agreement}>
          <strong>一致率 80%（8/10）</strong>
          <Progress percent={80} showInfo={false} />
          <Typography.Text type="secondary">
            当前交互一致率：{agreement}/{results.length}；低于 85% 建议调整配置后重新试跑
          </Typography.Text>
        </div>
      </Card>
      <footer className={styles.footer}>
        <Typography.Text type="secondary">预演结果不会保存为正式匹配记录</Typography.Text>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/positions/new/weights')}>
            调整配置
          </Button>
          <Button type="primary" onClick={enable}>
            配置无误，启用岗位
          </Button>
        </div>
      </footer>
    </div>
  );
}
