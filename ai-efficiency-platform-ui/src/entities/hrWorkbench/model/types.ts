export type HrWorkbenchTodoTone = 'warning' | 'info';

export interface HrWorkbenchQuickAction {
  key: 'upload' | 'matching' | 'interview' | 'position';
  title: string;
  description: string;
  route: string;
}

export interface HrWorkbenchMetric {
  label: string;
  value: string;
  comparisonText: string;
  tone: 'positive' | 'warning';
}

export interface HrWorkbenchTodo {
  id: string;
  content: string;
  detail: string;
  actionLabel: string;
  route: string;
  tone: HrWorkbenchTodoTone;
}

export interface HrPositionProgress {
  id: string;
  name: string;
  matched: number;
  stronglyRecommended: number;
  recommended: number;
  reviewSuggested: number;
  notRecommended: number;
  filtered: number;
}

export interface HrWorkbenchActivity {
  id: string;
  time: string;
  actor: '你' | '系统';
  content: string;
}

export interface HrWorkbenchViewModel {
  greeting: string;
  dateText: string;
  quickActions: readonly HrWorkbenchQuickAction[];
  metrics: readonly HrWorkbenchMetric[];
  todos: readonly HrWorkbenchTodo[];
  positions: readonly HrPositionProgress[];
  activities: readonly HrWorkbenchActivity[];
}
