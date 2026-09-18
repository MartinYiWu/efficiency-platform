import { CheckCircleFilled, InfoCircleFilled } from '@ant-design/icons';
import { Button, Card, InputNumber, Slider, Switch, Tag, Typography } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionWeightsPage.module.css';

const labels = ['基本信息', '硬性条件', '软性要求', '权重与分档', '预演与保存'];
const dimensionNames = ['技能匹配', '经验匹配', '项目匹配', '学历匹配', '加分项'];

export function PositionWeightsPage() {
  const navigate = useNavigate();
  const [weights, setWeights] = useState([40, 25, 25, 5, 5]);
  const [thresholds, setThresholds] = useState([80, 65, 50]);
  const total = weights.reduce((sum, value) => sum + value, 0);
  const validThresholds = thresholds[0] > thresholds[1] && thresholds[1] > thresholds[2];
  const canProceed = total === 100 && validThresholds;
  const updateWeight = (index: number, value: number) =>
    setWeights((current) => current.map((item, itemIndex) => (itemIndex === index ? value : item)));

  return (
    <div className={styles.page}>
      <aside className={styles.stepPanel} aria-label="岗位配置步骤">
        {labels.map((label, index) => (
          <div
            className={`${styles.step} ${index < 3 ? styles.done : index === 3 ? styles.current : ''}`}
            key={label}
          >
            <span>{index < 3 ? '✓' : index + 1}</span>
            <div>
              <strong>{label}</strong>
              <small>
                {
                  [
                    '岗位名称、职级、JD',
                    '必须满足的条件',
                    '希望具备的能力',
                    '各维度占比与阈值',
                    '试跑验证配置效果',
                  ][index]
                }
              </small>
            </div>
          </div>
        ))}
      </aside>
      <div className={styles.content}>
        <section>
          <Typography.Title level={1}>权重与分档</Typography.Title>
          <div className={styles.info}>
            <InfoCircleFilled />
            权重决定各维度在总分中的占比。请按本岗位实际情况调整，不要沿用默认值。
          </div>
          <Card>
            <Typography.Title level={2}>维度权重</Typography.Title>
            {weights.map((weight, index) => (
              <div className={styles.weightRow} key={dimensionNames[index]}>
                <strong>{dimensionNames[index]}</strong>
                <Slider value={weight} onChange={(value) => updateWeight(index, value)} />
                <InputNumber
                  value={weight}
                  min={0}
                  max={100}
                  onChange={(value) => updateWeight(index, Number(value ?? 0))}
                />
                <span>%</span>
                <small>
                  {
                    [
                      '核心技能的覆盖与证据强度',
                      '年限拟合、行业与职能相关性',
                      '项目关键词、规模、角色层级',
                      '学历层次与专业相关性',
                      '加分技能、证书、语言',
                    ][index]
                  }
                </small>
              </div>
            ))}
            <div className={total === 100 ? styles.totalGood : styles.totalError}>
              {total === 100 ? <CheckCircleFilled /> : '!'} 合计 {total}%
              {total !== 100 && '，必须调整为 100%'}
            </div>
            {weights[3] > 10 && (
              <div className={styles.warning}>
                学历权重 {weights[3]}% 偏高。建议降至 10% 以内，避免用弱相关变量替代强相关变量。
              </div>
            )}
          </Card>
          <Card className={styles.thresholdCard}>
            <Typography.Title level={2}>分档阈值</Typography.Title>
            {['强烈推荐面试', '推荐面试', '建议复核'].map((label, index) => (
              <label key={label}>
                {label} ≥{' '}
                <InputNumber
                  value={thresholds[index]}
                  min={0}
                  max={100}
                  onChange={(value) =>
                    setThresholds((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? Number(value ?? 0) : item,
                      ),
                    )
                  }
                />{' '}
                分
              </label>
            ))}
            <label>暂不推荐 &lt; {thresholds[2]} 分</label>
            <div className={styles.gradeBar}>
              <span />
              <span />
              <span />
              <span />
            </div>
            {!validThresholds && (
              <div className={styles.warning}>三个分档阈值必须从高到低严格递减。</div>
            )}
          </Card>
          <Card>
            <Typography.Title level={2}>特殊标记开关</Typography.Title>
            <div className={styles.switches}>
              {['需人工复核', '硬条件临界', '简历质量提示', '疑似重复', '特殊背景值得关注'].map(
                (label) => (
                  <label key={label}>
                    <Switch defaultChecked />
                    {label}
                    <small>
                      {label === '需人工复核'
                        ? '解析置信度低或关键字段缺失时标记'
                        : '匹配结果中以提示标签展示，供人工复核'}
                    </small>
                  </label>
                ),
              )}
            </div>
          </Card>
        </section>
        <aside className={styles.rail}>
          <Card>
            <Typography.Title level={2}>权重设置提示</Typography.Title>
            <p>同样是技术研发族，偏架构的高级岗与偏业务的中级岗权重应当不同。</p>
          </Card>
          <Card>
            <Typography.Title level={2}>实时预览</Typography.Title>
            {[
              '技能 88 × 40% = 35.2',
              '经验 85 × 25% = 21.3',
              '项目 78 × 25% = 19.5',
              '学历 80 × 5% = 4.0',
              '加分 40 × 5% = 2.0',
            ].map((item) => (
              <p key={item}>{item}</p>
            ))}
            <strong>
              总分 82.0 <Tag color="blue">推荐面试</Tag>
            </strong>
          </Card>
        </aside>
      </div>
      <footer className={styles.footer}>
        <Button onClick={() => navigate('/ai-assistants/hr/positions/new')}>上一步</Button>
        <Button
          type="primary"
          disabled={!canProceed}
          onClick={() => navigate('/ai-assistants/hr/positions/new/preview')}
        >
          下一步：预演与保存
        </Button>
      </footer>
    </div>
  );
}
