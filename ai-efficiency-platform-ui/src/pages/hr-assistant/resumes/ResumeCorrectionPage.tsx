import {
  CheckCircleFilled,
  CloseCircleFilled,
  DownloadOutlined,
  ExclamationCircleFilled,
  LeftOutlined,
  LockOutlined,
  MinusOutlined,
  PlusOutlined,
  RightOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Input,
  Modal,
  Progress,
  Select,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './ResumeCorrectionPage.module.css';

const skills = [
  ['Python', 'Python', '强', '3 处', 'success'],
  ['Django', 'Django', '中', '2 处', 'primary'],
  ['MySQL', 'MySQL', '中', '2 处', 'primary'],
  ['Git', 'Git', '弱', '1 处', 'default'],
  ['Linux', 'Linux', '弱', '1 处', 'default'],
];

function FieldState({
  type = 'success',
  children,
}: {
  type?: 'success' | 'warning' | 'error';
  children: string;
}) {
  const Icon =
    type === 'success'
      ? CheckCircleFilled
      : type === 'warning'
        ? ExclamationCircleFilled
        : CloseCircleFilled;
  return (
    <span className={styles[`state${type[0].toUpperCase()}${type.slice(1)}`]}>
      <Icon /> {children}
    </span>
  );
}

function ResumePage({ activeMarker }: { activeMarker: number | null }) {
  const markerClass = (id: number, type: 'success' | 'warning' | 'error' = 'success') =>
    `${styles.marker} ${styles[`marker${type[0].toUpperCase()}${type.slice(1)}`]} ${activeMarker === id ? styles.markerActive : ''}`;

  return (
    <article className={styles.resumePaper} aria-label="张伟原简历">
      <h2>张伟</h2>
      <p>手机：138****5678　｜　邮箱：zhangwei***@email.com　｜　地址：上海</p>
      <section>
        <h3>教育经历</h3>
        <div className={markerClass(1)}>
          <b>01</b>2014.09 - 2018.06　 北京理工大学　 计算机科学与技术　 本科
        </div>
      </section>
      <section>
        <h3>工作经历</h3>
        <div className={markerClass(2)}>
          <b>02</b>
          <strong>2022.07 - 至今</strong>　 某科技有限公司　 后端开发工程师
          <br />
          工作概述：
          <br />· 负责公司核心业务系统的设计与开发，支撑日均千万级订单处理。
          <br />· 参与系统架构优化与性能调优，提升系统稳定性与可扩展性。
          <br />
          技术栈：Java、Spring Boot、MySQL、Redis、Kafka、Docker
        </div>
        <div className={markerClass(3)}>
          <b>03</b>
          <strong>2020.07 - 2022.06</strong>　 某互联网公司　 后端开发工程师
          <br />· 负责用户中心模块开发与维护。
          <br />· 优化缓存策略和慢查询，提升接口响应性能。
          <br />
          技术栈：Python、Django、MySQL、Redis
        </div>
      </section>
      <section>
        <h3>项目经历</h3>
        <div className={markerClass(4)}>
          <b>04</b>
          <strong>分布式订单系统</strong>　 项目时间：2021.03 – 2021.11
          <br />
          项目描述：构建高可用、高并发的分布式订单系统，支持秒杀、支付等场景。
          <br />
          担任角色：后端开发负责人
          <br />
          项目技术：Spring Cloud、MySQL、Redis、RocketMQ
          <br />
          <span className={markerClass(5, 'warning')}>
            <b>05</b>团队规模：5 人
          </span>
          <br />
          <span className={markerClass(6, 'warning')}>
            <b>06</b>项目描述：带领 5 人小组完成支付模块改造
          </span>
        </div>
      </section>
      <section>
        <h3>专业技能</h3>
        <div className={markerClass(7)}>
          <b>07</b>熟练掌握：Java、Python、Django、MySQL、Redis、Kafka、Linux
        </div>
        <div className={markerClass(8, 'error')}>
          <b>08</b>个人网站：——
        </div>
      </section>
    </article>
  );
}

export function ResumeCorrectionPage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [zoom, setZoom] = useState(100);
  const [activeMarker, setActiveMarker] = useState<number | null>(5);
  const [skipOpen, setSkipOpen] = useState(false);
  const [teamSize, setTeamSize] = useState('5');
  const [role, setRole] = useState('');
  const [city, setCity] = useState('');
  const [reviewedItems, setReviewedItems] = useState<string[]>([]);
  const reviewed = reviewedItems.length;
  const markReviewed = (field: string) =>
    setReviewedItems((items) => (items.includes(field) ? items : [...items, field]));
  const canContinue = reviewed === 4;

  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div>
          <Typography.Title level={1}>核对解析结果</Typography.Title>
          <Typography.Text>
            张伟_后端开发工程师.pdf　·　解析置信度 62%　·　4 项需确认
          </Typography.Text>
        </div>
        <div className={styles.headerActions}>
          <Button onClick={() => notice.loading({ content: '正在重新解析简历…', duration: 1.2 })}>
            重新解析
          </Button>
          <Button onClick={() => setSkipOpen(true)}>跳过，按现有结果继续</Button>
          <Button
            type="primary"
            disabled={!canContinue}
            onClick={() => navigate('/ai-assistants/hr/talent/zhang-wei')}
          >
            确认并继续匹配
          </Button>
        </div>
      </header>

      <Alert
        className={styles.warning}
        type="warning"
        showIcon
        title="本份简历解析置信度较低，请核对标记项后再进行匹配"
        description="置信度低通常由排版复杂、图片型简历、非标准格式导致"
      />

      <div className={styles.workspace}>
        <section className={styles.sourceCard}>
          <div className={styles.sourceToolbar}>
            <div>
              <Button
                aria-label="缩小"
                icon={<MinusOutlined />}
                onClick={() => setZoom((value) => Math.max(80, value - 10))}
              />
              <span>{zoom}%</span>
              <Button
                aria-label="放大"
                icon={<PlusOutlined />}
                onClick={() => setZoom((value) => Math.min(120, value + 10))}
              />
            </div>
            <div>
              <Button aria-label="上一页" icon={<LeftOutlined />} />
              <b>1 / 3</b>
              <Button aria-label="下一页" icon={<RightOutlined />} />
            </div>
            <div>
              <Button>适应窗口</Button>
              <Tooltip title="下载原件">
                <Button aria-label="下载原件" icon={<DownloadOutlined />} />
              </Tooltip>
            </div>
          </div>
          <div className={styles.paperArea}>
            <div style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top center' }}>
              <ResumePage activeMarker={activeMarker} />
            </div>
          </div>
          <div className={styles.legend}>
            <FieldState>高置信 18</FieldState>
            <FieldState type="warning">需确认 4</FieldState>
            <FieldState type="error">未识别 2</FieldState>
          </div>
        </section>

        <section className={styles.resultCard}>
          <div className={styles.reviewProgress}>
            <b>已核对 {reviewed} / 4</b>
            <Progress percent={Math.round((reviewed / 4) * 100)} showInfo />
            <span>全部核对完成后可继续匹配</span>
          </div>
          <section className={styles.group}>
            <h2>⌄　基础信息</h2>
            <div className={styles.basicGrid}>
              <label>
                <span>
                  <b>01</b> 姓名
                </span>
                <Input value="张伟" readOnly suffix={<FieldState>高置信</FieldState>} />
              </label>
              <label>
                <span>
                  <b>02</b> 手机号
                </span>
                <Input value="138****5678" readOnly suffix={<LockOutlined />} />
              </label>
              <label>
                <span>
                  <b>03</b> 当前城市
                </span>
                <Input value="上海" readOnly suffix={<FieldState>高置信</FieldState>} />
              </label>
              <label>
                <span>期望城市</span>
                <Input
                  status="error"
                  placeholder="请手动输入"
                  value={city}
                  onFocus={() => setActiveMarker(8)}
                  onChange={(event) => setCity(event.target.value)}
                  onBlur={() => city && markReviewed('city')}
                  suffix={<FieldState type="error">未识别</FieldState>}
                />
                <small>原简历中未找到期望工作地信息，可留空</small>
              </label>
            </div>
          </section>
          <section className={styles.group}>
            <h2>⌄　教育经历</h2>
            <div className={styles.readonlyLine}>
              <b>04</b> 2014.09 – 2018.06　 北京理工大学　 计算机科学与技术　 本科{' '}
              <FieldState>高置信</FieldState>
            </div>
          </section>
          <section className={`${styles.group} ${styles.focusGroup}`}>
            <h2>
              ⌃　工作经历（当前） <FieldState type="warning">需确认</FieldState>
            </h2>
            <div className={styles.readonlyLine}>
              2022.07 – 至今　 某科技有限公司　 后端开发工程师 <b>05</b>
            </div>
            <div className={styles.formLine}>
              <span>时间</span>
              <Input value="2022.07 – 至今" readOnly />
            </div>
            <div className={styles.formLine}>
              <span>团队规模</span>
              <Input
                status="warning"
                value={teamSize}
                onFocus={() => setActiveMarker(5)}
                onChange={(event) => setTeamSize(event.target.value)}
                suffix={<b>06</b>}
              />
            </div>
            <div className={styles.evidence}>
              <span>原文证据</span>
              <p>“带领 5 人小组完成支付模块改造”</p>
              <span>需确认原因</span>
              <p>需确认“5 人”是否包含本人，建议核实团队组成。</p>
              <Button type="link" onClick={() => setActiveMarker(5)}>
                在原简历中定位 →
              </Button>
            </div>
            <div className={styles.inlineActions}>
              <Button
                type="primary"
                ghost
                icon={<CheckCircleFilled />}
                onClick={() => {
                  markReviewed('team-size');
                  notice.success('团队规模已确认');
                }}
              >
                确认无误
              </Button>
              <Button
                icon={<CheckCircleFilled />}
                onClick={() => notice.info('团队规模已进入编辑状态')}
              >
                修改
              </Button>
            </div>
          </section>
          <section className={styles.group}>
            <h2>⌄　工作经历（过往）</h2>
            <div className={styles.readonlyLine}>
              <b>08</b> 2020.07 – 2022.06　 某互联网公司　 后端开发工程师{' '}
              <FieldState>高置信</FieldState>
            </div>
          </section>
          <section className={styles.group}>
            <h2>⌃　项目经历（分布式订单系统）</h2>
            <p>负责后端开发负责人，项目时间 2021.03 – 2021.11</p>
            <div className={styles.formLine}>
              <span>角色</span>
              <Select
                status="warning"
                value={role || undefined}
                placeholder="请选择角色"
                options={['主导', '核心成员', '参与'].map((value) => ({ value, label: value }))}
                onFocus={() => setActiveMarker(6)}
                onChange={(value) => {
                  setRole(value);
                  markReviewed('role');
                }}
              />
            </div>
            <div className={styles.evidence}>
              <span>原文证据</span>
              <p>“主导系统重构，QPS 从 2000 提升至 8000”</p>
              <span>不确定原因</span>
              <p>“主导”的职责边界不明确，可能是架构设计也可能是执行落地。</p>
              <em>该项将进入面试待核实点，建议在面试中确认</em>
            </div>
          </section>
          <section className={styles.group}>
            <h2>⌃　专业技能</h2>
            <div className={styles.skillTable}>
              <b>技能名</b>
              <b>归一后</b>
              <b>证据强度</b>
              <b>出现次数</b>
              {skills.map(([name]) => (
                <span key={name}>{name}</span>
              ))}
              {skills.map(([, normalized]) => (
                <span key={`normalized-${normalized}`}>{normalized}</span>
              ))}
              {skills.map(([, , strength, , color], index) => (
                <Tag key={`strength-${index}`} color={color}>
                  {strength}
                </Tag>
              ))}
              {skills.map(([, , , count], index) => (
                <span key={`count-${index}`}>{count}</span>
              ))}
            </div>
            <div className={styles.unmatched}>
              <b>14</b>
              <span>RabbitMQ</span>
              <FieldState type="warning">未匹配到标准名</FieldState>
              <Tag>弱</Tag>
              <span>1 处</span>
              <p>同义词库中未找到「RabbitMQ」的标准写法</p>
              <div>
                <Button type="link" onClick={() => markReviewed('rabbitmq')}>
                  按原文保留
                </Button>
                <Button type="link" onClick={() => markReviewed('rabbitmq')}>
                  指定标准名
                </Button>
                <Button type="link" onClick={() => notice.success('已加入同义词库待审核')}>
                  加入同义词库
                </Button>
              </div>
            </div>
          </section>
          <section className={styles.derived}>
            <h2>派生信息（只读）</h2>
            <span>
              总工作年限　<b>7年3个月</b>
            </span>
            <span>
              跳槽次数　<b>1 次</b>
            </span>
            <span>
              平均在职时长　<b>43 个月</b>
            </span>
            <span>
              时间断档　<b>2022.03 – 2022.06（3个月）</b>{' '}
              <Tag color="orange">将进入面试待核实点</Tag>
            </span>
            <span>
              时间重叠　<b>无</b>
            </span>
            <span>
              管理经历　<b>有（带过 5 人）</b>
            </span>
          </section>
          <section className={styles.quality}>
            <h2>
              <ExclamationCircleFilled /> 简历质量提示
            </h2>
            <p>1. 时间连续性：存在 3 个月时间间隔（2022.04 – 2022.06），建议补充说明。</p>
            <p>2. 职责边界：部分成果描述较笼统，建议补充具体负责范围与产出。</p>
            <small>以上提示仅供参考，不影响后续流程，会作为面试待核实点。</small>
          </section>
        </section>
      </div>
      <footer className={styles.footer}>
        <span>未核对项将按当前解析结果使用</span>
        <div>
          <Button onClick={() => notice.success('已保存，稍后可继续核对')}>保存并稍后处理</Button>
          <Button
            type="primary"
            disabled={!canContinue}
            onClick={() => navigate('/ai-assistants/hr/talent/zhang-wei')}
          >
            确认并继续匹配
          </Button>
        </div>
      </footer>
      <p className={styles.note}>解析结果与人工修正记录将一并保存，可在候选人档案中追溯。</p>
      <Modal
        open={skipOpen}
        title="按现有结果继续匹配"
        okText="确认继续"
        cancelText="返回核对"
        onCancel={() => setSkipOpen(false)}
        onOk={() => {
          setSkipOpen(false);
          navigate('/ai-assistants/hr/talent/zhang-wei');
        }}
      >
        仍有 {Math.max(0, 4 - reviewed)}{' '}
        项字段未确认。跳过后将按当前解析结果进行匹配，该候选人会被标记为需人工复核。确认继续？
      </Modal>
    </div>
  );
}
