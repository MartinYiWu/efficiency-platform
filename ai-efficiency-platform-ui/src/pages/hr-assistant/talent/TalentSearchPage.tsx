import { AppstoreOutlined, SearchOutlined, UnorderedListOutlined } from '@ant-design/icons';
import { Button, Checkbox, Input, InputNumber, Pagination, Select, Tag } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import styles from './TalentSearchPage.module.css';
const candidates = [
  [
    '张',
    '张伟',
    '7年3个月 · 上海',
    'Python',
    'MySQL',
    'Django',
    '后端开发工程师',
    '88.5',
    '强烈推荐',
    '09-01',
    '',
  ],
  [
    '李',
    '李静',
    '5年8个月 · 杭州',
    'Python',
    'MySQL',
    'Spring Boot',
    '后端开发工程师',
    '82.3',
    '推荐',
    '08-29',
    '',
  ],
  [
    '王',
    '王强',
    '6年1个月 · 深圳',
    'Python',
    'MySQL',
    'Django',
    '暂无匹配记录',
    '',
    '',
    '08-22',
    '',
  ],
  [
    '刘',
    '刘敏',
    '4年7个月 · 北京',
    'Python',
    'MySQL',
    'Flask',
    '后端开发工程师',
    '65.4',
    '推荐',
    '07-28',
    '档案较旧',
  ],
  [
    '赵',
    '赵磊',
    '3年10个月 · 成都',
    'Python',
    'MySQL',
    'Linux',
    '后端开发工程师',
    '58.7',
    '推荐',
    '07-15',
    '保留期剩余 32 天',
  ],
];
export function TalentSearchPage() {
  const navigate = useNavigate();
  const [searched, setSearched] = useState(false);
  const [card, setCard] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 3;
  const visibleCandidates = candidates.slice((page - 1) * pageSize, page * pageSize);
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>人才库</h1>
          <p>已解析的候选人档案，可跨岗位复用</p>
        </div>
        <div>
          <Button>导出</Button>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/resumes/upload')}>
            上传简历
          </Button>
        </div>
      </header>
      <div className={styles.layout}>
        <aside className={styles.filters}>
          <h2>语义搜索</h2>
          <Input.TextArea
            rows={3}
            defaultValue="有高并发系统重构经验的后端工程师"
            placeholder="用自然语言描述你要找的人，例如：有高并发系统重构经验的后端工程师"
          />
          <Button
            block
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => {
              setSearched(true);
              setPage(1);
            }}
          >
            搜索
          </Button>
          <Filter title="基础条件">
            <label>学历要求</label>
            <div className={styles.chips}>
              {['大专', '本科', '硕士', '博士'].map((x) => (
                <button className={x === '本科' ? styles.chipActive : ''} key={x}>
                  {x}
                </button>
              ))}
            </div>
            <label>工作年限</label>
            <div className={styles.range}>
              <InputNumber placeholder="最小年限" />
              <span>-</span>
              <InputNumber placeholder="最大年限" />
            </div>
            <label>期望工作城市</label>
            <div className={styles.chips}>
              {['不限', '北京', '上海', '深圳', '杭州'].map((x) => (
                <button className={x === '不限' ? styles.chipActive : ''} key={x}>
                  {x}
                </button>
              ))}
            </div>
          </Filter>
          <Filter title="技能">
            <Select mode="tags" defaultValue={['Python', 'MySQL']} options={[]} />
            <small>按归一后的标准名匹配</small>
          </Filter>
          <Filter title="行业">
            <div className={styles.chips}>
              {['互联网', '金融科技', '企业服务', '制造业'].map((x) => (
                <button className={x === '互联网' ? styles.chipActive : ''} key={x}>
                  {x}
                </button>
              ))}
            </div>
          </Filter>
          <Filter title="入库时间">
            <div className={styles.range}>
              <Input placeholder="开始日期" />
              <Input placeholder="结束日期" />
            </div>
          </Filter>
          <Filter title="排除条件">
            <Checkbox>排除已匹配过某岗位的候选人</Checkbox>
          </Filter>
          <Button block>重置</Button>
        </aside>
        <main className={styles.results} data-height="content" data-testid="talent-results">
          <div className={styles.tools}>
            <span>共 486 位候选人 · {searched ? '当前筛选出 34 位' : '当前可查看 486 位'}</span>
            <div>
              <Select
                defaultValue="入库时间"
                options={[{ value: '入库时间' }, { value: '工作年限' }, { value: '最近匹配分' }]}
              />
              <Button
                className={!card ? styles.viewActive : ''}
                icon={<UnorderedListOutlined />}
                onClick={() => setCard(false)}
              />
              <Button
                className={card ? styles.viewActive : ''}
                icon={<AppstoreOutlined />}
                onClick={() => setCard(true)}
              />
            </div>
          </div>
          <div className={card ? styles.cards : styles.list}>
            {visibleCandidates.map(([initial, name, meta, ...rest]) => (
              <Candidate
                key={name}
                initial={initial}
                name={name}
                meta={meta}
                data={rest}
                onProfile={() =>
                  navigate(`/ai-assistants/hr/talent/${name === '张伟' ? 'zhang-wei' : 'li-jing'}`)
                }
              />
            ))}
          </div>
          <div className={styles.pagination} aria-label="人才库分页">
            <span>
              第 {page} 页 · 共 {candidates.length} 条，每页 {pageSize} 条
            </span>
            <Pagination
              current={page}
              pageSize={pageSize}
              showSizeChanger={false}
              size="small"
              total={candidates.length}
              onChange={setPage}
            />
          </div>
        </main>
      </div>
      <footer className={styles.notice}>
        ⓘ　候选人档案保留期为 12 个月，到期后将自动清理。清理范围包括档案、原始简历文件与检索索引。
      </footer>
    </div>
  );
}
function Filter({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.filter}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
function Candidate({
  initial,
  name,
  meta,
  data,
  onProfile,
}: {
  initial: string;
  name: string;
  meta: string;
  data: string[];
  onProfile: () => void;
}) {
  const [skill1, skill2, skill3, job, score, tier, date, flag] = data;
  return (
    <article className={styles.candidate}>
      <i>{initial}</i>
      <div className={styles.info}>
        <h2>
          {name}
          <span>{meta}</span>
        </h2>
        <div>
          {[skill1, skill2, skill3].map((x, index) => (
            <Tag color={index < 2 ? 'blue' : undefined} key={x}>
              {x}
            </Tag>
          ))}
        </div>
        <p>最近任职：高级后端开发工程师 · 某科技公司</p>
        <small>语义匹配：…主导系统重构，QPS 从 2000 提升至 8000…</small>
      </div>
      <div className={styles.match}>
        <label>最近匹配岗位</label>
        <b>{job}</b>
        {score && (
          <strong>
            {score} <Tag color="green">{tier}</Tag>
          </strong>
        )}
        <span>入库时间：{date}</span>
        {flag && <Tag color={flag.includes('32') ? 'orange' : 'default'}>{flag}</Tag>}
      </div>
      <div className={styles.actions}>
        <Button onClick={onProfile}>查看档案</Button>
        <Button type="primary">匹配岗位</Button>
      </div>
    </article>
  );
}
