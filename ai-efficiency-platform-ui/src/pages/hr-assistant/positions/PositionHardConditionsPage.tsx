import { DeleteOutlined, InfoCircleFilled, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import { Button, Card, Input, InputNumber, Select, Switch, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionWizardPage.module.css';

type Condition = { type: string; requirement: string; tolerance?: number; releasable: boolean };
const allowedTypes = [
  '学历层次',
  '工作年限',
  '必备技能',
  '工作地域',
  '资质证书',
  '语言能力',
  '项目规模',
  '团队规模',
];
const initial: Condition[] = [
  { type: '学历层次', requirement: '本科及以上', tolerance: 1, releasable: true },
  { type: '工作年限', requirement: '3 年及以上', tolerance: 3, releasable: true },
  { type: '必备技能', requirement: 'Python', releasable: false },
];

export function PositionHardConditionsPage() {
  const navigate = useNavigate();
  const [notice, contextHolder] = message.useMessage();
  const [conditions, setConditions] = useState(initial);
  const add = () =>
    setConditions((current) => [
      ...current,
      { type: '工作地域', requirement: '上海', releasable: true },
    ]);
  const update = (index: number, patch: Partial<Condition>) =>
    setConditions((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  return (
    <div className={styles.page}>
      {contextHolder}
      <aside className={styles.stepPanel} aria-label="岗位配置步骤">
        <div className={styles.stepList}>
          {[
            ['基本信息', '填写岗位基础信息'],
            ['硬性条件', '设置必备条件'],
            ['软性要求', '设置加权评分项'],
            ['权重与分档', '设置权重与评分档位'],
            ['预演与保存', '预览评分与保存岗位'],
          ].map(([title, detail], index) => (
            <div
              className={`${styles.step} ${index < 1 ? styles.done : index === 1 ? styles.current : ''}`}
              key={title}
            >
              <span>{index < 1 ? '✓' : index + 1}</span>
              <div>
                <strong>{title}</strong>
                <small>{detail}</small>
              </div>
            </div>
          ))}
        </div>
      </aside>
      <div className={styles.body}>
        <section className={styles.formArea}>
          <Typography.Title level={1}>硬性条件</Typography.Title>
          <div className={styles.infoBar}>
            <InfoCircleFilled />
            硬性条件不满足时不进入评分。仅配置确实不满足就不能做该工作的条件。
          </div>
          <Card className={styles.skillCard}>
            <Typography.Title level={2}>必备条件</Typography.Title>
            {conditions.map((condition, index) => (
              <div className={styles.conditionRow} key={`${condition.type}-${index}`}>
                <Select
                  value={condition.type}
                  options={allowedTypes.map((value) => ({ value, label: value }))}
                  onChange={(value) => update(index, { type: value })}
                />
                <Input
                  value={condition.requirement}
                  onChange={(event) => update(index, { requirement: event.target.value })}
                />
                {['学历层次', '工作年限', '语言能力', '项目规模', '团队规模'].includes(
                  condition.type,
                ) ? (
                  <InputNumber
                    aria-label={`${condition.type}容差`}
                    value={condition.tolerance ?? 0}
                    min={0}
                    onChange={(value) => update(index, { tolerance: Number(value ?? 0) })}
                  />
                ) : (
                  <span>不提供容差</span>
                )}
                <label>
                  <Switch
                    checked={condition.releasable}
                    disabled={condition.type === '必备技能' || condition.type === '资质证书'}
                    onChange={(releasable) => update(index, { releasable })}
                  />
                  {condition.releasable ? '允许人工放行' : '不可放行'}
                </label>
                <Button
                  type="text"
                  aria-label={`删除${condition.type}`}
                  icon={<DeleteOutlined />}
                  onClick={() =>
                    setConditions((current) => current.filter((_, item) => item !== index))
                  }
                />
              </div>
            ))}
            <Button
              className={styles.addSkill}
              type="dashed"
              block
              icon={<PlusOutlined />}
              onClick={add}
            >
              添加硬性条件
            </Button>
          </Card>
          <Card className={styles.skillCard}>
            <Typography.Title level={2}>配置边界</Typography.Title>
            <div className={styles.boundaries}>
              <Tag color="blue">同一类型只能配置一条</Tag>
              <Tag color="gold">数值型容差仅向下放宽</Tag>
              <Tag>必备技能、资质证书默认不可放行</Tag>
            </div>
            <Typography.Text type="secondary">
              系统不提供性别、年龄、婚育、籍贯、民族、健康等受保护特征的筛选入口。
            </Typography.Text>
          </Card>
        </section>
        <aside className={styles.tipRail}>
          <Card>
            <Typography.Title level={2}>为什么要少配硬性条件</Typography.Title>
            <p>硬性条件是一票否决项。配置过多会挡掉大量合格候选人，建议控制在 5 条以内。</p>
          </Card>
          <Card>
            <Typography.Title level={2}>容差说明</Typography.Title>
            <p>工作年限等数值型条件可向下放宽；落在容差内会标记“临界”，供面试重点核实。</p>
          </Card>
        </aside>
      </div>
      <footer className={styles.footer}>
        <Button icon={<SaveOutlined />} onClick={() => notice.success('硬性条件草稿已保存')}>
          保存草稿
        </Button>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/positions/new')}>上一步</Button>
          <Button
            type="primary"
            disabled={conditions.length === 0}
            onClick={() => navigate('/ai-assistants/hr/positions/new/soft-requirements')}
          >
            下一步：软性要求
          </Button>
        </div>
      </footer>
    </div>
  );
}
