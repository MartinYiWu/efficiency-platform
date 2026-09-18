import {
  AppstoreOutlined,
  ArrowRightOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  FormOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { Button, Card, Empty, Statistic, Typography } from 'antd';
import { useNavigate } from 'react-router';

import {
  hrWorkbenchFixture,
  type HrWorkbenchQuickAction,
  type HrWorkbenchViewModel,
} from '../../../entities/hrWorkbench';
import styles from './HrWorkbenchPage.module.css';

interface HrWorkbenchPageProps {
  viewModel?: HrWorkbenchViewModel;
}

function QuickActionIcon({ action }: { action: HrWorkbenchQuickAction }) {
  if (action.key === 'upload') return <FileTextOutlined />;
  if (action.key === 'matching') return <AppstoreOutlined />;
  if (action.key === 'interview') return <FormOutlined />;
  return <FolderOpenOutlined />;
}

export function HrWorkbenchPage({ viewModel = hrWorkbenchFixture }: HrWorkbenchPageProps) {
  const navigate = useNavigate();
  const hasData = viewModel.positions.length > 0;

  return (
    <div className={styles.page}>
      <section className={styles.welcome} aria-labelledby="hr-workbench-title">
        <div>
          <Typography.Title id="hr-workbench-title" level={1} className={styles.pageTitle}>
            工作台
          </Typography.Title>
          <Typography.Title level={2} className={styles.greeting}>
            {viewModel.greeting}
          </Typography.Title>
          <Typography.Text className={styles.dateText}>{viewModel.dateText}</Typography.Text>
        </div>
        <div className={styles.welcomeActions}>
          <Button type="primary" onClick={() => navigate('/ai-assistants/hr/resumes/upload')}>
            上传简历
          </Button>
          <Button onClick={() => navigate('/ai-assistants/hr/positions/new')}>新建岗位</Button>
        </div>
      </section>

      <section className={styles.quickGrid} aria-label="快捷入口">
        {viewModel.quickActions.map((action) => (
          <Button
            key={action.key}
            className={styles.quickAction}
            type="text"
            onClick={() => navigate(action.route)}
          >
            <span className={styles.quickIcon}>
              <QuickActionIcon action={action} />
            </span>
            <span className={styles.quickCopy}>
              <span>{action.title}</span>
              <span>{action.description}</span>
            </span>
            <RightOutlined className={styles.quickArrow} />
          </Button>
        ))}
      </section>

      <section className={styles.metricGrid} aria-label="本周概览">
        {viewModel.metrics.map((metric) => (
          <Card key={metric.label} className={styles.metricCard}>
            <Typography.Text className={styles.metricLabel}>{metric.label}</Typography.Text>
            <Statistic
              value={metric.value}
              className={metric.tone === 'warning' ? styles.warningValue : styles.metricValue}
            />
            <Typography.Text
              className={
                metric.tone === 'warning' ? styles.warningComparison : styles.positiveComparison
              }
            >
              {metric.comparisonText}
            </Typography.Text>
          </Card>
        ))}
      </section>

      {hasData ? (
        <div
          className={styles.contentGrid}
          data-layout="balanced"
          data-testid="workbench-main-grid"
        >
          <Card
            className={styles.todosCard}
            title={
              <Typography.Title level={2} className={styles.cardTitle}>
                需要你处理
              </Typography.Title>
            }
            extra={<span className={styles.todoCount}>{viewModel.todos.length}</span>}
          >
            <div className={styles.todoList}>
              {viewModel.todos.map((todo) => (
                <div key={todo.id} className={styles.todoItem}>
                  <span
                    className={todo.tone === 'warning' ? styles.warningDot : styles.infoDot}
                    aria-hidden="true"
                  />
                  <div className={styles.todoCopy}>
                    <Typography.Text strong>{todo.content}</Typography.Text>
                    <Typography.Text>{todo.detail}</Typography.Text>
                  </div>
                  <Button type="link" onClick={() => navigate(todo.route)}>
                    {todo.actionLabel}
                  </Button>
                </div>
              ))}
            </div>
          </Card>

          <Card
            className={styles.positionsCard}
            title={
              <Typography.Title level={2} className={styles.cardTitle}>
                岗位匹配进展
              </Typography.Title>
            }
            extra={
              <Button type="link" onClick={() => navigate('/ai-assistants/hr/positions')}>
                查看全部 <ArrowRightOutlined />
              </Button>
            }
          >
            <div className={styles.tableScroll}>
              <table className={styles.positionTable}>
                <thead>
                  <tr>
                    <th>岗位</th>
                    <th>已匹配</th>
                    <th>强烈推荐</th>
                    <th>推荐</th>
                    <th>建议复核</th>
                    <th>暂不推荐</th>
                    <th>被过滤</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {viewModel.positions.map((position) => (
                    <tr key={position.id}>
                      <td>{position.name}</td>
                      <td>{position.matched}</td>
                      <td className={styles.stronglyRecommended}>{position.stronglyRecommended}</td>
                      <td className={styles.recommended}>{position.recommended}</td>
                      <td className={styles.reviewSuggested}>{position.reviewSuggested}</td>
                      <td className={styles.notRecommended}>{position.notRecommended}</td>
                      <td
                        className={
                          position.filtered / position.matched > 0.4
                            ? styles.filteredWarning
                            : undefined
                        }
                      >
                        {position.filtered}
                      </td>
                      <td>
                        <Button
                          type="link"
                          onClick={() =>
                            navigate(`/ai-assistants/hr/matching?position=${position.id}`)
                          }
                        >
                          查看
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card
            className={styles.activitiesCard}
            title={
              <Typography.Title level={2} className={styles.cardTitle}>
                最近活动
              </Typography.Title>
            }
          >
            <ol className={styles.activityList}>
              {viewModel.activities.map((activity) => (
                <li key={activity.id}>
                  <time>{activity.time}</time>
                  <Typography.Text strong>{activity.actor}</Typography.Text>
                  <Typography.Text>{activity.content}</Typography.Text>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      ) : (
        <Card className={styles.emptyCard}>
          <Empty description={<span>开始使用 AI 人事助手</span>}>
            <div className={styles.onboardingSteps}>
              <div>
                <strong>1. 配置岗位</strong>
                <span>和用人经理一起把要求说清楚</span>
                <Button onClick={() => navigate('/ai-assistants/hr/positions/new')}>
                  新建岗位
                </Button>
              </div>
              <div>
                <strong>2. 上传简历</strong>
                <span>支持批量上传与压缩包</span>
                <Button disabled>上传简历</Button>
              </div>
              <div>
                <strong>3. 查看结果</strong>
                <span>看排序、看理由、生成面试题</span>
                <Button disabled>查看结果</Button>
              </div>
            </div>
            <Button type="link">查看使用指南</Button>
          </Empty>
        </Card>
      )}
    </div>
  );
}
