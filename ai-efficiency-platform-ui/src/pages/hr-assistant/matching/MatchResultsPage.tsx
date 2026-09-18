import {
  CheckCircleFilled,
  CloseOutlined,
  ExclamationCircleFilled,
  FileTextOutlined,
} from '@ant-design/icons';
import {
  Button,
  Checkbox,
  Input,
  InputNumber,
  Modal,
  Pagination,
  Progress,
  Radio,
  Select,
  Slider,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './MatchResultsPage.module.css';

type Tier = '强烈推荐面试' | '推荐面试' | '建议复核' | '暂不推荐';
const candidates = [
  ['张伟', '7年3个月 · 上海', 88.5, '强烈推荐面试', 92, 85, 90, '4/4', ''],
  ['李静', '5年2个月 · 上海', 82, '推荐面试', 88, 85, 78, '4/4', '质量提示'],
  ['王强', '4年8个月 · 杭州→上海', 76.5, '推荐面试', 80, 75, 74, '3/4 · 1临界', '硬条件临界'],
  ['刘敏', '6年1个月 · 上海', 71, '推荐面试', 75, 72, 68, '4/4', ''],
  ['陈浩', '3年5个月 · 上海', 62.5, '建议复核', 68, 60, 62, '4/4', '需人工复核'],
  ['赵磊', '9年3个月 · 上海', 58, '建议复核', 72, 45, 60, '4/4', '特殊背景值得关注'],
  ['孙芳', '2年3个月 · 上海', 45, '暂不推荐', 55, 30, 48, '4/4', ''],
  ['周涛', '8年 · 北京', 41.5, '暂不推荐', 40, 65, 38, '4/4', '疑似重复'],
] as const;
const tierColor: Record<Tier, string> = {
  强烈推荐面试: 'green',
  推荐面试: 'blue',
  建议复核: 'orange',
  暂不推荐: 'default',
};
function TierTag({ tier }: { tier: Tier }) {
  return <Tag color={tierColor[tier]}>{tier}</Tag>;
}
function WeightDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [notice, context] = message.useMessage();
  const [weights, setWeights] = useState([40, 20, 30, 5, 5]);
  const [saveMode, setSaveMode] = useState('default');
  const updateWeight = (index: number, value: number) =>
    setWeights((current) => current.map((item, itemIndex) => (itemIndex === index ? value : item)));
  const total = weights.reduce((sum, item) => sum + item, 0);
  return (
    <Modal
      width={880}
      open={open}
      title="调整权重并重算"
      okText="确认并重算"
      cancelText="取消"
      okButtonProps={{ disabled: total !== 100 }}
      onCancel={onClose}
      onOk={() => {
        notice.success('权重重算任务已提交，历史结果将保留。');
        onClose();
      }}
    >
      {context}
      <Typography.Text type="secondary">
        调整后将重新计算已匹配的 47 份简历，不需要重新解析
      </Typography.Text>
      <div className={styles.currentPosition}>
        后端开发工程师（P6） · 当前权重版本 v1.2 · 47 份已匹配
      </div>
      <div className={styles.weightContent}>
        <section>
          <h3>权重调整</h3>
          {['技能匹配', '经验匹配', '项目匹配', '学历匹配', '加分项'].map((label, index) => (
            <div className={styles.weightLine} key={label}>
              <span>{label}</span>
              <Slider
                value={weights[index]}
                onChange={(value) => updateWeight(index, Number(value))}
              />
              <InputNumber
                min={0}
                max={100}
                value={weights[index]}
                onChange={(value) => updateWeight(index, value ?? 0)}
              />
              <b>{index === 1 ? '-5%' : index === 2 ? '+5%' : '—'}</b>
            </div>
          ))}
          <p className={total === 100 ? styles.totalOk : styles.totalError}>
            {total === 100 ? <CheckCircleFilled /> : <ExclamationCircleFilled />} 合计 {total}%
          </p>
          <h3>分档阈值调整</h3>
          <div className={styles.thresholds}>
            强烈推荐 ≥ <InputNumber defaultValue={80} /> 推荐 ≥ <InputNumber defaultValue={65} />{' '}
            建议复核 ≥ <InputNumber defaultValue={50} />
          </div>
          <div className={styles.presets}>
            {['恢复默认', '技术研发族推荐值', '上一版本 v1.1'].map((label) => (
              <Button
                key={label}
                onClick={() => label === '恢复默认' && setWeights([40, 25, 25, 5, 5])}
              >
                {label}
              </Button>
            ))}
          </div>
        </section>
        <section className={styles.impactPreview}>
          <h3>调整后的预计变化</h3>
          <small>基于当前 47 份简历试算</small>
          {[
            '强烈推荐  5 → 7　+2',
            '推荐面试 18 → 16　-2',
            '建议复核 12 → 13　+1',
            '暂不推荐 12 → 11　-1',
          ].map((item) => (
            <p key={item}>{item}</p>
          ))}
          <h4>分档变动明细</h4>
          {[
            '张伟  88.5 → 90.2　推荐面试 → 强烈推荐面试',
            '王强  76.5 → 79.8　无变化',
            '刘敏  71.0 → 64.5　推荐面试 → 建议复核',
            '陈浩  62.5 → 66.8　建议复核 → 推荐面试',
          ].map((item) => (
            <span key={item}>{item}</span>
          ))}
          <div className={styles.recalculateTip}>
            本次调整将使 6 份简历的分档发生变化。历史匹配结果会保留，可随时对比查看。
          </div>
        </section>
      </div>
      <Radio.Group value={saveMode} onChange={(event) => setSaveMode(event.target.value)}>
        <Radio value="default">将新权重保存为岗位默认配置（版本 v1.3）</Radio>
        <Radio value="once">仅本次重算，不修改岗位配置</Radio>
      </Radio.Group>
    </Modal>
  );
}
export function MatchResultsPage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [banner, setBanner] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [keyword, setKeyword] = useState('');
  const [tier, setTier] = useState<string[]>([]);
  const [empty, setEmpty] = useState(false);
  const [weightOpen, setWeightOpen] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 5;
  const visible = useMemo(
    () =>
      candidates.filter(
        ([name, , , candidateTier]) =>
          name.includes(keyword) && (!tier.length || tier.includes(candidateTier)),
      ),
    [keyword, tier],
  );
  const visibleRows = visible.slice((page - 1) * pageSize, page * pageSize);
  const updateKeyword = (value: string) => {
    setKeyword(value);
    setPage(1);
  };
  const updateTier = (value: string[]) => {
    setTier(value);
    setPage(1);
  };
  const toggle = (name: string) =>
    setSelected((v) => (v.includes(name) ? v.filter((x) => x !== name) : [...v, name]));
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div>
          <Typography.Title level={1}>
            后端开发工程师（P6） <Tag color="blue">技术研发</Tag>
          </Typography.Title>
          <Typography.Text>共 47 份简历 · 匹配于 2026-09-01 09:45 · 权重版本 v1.2</Typography.Text>
        </div>
        <div>
          <Button onClick={() => setWeightOpen(true)}>调整权重重算</Button>
          <Button onClick={() => notice.success('匹配结果导出任务已创建')}>导出结果</Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/resumes/upload')}>
            继续上传简历
          </Button>
        </div>
      </header>
      {banner && (
        <div className={styles.aiBanner}>
          ✦　<strong>本结果由 AI 辅助生成，仅供参考。最终判断请结合面试与人工评估。</strong>
          <Button
            aria-label="关闭 AI 提示"
            type="text"
            icon={<CloseOutlined />}
            onClick={() => setBanner(false)}
          />
        </div>
      )}
      <div className={styles.stats}>
        {(['强烈推荐面试', '推荐面试', '建议复核', '暂不推荐'] as Tier[]).map((item, index) => (
          <button key={item} className={styles[`stat${index}`]} onClick={() => updateTier([item])}>
            <span>{item}</span>
            <b>{[5, 18, 12, 12][index]}</b>
            <small>
              {index === 0
                ? '≥80分'
                : index === 1
                  ? '≥65分'
                  : index === 2
                    ? '≥50分'
                    : '<50分或硬条件未过'}
            </small>
          </button>
        ))}
        <button
          className={styles.filtered}
          onClick={() => navigate('/ai-assistants/hr/matching/filtered')}
        >
          <b>被硬性条件过滤　8 人</b>
          <span>查看并打捞 →</span>
          <small>这些简历未进入评分，建议检查是否误伤</small>
        </button>
      </div>
      <div className={styles.layout}>
        <main>
          <section className={styles.filters}>
            <Input
              value={keyword}
              onChange={(e) => updateKeyword(e.target.value)}
              placeholder="搜索候选人姓名或技能"
            />
            <Select
              mode="multiple"
              value={tier}
              onChange={updateTier}
              placeholder="全部分档"
              options={(['强烈推荐面试', '推荐面试', '建议复核', '暂不推荐'] as Tier[]).map(
                (value) => ({ value, label: value }),
              )}
            />
            <Select
              mode="multiple"
              placeholder="全部标记"
              options={['需人工复核', '硬条件临界', '质量提示', '特殊背景'].map((value) => ({
                value,
                label: value,
              }))}
            />
            <span>
              <InputNumber placeholder="最低分" /> - <InputNumber placeholder="最高分" />
            </span>
            <Select
              defaultValue="总分降序"
              options={['总分降序', '技能分', '经验分', '项目分', '匹配时间'].map((value) => ({
                value,
                label: value,
              }))}
            />
            <Button type="primary" onClick={() => setEmpty(false)}>
              查询
            </Button>
            <Button
              onClick={() => {
                updateKeyword('');
                updateTier([]);
              }}
            >
              重置
            </Button>
          </section>
          {empty ? (
            <section className={styles.empty}>
              <FileTextOutlined />
              <h2>还没有匹配结果</h2>
              <p>上传候选人简历后，系统会自动与本岗位进行匹配</p>
              <Button type="primary" onClick={() => navigate('/ai-assistants/hr/resumes/upload')}>
                上传简历
              </Button>
              <Button type="link">从人才库选择候选人</Button>
            </section>
          ) : (
            <section className={styles.tableWrap}>
              <div className={styles.tableHead}>
                <b>选择</b>
                <b>候选人</b>
                <b>总分</b>
                <b>分档</b>
                <b>技能</b>
                <b>经验</b>
                <b>项目</b>
                <b>硬性条件</b>
                <b>标记</b>
                <b>操作</b>
              </div>
              {visibleRows.map(
                ([name, desc, score, candidateTier, skill, experience, project, hard, mark]) => (
                  <div key={name} className={`${styles.row} ${styles[`row${candidateTier}`]}`}>
                    <Checkbox checked={selected.includes(name)} onChange={() => toggle(name)} />
                    <span className={styles.candidate}>
                      <i>{name[0]}</i>
                      <b>{name}</b>
                      <small>{desc}</small>
                    </span>
                    <strong className={styles[`score${candidateTier}`]}>{score}</strong>
                    <TierTag tier={candidateTier} />
                    <span>{skill}</span>
                    <span>{experience}</span>
                    <span>{project}</span>
                    <span className={hard.startsWith('4') ? styles.pass : styles.borderline}>
                      {hard.startsWith('4') ? <CheckCircleFilled /> : <ExclamationCircleFilled />}{' '}
                      {hard}
                    </span>
                    <span>
                      {mark && (
                        <Tooltip
                          title={
                            mark === '需人工复核' ? '解析置信度 62%，部分字段需确认' : undefined
                          }
                        >
                          <Tag
                            color={
                              mark.includes('特殊')
                                ? 'purple'
                                : mark.includes('临界') || mark.includes('人工')
                                  ? 'orange'
                                  : mark.includes('质量')
                                    ? 'gold'
                                    : 'blue'
                            }
                          >
                            {mark}
                          </Tag>
                        </Tooltip>
                      )}
                    </span>
                    <span>
                      <Button
                        type="link"
                        onClick={() => navigate('/ai-assistants/hr/matching/zhang-wei')}
                      >
                        查看详情
                      </Button>
                      <Button
                        type="link"
                        onClick={() => navigate('/ai-assistants/hr/interviews/generate')}
                      >
                        生成面试题
                      </Button>
                    </span>
                    {name === '赵磊' && (
                      <p className={styles.special}>
                        有 3 段跨行业经历与 1 段创业经历，规则可能未能识别其综合能力，建议人工看一眼
                      </p>
                    )}
                  </div>
                ),
              )}
            </section>
          )}
          {visible.length > pageSize && (
            <div className={styles.pagination} aria-label="匹配结果分页">
              <span>
                第 {page} 页 · 共 {visible.length} 条（不含被过滤 8 条），每页 {pageSize} 条
              </span>
              <Pagination
                current={page}
                pageSize={pageSize}
                showSizeChanger={false}
                size="small"
                total={visible.length}
                onChange={setPage}
              />
            </div>
          )}
        </main>
        <aside>
          <section>
            <h2>匹配概览</h2>
            <b className={styles.big}>39</b> 份已评分
            <div className={styles.bar}>
              <i />
              <i />
              <i />
              <i />
            </div>
            <small>另有 8 份被硬性条件过滤</small>
          </section>
          <section>
            <h2>维度均分</h2>
            {[
              ['技能匹配', 71.2],
              ['经验匹配', 66.8],
              ['项目匹配', 64.5],
              ['学历匹配', 78],
              ['加分项', 32.1],
            ].map(([label, value]) => (
              <div className={styles.metric} key={String(label)}>
                <span>{label}</span>
                <Progress percent={Number(value)} showInfo={false} />
                <b>{value}</b>
              </div>
            ))}
            <small>加分项均分偏低，说明该项要求在候选池中较稀缺</small>
          </section>
          <section>
            <h2>当前权重</h2>
            <p>技能40% / 经验25% / 项目25% / 学历5% / 加分5%</p>
            <small>权重版本 v1.2 · 09-01 09:30 更新</small>
            <Button block onClick={() => setWeightOpen(true)}>
              调整权重并重算
            </Button>
          </section>
          <section>
            <h2>操作</h2>
            <Button
              block
              type="primary"
              onClick={() => navigate('/ai-assistants/hr/interviews/generate?batch=1')}
            >
              批量生成面试题
            </Button>
            <Button block onClick={() => notice.success('匹配结果导出任务已创建')}>
              导出匹配结果
            </Button>
            <Button
              block
              type="link"
              onClick={() => navigate('/ai-assistants/hr/matching/filtered')}
            >
              查看被过滤的 8 份
            </Button>
          </section>
        </aside>
      </div>
      {selected.length > 0 && (
        <div className={styles.batch}>
          <span>
            已选 {selected.length} 人　
            <Button type="link" onClick={() => setSelected([])}>
              取消选择
            </Button>
          </span>
          <div>
            <Button onClick={() => navigate('/ai-assistants/hr/interviews/generate?batch=1')}>
              批量生成面试题
            </Button>
            <Button>导出所选</Button>
            <Button>加入人才库</Button>
          </div>
        </div>
      )}
      {weightOpen && <WeightDialog open onClose={() => setWeightOpen(false)} />}
    </div>
  );
}
