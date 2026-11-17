import type { Component } from 'vue';
import { mount } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import { it, expect } from 'vitest';
import Page0 from './chat/HrChatPage.vue';
import Page1 from './component-states/HrComponentStatesPage.vue';
import Page2 from './interviews/InterviewGeneratePage.vue';
import Page3 from './interviews/InterviewGuidePreviewPage.vue';
import Page4 from './interviews/InterviewQuestionSetPage.vue';
import Page5 from './matching/FilteredResumesPage.vue';
import Page6 from './matching/MatchDetailPage.vue';
import Page7 from './matching/MatchResultsPage.vue';
import Page8 from './module-entry/HrModuleEntryPage.vue';
import Page9 from './positions/PositionBasicPage.vue';
import Page10 from './positions/PositionDetailPage.vue';
import Page11 from './positions/PositionHardConditionsPage.vue';
import Page12 from './positions/PositionListPage.vue';
import Page13 from './positions/PositionPreviewPage.vue';
import Page14 from './positions/PositionTemplateLibraryPage.vue';
import Page15 from './positions/PositionWeightsPage.vue';
import Page16 from './positions/PositionWizardPage.vue';
import Page17 from './resumes/ResumeCorrectionPage.vue';
import Page18 from './resumes/ResumeProgressPage.vue';
import Page19 from './resumes/ResumeUploadPage.vue';
import Page20 from './settings/AuditPage.vue';
import Page21 from './settings/SkillSynonymPage.vue';
import Page22 from './talent/CandidateProfilePage.vue';
import Page23 from './talent/TalentSearchPage.vue';
import Page24 from './workbench/HrWorkbenchPage.vue';
const pages: [string, Component][] = [
  ['chat/HrChatPage.vue', Page0],
  ['component-states/HrComponentStatesPage.vue', Page1],
  ['interviews/InterviewGeneratePage.vue', Page2],
  ['interviews/InterviewGuidePreviewPage.vue', Page3],
  ['interviews/InterviewQuestionSetPage.vue', Page4],
  ['matching/FilteredResumesPage.vue', Page5],
  ['matching/MatchDetailPage.vue', Page6],
  ['matching/MatchResultsPage.vue', Page7],
  ['module-entry/HrModuleEntryPage.vue', Page8],
  ['positions/PositionBasicPage.vue', Page9],
  ['positions/PositionDetailPage.vue', Page10],
  ['positions/PositionHardConditionsPage.vue', Page11],
  ['positions/PositionListPage.vue', Page12],
  ['positions/PositionPreviewPage.vue', Page13],
  ['positions/PositionTemplateLibraryPage.vue', Page14],
  ['positions/PositionWeightsPage.vue', Page15],
  ['positions/PositionWizardPage.vue', Page16],
  ['resumes/ResumeCorrectionPage.vue', Page17],
  ['resumes/ResumeProgressPage.vue', Page18],
  ['resumes/ResumeUploadPage.vue', Page19],
  ['settings/AuditPage.vue', Page20],
  ['settings/SkillSynonymPage.vue', Page21],
  ['talent/CandidateProfilePage.vue', Page22],
  ['talent/TalentSearchPage.vue', Page23],
  ['workbench/HrWorkbenchPage.vue', Page24],
];
it.each(pages)('渲染完整HR页面 %s', async (_, page) => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  });
  await router.push('/');
  const wrapper = mount(page, {
    props: { title: '模块入口', description: '模块说明', nextPage: '下一页' },
    global: { plugins: [router] },
  });
  expect(wrapper.find('h1').exists()).toBe(true);
  wrapper.unmount();
});
