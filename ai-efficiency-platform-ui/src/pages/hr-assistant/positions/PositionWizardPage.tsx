import { DeleteOutlined, InfoCircleFilled, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import { Button, Card, Input, InputNumber, Radio, Slider, Tag, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionWizardPage.module.css';

type Skill = [string, number, number];

const initialSkills: Skill[] = [
  ['Python', 60, 10],
  ['Django', 48, 8],
  ['MySQL', 36, 6],
  ['Redis', 30, 5],
  ['消息队列', 24, 4],
];
const steps = [
  ['基本信息', '填写岗位基础信息'],
  ['硬性条件', '设置必备条件'],
  ['软性要求', '设置加权评分项'],
  ['权重与分档', '设置权重与评分档位'],
  ['预演与保存', '预览评分与保存岗位'],
];

export function PositionWizardPage() {
  const navigate = useNavigate();
  const [skills, setSkills] = useState(initialSkills);
  const [bonusSkills, setBonusSkills] = useState(['Kubernetes', 'Docker', '微服务架构']);
  const [projectRole, setProjectRole] = useState('lead');
  const [notice, contextHolder] = message.useMessage();

  const addSkill = () => setSkills((current) => [...current, ['新技能', 30, 3]]);
  const removeSkill = (index: number) =>
    setSkills((current) => current.filter((_, item) => item !== index));
  const saveDraft = () => notice.success('岗位配置草稿已保存，可随时继续配置');

  return (
    <div className={styles.page}>
      {contextHolder}
      <aside className={styles.stepPanel} aria-label="岗位配置步骤">
        <div className={styles.stepList}>
          {steps.map(([title, description], index) => (
            <div
              className={`${styles.step} ${index < 2 ? styles.done : index === 2 ? styles.current : ''}`}
              key={title}
            >
              <span>{index < 2 ? '✓' : index + 1}</span>
              <div>
                <strong>{title}</strong>
                <small>{description}</small>
              </div>
            </div>
          ))}
        </div>
        <div className={styles.templateSummary}>
          <span>已选模板：</span>
          <strong>技术研发 / 后端开发</strong>
          <Button type="link">更换模板 →</Button>
        </div>
      </aside>

      <div className={styles.body}>
        <section className={styles.formArea}>
          <Typography.Title level={1}>软性要求</Typography.Title>
          <div className={styles.infoBar}>
            <InfoCircleFilled />
            软性要求进入加权评分。未满足不会一票否决，只影响得分。
          </div>
          <Card className={styles.skillCard}>
            <Typography.Title level={2}>核心技能（建议 3-6 项）</Typography.Title>
            <div className={styles.skillHeader}>
              <span>技能名称</span>
              <span>期望程度（建议分值）</span>
              <span>权重分值</span>
              <span>操作</span>
            </div>
            {skills.map(([name, level, weight], index) => (
              <div className={styles.skillRow} key={`${name}-${index}`}>
                <span className={styles.drag}>⠿</span>
                <Input
                  aria-label={`技能名称-${index + 1}`}
                  value={name}
                  onChange={(event) =>
                    setSkills((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? [event.target.value, item[1], item[2]] : item,
                      ),
                    )
                  }
                />
                <Slider
                  value={level}
                  tooltip={{ open: false }}
                  onChange={(value) =>
                    setSkills((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? [item[0], value, item[2]] : item,
                      ),
                    )
                  }
                />
                <InputNumber
                  aria-label={`权重分值-${index + 1}`}
                  min={1}
                  value={weight}
                  onChange={(value) =>
                    setSkills((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? [item[0], item[1], Number(value ?? 1)] : item,
                      ),
                    )
                  }
                />
                <Button
                  type="text"
                  aria-label={`删除${name}`}
                  icon={<DeleteOutlined />}
                  onClick={() => removeSkill(index)}
                />
              </div>
            ))}
            <Button
              className={styles.addSkill}
              type="dashed"
              block
              icon={<PlusOutlined />}
              onClick={addSkill}
            >
              添加技能
            </Button>
            <div className={styles.bonus}>
              <strong>加分技能（可多选）</strong>
              {bonusSkills.map((skill) => (
                <Tag
                  key={skill}
                  closable
                  onClose={() =>
                    setBonusSkills((current) => current.filter((item) => item !== skill))
                  }
                >
                  {skill}
                </Tag>
              ))}
              <Button
                size="small"
                onClick={() => setBonusSkills((current) => [...current, '新加分技能'])}
              >
                ＋ 添加
              </Button>
            </div>
          </Card>
          <Card className={styles.expectationCard}>
            <div>
              <Typography.Title level={2}>经验期望</Typography.Title>
              <span>工作年限</span>
              <div>
                <InputNumber value={3} readOnly /> 至 <InputNumber value={6} readOnly /> 年
              </div>
              <span>期望行业（可多选）</span>
              <div>
                <Tag>互联网</Tag>
                <Tag>金融科技</Tag>
              </div>
              <span>技术方向（可多选）</span>
              <div>
                <Tag>后端</Tag>
                <Tag>服务端</Tag>
                <Tag>平台</Tag>
              </div>
            </div>
            <div>
              <Typography.Title level={2}>项目期望</Typography.Title>
              <span>项目关键词（可多选）</span>
              <div>
                <Tag>高并发</Tag>
                <Tag>分布式</Tag>
                <Tag>微服务</Tag>
                <Tag>系统重构</Tag>
              </div>
              <span>项目角色期望</span>
              <Radio.Group
                value={projectRole}
                onChange={(event) => setProjectRole(event.target.value)}
              >
                <Radio value="lead">需主导过</Radio>
                <Radio value="participate">参与过即可</Radio>
                <Radio value="aware">了解即可</Radio>
              </Radio.Group>
            </div>
          </Card>
        </section>
        <aside className={styles.tipRail}>
          <Card>
            <Typography.Title level={2}>
              <InfoCircleFilled /> 为什么要区分核心与加分
            </Typography.Title>
            <p>
              核心技能是岗位的关键胜任项，建议分值较高；加分技能是锦上添花的能力项，可提升综合得分。
            </p>
          </Card>
          <Card>
            <Typography.Title level={2}>模板参考</Typography.Title>
            <strong>技术研发族 · 后端开发</strong>
            <ul>
              <li>核心技能：Python、Django、MySQL、Redis、消息队列</li>
              <li>加分技能：Kubernetes、Docker、微服务架构</li>
              <li>经验期望：3-6 年</li>
              <li>项目期望：高并发、分布式、微服务</li>
            </ul>
            <Button type="link">查看模板详情 →</Button>
          </Card>
          <Card>
            <Typography.Title level={2}>填写进度</Typography.Title>
            <strong>
              已填 <em>5 / 5</em> 项
            </strong>
            <div className={styles.progress}>
              <span />
            </div>
            <p>软性要求填写完整，请点击“下一步”继续</p>
          </Card>
        </aside>
      </div>
      <footer className={styles.footer}>
        <Button icon={<SaveOutlined />} onClick={saveDraft}>
          保存草稿
        </Button>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/positions')}>上一步</Button>
          <Button
            type="primary"
            onClick={() => navigate('/ai-assistants/hr/positions/new/weights')}
          >
            下一步：权重与分档
          </Button>
        </div>
      </footer>
    </div>
  );
}
