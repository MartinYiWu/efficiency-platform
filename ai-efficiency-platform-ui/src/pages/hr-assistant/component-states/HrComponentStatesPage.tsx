import { CloseOutlined, InfoCircleFilled, LoadingOutlined } from '@ant-design/icons';
import { Button, Empty, Modal, Progress, Skeleton, Typography } from 'antd';
import { useState, type ReactNode } from 'react';

import styles from './HrComponentStatesPage.module.css';

const colors = [
  ['primary', '主色 / 主要操作', '#1677FF'],
  ['success', '成功 / 正向', '#52C41A'],
  ['warning', '警示 / 需关注', '#FA8C16'],
  ['neutral', '中性 / 禁用', '#BFBFBF'],
  ['border', '边框 / 分割线', '#E6E6E6'],
  ['background', '背景 / 页面', '#F5F7FA'],
] as const;
const grades = [
  ['strong', '强烈推荐面试', '匹配度高，建议优先安排面试'],
  ['recommend', '推荐面试', '匹配度良好，建议安排面试'],
  ['review', '建议复核', '存在部分差距，建议复核后再决定'],
  ['muted', '暂不推荐', '匹配度较低，暂不建议面试'],
] as const;
const conditions = [
  ['🎓', '学历要求：本科及以上', '≥', '本科'],
  ['💼', '工作年限：3年及以上', '≥', '4.2年'],
  ['⌖', '期望城市：上海', '=', '上海'],
  ['⌘', '技能要求：Django', '包含', '是'],
  ['▣', '项目经验：电商系统开发', '包含', '是'],
  ['¥', '期望薪资：15K-25K/月', '范围', '20K'],
] as const;
const dimensions = [
  ['◉', '技能匹配', 92, 'blue'],
  ['✖', '经验匹配', 85, 'blue'],
  ['▣', '项目匹配', 90, 'blue'],
  ['🎓', '学历匹配', 80, 'blue'],
  ['♨', '加分项', 60, 'orange'],
] as const;

export function HrComponentStatesPage() {
  const [dialog, setDialog] = useState<'delete' | 'release' | null>(null);
  return (
    <div className={styles.page}>
      <div className={styles.intro}>
        <Typography.Title level={1}>页面：组件与状态规范（PAGE-00）</Typography.Title>
        <Typography.Paragraph>
          本页定义 AI
          人事助手在匹配结果与面试准备场景中的核心组件与状态样式，供设计与研发一致性使用。
        </Typography.Paragraph>
      </div>
      <div className={styles.twoColumn}>
        <Panel title="一、色彩规范">
          <div className={styles.colors}>
            {colors.map(([tone, label, hex]) => (
              <div className={styles.swatch} key={label}>
                <span className={styles[tone]} />
                <strong>{label}</strong>
                <small>{hex}</small>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="二、匹配等级标签（面试建议）">
          <div className={styles.grades}>
            {grades.map(([tone, label, description]) => (
              <div className={styles.gradeRow} key={label}>
                <span className={styles[`grade${tone}`]}>{label}</span>
                <small>{description}</small>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="三、硬性条件判断状态（示例：实际数值展示）">
          <div className={styles.conditionGrid}>
            {conditions.map(([icon, requirement, operator, actual]) => (
              <div className={styles.conditionRow} key={requirement}>
                <span>{icon}</span>
                <span>{requirement}</span>
                <b>{operator}</b>
                <span>{actual}</span>
                <span className={styles.pass}>满足</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="四、维度得分进度条（5项）">
          <div className={styles.dimensionList}>
            {dimensions.map(([icon, label, score, tone]) => (
              <div className={styles.dimensionRow} key={label}>
                <span className={tone === 'orange' ? styles.orangeIcon : styles.blueIcon}>
                  {icon}
                </span>
                <span>{label}</span>
                <Progress
                  percent={score}
                  showInfo={false}
                  strokeColor={tone === 'orange' ? '#fa8c16' : '#1677ff'}
                />
                <b>{score}/100</b>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="五、证据卡片（可点击）">
          <article className={styles.evidenceCard}>
            <div>
              <strong>证据：具备真实的后端开发基础与系统设计实践</strong>
              <span className={styles.confident}>强（HIGH）</span>
            </div>
            <p>
              候选人具备扎实的后端开发基础，熟悉高并发、分布式系统设计与实现。在微服务、数据库优化及缓存等方面有丰富的实践经验。
            </p>
            <Button type="link">查看原文位置 →</Button>
          </article>
        </Panel>
        <Panel title="六、置信度标签">
          <div className={styles.confidenceList}>
            {[
              ['strong', '强（HIGH）', '证据充分，结论可靠'],
              ['recommend', '中（MEDIUM）', '证据一般，结论较可靠'],
              ['muted', '弱（LOW）', '证据不足，结论需谨慎'],
            ].map(([tone, label, description]) => (
              <div className={styles.confidenceRow} key={label}>
                <i className={styles[`dot${tone}`]} />
                <span>{label}</span>
                <small>{description}</small>
                <span className={styles[`grade${tone}`]}>{label}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className={styles.twoColumn}>
        <Panel title="七、按钮组件状态">
          <div className={styles.buttonMatrix}>
            <span />
            <span>主要按钮（实心）</span>
            <span>次要按钮（描边）</span>
            <span>文本按钮（链接）</span>
            {['默认', '悬停', '点击', '禁用'].map((state, index) => (
              <ButtonStateRow key={state} state={state} disabled={index === 3} />
            ))}
          </div>
          <p className={styles.note}>
            说明：主要按钮用于核心操作；次要按钮用于辅助操作；文本按钮用于跳转或查看。
          </p>
        </Panel>
        <Panel title="八、表格行组件（标准行）">
          <div className={styles.tableFrame}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>候选人</th>
                  <th>岗位</th>
                  <th>匹配度</th>
                  <th>面试建议</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <span className={styles.avatar}>张</span>张伟
                  </td>
                  <td>后端开发工程师（P6）</td>
                  <td className={styles.scoreNumber}>88.5</td>
                  <td>
                    <span className={styles.gradeStrong}>强烈推荐面试</span>
                  </td>
                  <td>今天 14:35</td>
                  <td>
                    <Button type="link">查看</Button>
                    <Button type="link">删除</Button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className={styles.note}>说明：行高 56px，分割线使用 #F0F2F5；操作链接间距 12px。</p>
        </Panel>
      </div>
      <Panel title="九、空状态与加载状态">
        <div className={styles.stateGrid}>
          <StateBox title="空状态 - 无结果">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无匹配结果" />
            <Button type="link">调整筛选条件，重新搜索</Button>
          </StateBox>
          <StateBox title="空状态 - 无数据">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无数据" />
            <Button type="link">去导入数据</Button>
          </StateBox>
          <StateBox title="加载中 - 列表">
            <LoadingOutlined className={styles.loadingIcon} />
            <span>加载中，请稍候...</span>
          </StateBox>
          <StateBox title="加载中 - 区块">
            <Skeleton active title={{ width: '55%' }} paragraph={{ rows: 2 }} />
            <span>加载中，请稍候...</span>
          </StateBox>
          <StateBox title="加载中 - 按钮">
            <Button type="primary" loading>
              生成中...
            </Button>
          </StateBox>
        </div>
      </Panel>
      <section className={styles.disclaimer}>
        <InfoCircleFilled />
        <span>
          <b>十、AI 提示说明（免责声明）</b>
          <br />
          AI
          产出的匹配结果与建议仅供参考，请结合岗位实际需求与面试评估综合判断，最终决策由用人部门负责。
        </span>
      </section>
      <Panel title="十一、操作确认弹窗（删除 / 人工放行）">
        <div className={styles.confirmations}>
          <Confirmation
            title="删除确认"
            text="确定要删除该候选人吗？此操作不可撤销。"
            primary="确定删除"
            warning
            onClick={() => setDialog('delete')}
          />
          <Confirmation
            title="人工放行确认"
            text="确定要人工放行该候选人吗？放行后将进入下一流程。"
            primary="确定放行"
            onClick={() => setDialog('release')}
          />
        </div>
      </Panel>
      <Modal
        title={dialog === 'delete' ? '删除确认' : '人工放行确认'}
        open={dialog !== null}
        onCancel={() => setDialog(null)}
        footer={[
          <Button key="cancel" onClick={() => setDialog(null)}>
            取消
          </Button>,
          <Button
            key="confirm"
            type="primary"
            danger={dialog === 'delete'}
            onClick={() => setDialog(null)}
          >
            {dialog === 'delete' ? '确定删除' : '确定放行'}
          </Button>,
        ]}
      >
        <Typography.Paragraph>
          {dialog === 'delete'
            ? '确定要删除该候选人吗？此操作不可撤销。'
            : '确定要人工放行该候选人吗？放行后将进入下一流程。'}
        </Typography.Paragraph>
      </Modal>
      <div className={styles.footnote}>
        注：1. 本规范基于 1600px 页面宽度，组件在 1200px 及以上断点保持一致；
        <br />
        2. 统一圆角 10px，边框 1px，颜色以本页色彩规范为准；
        <br />
        3. 文字颜色使用深灰 #2F2F2F 及浅灰 #8C8C8C。
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.panel}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
function ButtonStateRow({ state, disabled }: { state: string; disabled: boolean }) {
  return (
    <>
      <span>{state}</span>
      <Button type="primary" disabled={disabled}>
        生成面试题
      </Button>
      <Button disabled={disabled}>查看原始简历</Button>
      <Button type="link" disabled={disabled}>
        查看原文位置
      </Button>
    </>
  );
}
function StateBox({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={styles.stateBox}>
      <strong>{title}</strong>
      <div>{children}</div>
    </div>
  );
}
function Confirmation({
  title,
  text,
  primary,
  warning = false,
  onClick,
}: {
  title: string;
  text: string;
  primary: string;
  warning?: boolean;
  onClick: () => void;
}) {
  return (
    <div className={styles.confirmation}>
      <div>
        <strong>{title}</strong>
        <CloseOutlined />
      </div>
      <p>
        <span className={warning ? styles.warningText : styles.infoText}>
          {warning ? '⚠' : 'ⓘ'}
        </span>
        {text}
      </p>
      <footer>
        <Button size="small">取消</Button>
        <Button size="small" type="primary" onClick={onClick}>
          {primary}
        </Button>
      </footer>
    </div>
  );
}
