import { render, screen, cleanup } from '@testing-library/vue';
import { afterEach, it, expect } from 'vitest';
import { createRouter, createMemoryHistory } from 'vue-router';
import { h, type Component } from 'vue';
import { ConfigProvider } from 'ant-design-vue';
import zhCN from 'ant-design-vue/es/locale/zh_CN';
afterEach(cleanup);
async function show(Page: Component, url = '/') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  });
  await router.push(url);
  return render(
    { setup: () => () => h(ConfigProvider, { locale: zhCN }, { default: () => h(Page) }) },
    { global: { plugins: [router] } },
  );
}
import InterviewGeneratePage from './interviews/InterviewGeneratePage.vue';

it('没有材料或版本时禁止创建付费面试任务', async () => {
  await show(InterviewGeneratePage);
  expect(screen.getByRole('button', { name: '确认参数并生成' })).toBeDisabled();
  expect(screen.queryByText('张伟')).not.toBeInTheDocument();
});
import InterviewGuidePreviewPage from './interviews/InterviewGuidePreviewPage.vue';
it('缺少题集时安全导出不虚构预览', async () => {
  await show(InterviewGuidePreviewPage);
  expect(screen.getByText('请选择真实题集后预览。')).toBeInTheDocument();
});
import InterviewQuestionSetPage from './interviews/InterviewQuestionSetPage.vue';
it('题集刷新只读且无目标不自动生成', async () => {
  await show(InterviewQuestionSetPage);
  expect(screen.getByText('请选择已保存题集，不会自动生成。')).toBeInTheDocument();
});

import MatchDetailPage from './matching/MatchDetailPage.vue';

it('does not fabricate a match detail without a selected result', async () => {
  await show(MatchDetailPage);
  expect(screen.getByText(/请选择匹配列表/)).toBeInTheDocument();
});

import ResumeCorrectionPage from './resumes/ResumeCorrectionPage.vue';

it('requires a selected candidate for real correction', async () => {
  await show(ResumeCorrectionPage);
  expect(screen.getByText(/请选择简历中心/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '确认并继续匹配' })).toBeDisabled();
});

import SkillSynonymPage from './settings/SkillSynonymPage.vue';
it('缺少部门范围时不读取配置也不假报保存', async () => {
  await show(SkillSynonymPage);
  expect(screen.getByRole('button', { name: '读取配置' })).toBeDisabled();
  expect(screen.queryByText('Kubernetes')).not.toBeInTheDocument();
});
import CandidateProfilePage from './talent/CandidateProfilePage.vue';
it('档案无目标时不展示fixture身份', async () => {
  await show(CandidateProfilePage);
  expect(screen.getByText('请从人才库选择真实候选人。')).toBeInTheDocument();
  expect(screen.queryByText('张伟')).not.toBeInTheDocument();
});
