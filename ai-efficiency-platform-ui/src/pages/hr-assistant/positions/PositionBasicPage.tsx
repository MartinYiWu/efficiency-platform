import { FileTextOutlined, InfoCircleFilled, SaveOutlined } from '@ant-design/icons';
import { Button, Card, Input, Select, Typography, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './PositionWizardPage.module.css';

const families = [
  '技术研发',
  '产品',
  '设计',
  '运营',
  '市场',
  '销售',
  '职能支持',
  '管理岗',
  '应届生',
];

export function PositionBasicPage() {
  const navigate = useNavigate();
  const [notice, contextHolder] = message.useMessage();
  const [form, setForm] = useState({
    name: '',
    family: undefined as string | undefined,
    department: '',
    level: '',
  });
  const complete = Boolean(form.name && form.family && form.department && form.level);
  const update = (key: keyof typeof form, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

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
            <div className={`${styles.step} ${index === 0 ? styles.current : ''}`} key={title}>
              <span>{index + 1}</span>
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
          <Typography.Title level={1}>基本信息</Typography.Title>
          <div className={styles.infoBar}>
            <InfoCircleFilled />
            请先填写岗位基础信息。岗位族决定后续权重参考值和面试考察模板，创建后不可修改。
          </div>
          <Card className={styles.skillCard}>
            <div className={styles.basicGrid}>
              <label>
                岗位名称<span>*</span>
                <Input
                  aria-label="岗位名称"
                  placeholder="例如：后端开发工程师"
                  value={form.name}
                  onChange={(event) => update('name', event.target.value)}
                />
              </label>
              <label>
                岗位族<span>*</span>
                <Select
                  aria-label="岗位族"
                  placeholder="请选择岗位族"
                  value={form.family}
                  options={families.map((value) => ({ value, label: value }))}
                  onChange={(value) => update('family', value)}
                />
              </label>
              <label>
                所属部门<span>*</span>
                <Input
                  aria-label="所属部门"
                  placeholder="例如：技术中心"
                  value={form.department}
                  onChange={(event) => update('department', event.target.value)}
                />
              </label>
              <label>
                职级<span>*</span>
                <Input
                  aria-label="职级"
                  placeholder="例如：P6"
                  value={form.level}
                  onChange={(event) => update('level', event.target.value)}
                />
              </label>
              <label>
                岗位编码<small>可留空，系统自动生成</small>
                <Input aria-label="岗位编码" placeholder="例如：TECH-001" />
              </label>
            </div>
          </Card>
          <Card className={styles.skillCard}>
            <Typography.Title level={2}>岗位 JD（可选）</Typography.Title>
            <Input.TextArea
              aria-label="岗位JD"
              rows={7}
              placeholder="粘贴岗位职责与任职要求；也可上传 doc、docx、pdf、txt 文件。"
            />
            <div className={styles.jdActions}>
              <Button
                icon={<FileTextOutlined />}
                onClick={() =>
                  notice.info('JD 草案提取将在接口接入后执行；当前仅保存本地展示内容。')
                }
              >
                从 JD 提取配置草案
              </Button>
              <Typography.Text type="secondary">
                JD 原文仅用作配置依据与面试语境，不参与规则计算。
              </Typography.Text>
            </div>
          </Card>
        </section>
        <aside className={styles.tipRail}>
          <Card>
            <Typography.Title level={2}>填写提示</Typography.Title>
            <p>岗位配置用于定义简历匹配规则。建议先和用人经理确认最急招岗位，再进入条件配置。</p>
          </Card>
          <Card>
            <Typography.Title level={2}>岗位族不可修改</Typography.Title>
            <p>岗位族会决定权重参考值、技能模板和面试考察维度。如需换岗位族，请新建岗位。</p>
          </Card>
        </aside>
      </div>
      <footer className={styles.footer}>
        <Button icon={<SaveOutlined />} onClick={() => notice.success('岗位基础信息草稿已保存')}>
          保存草稿
        </Button>
        <div>
          <Button
            type="primary"
            disabled={!complete}
            onClick={() => navigate('/ai-assistants/hr/positions/new/hard-conditions')}
          >
            下一步：硬性条件
          </Button>
        </div>
      </footer>
    </div>
  );
}
