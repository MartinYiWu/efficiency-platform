import { ExclamationCircleFilled, PlusOutlined } from '@ant-design/icons';
import { Button, Input, Modal, Select, Table, Tag } from 'antd';
import { useState } from 'react';
import styles from './SkillSynonymPage.module.css';
const rows = [
  ['Kubernetes', 'K8s, k8s, K8S', '云与运维', '86', '平台预置'],
  ['Spring Boot', 'SpringBoot, springboot, spring-boot', '框架', '142', '平台预置'],
  ['PostgreSQL', 'PG, Postgres, postgres', '数据库', '38', '平台预置'],
  ['JavaScript', 'JS, js, ES6, ES2015', '编程语言', '203', '平台预置'],
  ['Photoshop', 'PS, ps', '工具', '47', '平台预置'],
  ['Elasticsearch', 'ES, es', '数据库', '29', '平台预置'],
  ['RabbitMQ', 'Rabbit MQ, rabbitmq', '中间件', '18', '手动添加'],
];
export function SkillSynonymPage() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const data = rows.filter((r) => r.join().toLowerCase().includes(query.toLowerCase()));
  return (
    <div className={styles.page}>
      <header>
        <div>
          <h1>技能同义词库</h1>
          <p>统一技能的不同写法。这是匹配准确率的基础，需要持续维护。</p>
        </div>
        <div>
          <Button>批量导入</Button>
          <Button>导出</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
            新增词条
          </Button>
        </div>
      </header>
      <p className={styles.info}>
        ⓘ　简历里写「PS」，岗位要求写「Photoshop」；写「K8s」，要求写「Kubernetes」。这些如果不归一，匹配就是在做无效比对。
      </p>
      <div className={styles.layout}>
        <aside>
          <h2>技能类别</h2>
          <Input placeholder="搜索类别" />
          {[
            '全部类别　248',
            '编程语言　42',
            '框架　68',
            '数据库　31',
            '中间件　24',
            '工具　55',
            '云与运维　18',
            '软技能　10',
          ].map((x, i) => (
            <button className={i === 0 ? styles.active : ''} key={x}>
              {x}
            </button>
          ))}
          <h3>按来源</h3>
          {['平台预置　180', '手动添加　46', '自动学习　22'].map((x) => (
            <button key={x}>{x}</button>
          ))}
          <h3>
            待处理 <Tag color="orange">14</Tag>
          </h3>
        </aside>
        <main>
          <div className={styles.stats}>
            <span>
              本月命中 <b>1,247</b> 次
            </span>
            <span>
              未匹配技能 <b>14</b> 个
            </span>
            <span>
              最近更新 <b>08-29</b>
            </span>
          </div>
          <div className={styles.search}>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索标准名或别名"
            />
            <Select defaultValue="全部类别" options={[{ value: '全部类别' }, { value: '框架' }]} />
            <Button type="primary">查询</Button>
            <Button onClick={() => setQuery('')}>重置</Button>
          </div>
          <Table
            rowKey={(r) => r[0]}
            pagination={false}
            scroll={{ x: 760 }}
            columns={[
              { title: '标准名', dataIndex: 0 },
              { title: '别名', dataIndex: 1 },
              { title: '类别', dataIndex: 2 },
              { title: '命中次数', dataIndex: 3 },
              { title: '来源', dataIndex: 4 },
              { title: '状态', render: () => <Tag color="green">启用</Tag> },
              {
                title: '操作',
                render: (_, r) => (
                  <>
                    <Button type="link">编辑</Button>
                    <Button type="link">停用</Button>
                    {r[0] === 'Elasticsearch' && <Tag color="orange">别名歧义</Tag>}
                  </>
                ),
              },
            ]}
            dataSource={data}
          />
          <section className={styles.ambiguous}>
            <h2>
              <ExclamationCircleFilled /> 歧义别名 <Tag color="orange">3</Tag>
            </h2>
            <p>以下别名在不同上下文中可能指向不同技能，已配置上下文判定规则。</p>
            <div>
              {[
                [
                  'AI',
                  'Illustrator：设计、视觉、排版、平面',
                  '人工智能：机器学习、深度学习、模型、算法',
                ],
                ['ES', 'Elasticsearch：搜索、索引、日志', 'ECMAScript：JavaScript、前端、Node'],
                ['PM', '项目管理（软技能）', '产品经理（职位，不作为技能处理）'],
              ].map(([a, l, r]) => (
                <article key={a}>
                  <b>{a}</b>
                  <span>{l}</span>
                  <span>{r}</span>
                  <Button type="link">编辑规则</Button>
                </article>
              ))}
            </div>
          </section>
          <section className={styles.pending}>
            <h2>
              未匹配到标准名的技能 <Tag color="orange">14</Tag>
            </h2>
            <p>解析过程中遇到的、词库中没有的技能名。请判断是否需要加入。</p>
            {['Seata', 'SkyWalking', 'Apache Dubbo', 'ShardingSphere'].map((x, i) => (
              <div key={x}>
                <b>{x}</b>
                <span>
                  {8 - i} 次　08-2{8 + i}
                </span>
                <Select
                  defaultValue={x === 'Apache Dubbo' ? '归入 Dubbo' : '归入现有'}
                  options={[
                    { value: '归入现有' },
                    { value: '新建标准名' },
                    { value: '忽略' },
                    { value: '归入 Dubbo' },
                  ]}
                />
                <Button type="link">去处理</Button>
              </div>
            ))}
            <Button>批量处理</Button>
          </section>
        </main>
      </div>
      <footer>
        ⓘ　同义词库需要有人长期维护。建议指定一位技术背景的同事负责，每两周处理一次待处理列表。这项工作对准确率的影响，大于任何模型调优。
      </footer>
      <Modal
        open={open}
        title="新增词条"
        okText="保存"
        cancelText="取消"
        onCancel={() => setOpen(false)}
        onOk={() => setOpen(false)}
      >
        <Input placeholder="标准名" />
        <Input placeholder="别名，多个别名以逗号分隔" />
        <Select
          placeholder="选择类别"
          options={['编程语言', '框架', '数据库', '中间件', '工具', '云与运维', '软技能'].map(
            (value) => ({ value }),
          )}
        />
      </Modal>
    </div>
  );
}
