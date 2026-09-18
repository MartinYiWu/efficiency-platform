import { DownloadOutlined, LockOutlined } from '@ant-design/icons';
import { Button, Checkbox, Radio, message } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import styles from './InterviewGuidePreviewPage.module.css';

const contents = [
  '候选人基本信息（姓名、年限、城市）',
  '结构化简历摘要',
  '面试重点核实项',
  '面试题（含考察目的、期望要点、追问方向、评分参考）',
  '评价记录页（空白表格，供面试官填写）',
  '原简历附件',
];

export function InterviewGuidePreviewPage() {
  const navigate = useNavigate();
  const [notice, context] = message.useMessage();
  const [format, setFormat] = useState('PDF');
  const [contact, setContact] = useState('不包含（推荐）');
  const [selected, setSelected] = useState(contents.slice(0, 5));
  const [zoom, setZoom] = useState('100%');
  const toggle = (item: string) =>
    setSelected((items) =>
      items.includes(item) ? items.filter((value) => value !== item) : [...items, item],
    );
  const download = () => notice.success(`已生成 ${format} 面试指南，导出操作已记录。`);
  return (
    <div className={styles.page}>
      {context}
      <header className={styles.header}>
        <div>
          <h1>导出面试指南</h1>
          <span>张伟 · 后端开发工程师（P6）</span>
        </div>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/interviews/questions')}>
            返回编辑
          </Button>
          <Button type="primary" icon={<DownloadOutlined />} onClick={download}>
            下载
          </Button>
        </div>
      </header>
      <div className={styles.layout}>
        <aside className={styles.settings}>
          <section>
            <h2>导出格式</h2>
            {['PDF', 'Word'].map((type) => (
              <button
                className={format === type ? styles.formatActive : ''}
                key={type}
                onClick={() => setFormat(type)}
              >
                <b>{type}</b>
                <span>{type === 'PDF' ? '适合打印或邮件发送' : '适合二次编辑'}</span>
              </button>
            ))}
          </section>
          <section>
            <h2>导出内容</h2>
            {contents.map((item) => (
              <Checkbox checked={selected.includes(item)} key={item} onChange={() => toggle(item)}>
                {item}
              </Checkbox>
            ))}
            <div className={styles.locked}>
              {['AI 匹配分数', '匹配分档', '各维度得分', '匹配亮点与能力缺口'].map((item) => (
                <Checkbox disabled key={item}>
                  <LockOutlined /> {item}
                </Checkbox>
              ))}
            </div>
            <p className={styles.warning}>
              面试指南不包含 AI
              匹配分数与评级。原因：面试官若预先知道分数，会带着预设进入面试，实际是在寻找支持 AI
              判断的证据，而非独立评估。这是 AI 招聘最隐蔽的失效方式。
            </p>
          </section>
          <section>
            <h2>联系方式</h2>
            <Radio.Group value={contact} onChange={(event) => setContact(event.target.value)}>
              {['不包含（推荐）', '包含脱敏（138****5678）', '包含完整'].map((item) => (
                <Radio key={item} value={item}>
                  {item}
                </Radio>
              ))}
            </Radio.Group>
            {contact !== '不包含（推荐）' && (
              <p className={styles.contactWarning}>包含联系方式的导出操作将被记录</p>
            )}
          </section>
          <section>
            <h2>页眉页脚</h2>
            <Checkbox defaultChecked>页眉显示岗位名称</Checkbox>
            <Checkbox defaultChecked>页脚显示免责说明</Checkbox>
            <textarea
              readOnly
              value="本指南由 AI 辅助生成，请面试官按实际情况调整。评价结论以面试官判断为准。"
            />
          </section>
        </aside>
        <main className={styles.preview}>
          <div className={styles.previewTools}>
            <span>缩放</span>
            {['50%', '75%', '100%'].map((item) => (
              <button
                className={zoom === item ? styles.zoomActive : ''}
                key={item}
                onClick={() => setZoom(item)}
              >
                {item}
              </button>
            ))}
            <span>第 1 页 / 共 4 页</span>
          </div>
          <div className={styles.paperWrap}>
            <article className={styles.paper} data-zoom={zoom}>
              <header>后端开发工程师（P6）· 首轮面试指南</header>
              <h1>面试指南</h1>
              <h2>候选人：张伟</h2>
              <section className={styles.profile}>
                <b>候选人概要</b>
                <p>工作年限　7年3个月　　所在城市　上海</p>
                <p>最高学历　本科 · 计算机科学与技术</p>
                <p>近期职位　高级后端开发工程师</p>
              </section>
              <section className={styles.focus}>
                <h3>本轮面试重点核实</h3>
                <ol>
                  <li>“主导系统重构”的具体职责边界</li>
                  <li>Django 的实际使用深度</li>
                  <li>2022年3月至6月的 3 个月时间断档</li>
                </ol>
              </section>
              <section>
                <h3>面试题</h3>
                <h4>A 简历深挖题</h4>
                <b>A1【8分钟】系统设计能力</b>
                <p>
                  你提到主导了订单系统重构，把 QPS 从 2000 提升到
                  8000。能讲讲当时是怎么定位性能瓶颈的吗？
                </p>
                <p>
                  <b>考察目的：</b>验证候选人是否真正参与了性能优化的分析过程。
                </p>
                <p>
                  <b>期望要点：</b>□ 使用的分析工具　□ 具体瓶颈层　□ 排除其他可能性　□ 对比数据来源
                </p>
                <p>
                  <b>追问方向：</b>如果当时 QPS 只提升到 4000，下一步会怎么做？
                </p>
                <div className={styles.score}>
                  <span>优秀</span>
                  <span>合格</span>
                  <span>需警惕</span>
                </div>
                <div className={styles.note}>
                  面试官记录：
                  <br />
                  <br />
                  <br />
                  评分：○优秀　○合格　○需警惕
                </div>
              </section>
              <footer>本指南由 AI 辅助生成，评价结论以面试官判断为准　　第 1 页 / 共 4 页</footer>
            </article>
          </div>
        </main>
      </div>
      <footer className={styles.footer}>
        <span>导出操作将记录在操作日志中</span>
        <div>
          <Button onClick={() => navigate('/ai-assistants/hr/interviews/questions')}>取消</Button>
          <Button type="primary" onClick={download}>
            下载 {format}
          </Button>
        </div>
      </footer>
    </div>
  );
}
