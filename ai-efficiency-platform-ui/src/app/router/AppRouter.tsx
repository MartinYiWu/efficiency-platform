import { Navigate, Route, Routes } from 'react-router';

import { HrComponentStatesPage } from '../../pages/hr-assistant/component-states/HrComponentStatesPage';
import { HrChatPage } from '../../pages/hr-assistant/chat/HrChatPage';
import { OperationsChatPage } from '../../pages/operations-assistant/chat/OperationsChatPage';
import { HrModuleEntryPage } from '../../pages/hr-assistant/module-entry/HrModuleEntryPage';
import { ResumeUploadPage } from '../../pages/hr-assistant/resumes/ResumeUploadPage';
import { ResumeProgressPage } from '../../pages/hr-assistant/resumes/ResumeProgressPage';
import { ResumeCorrectionPage } from '../../pages/hr-assistant/resumes/ResumeCorrectionPage';
import { CandidateProfilePage } from '../../pages/hr-assistant/talent/CandidateProfilePage';
import { TalentSearchPage } from '../../pages/hr-assistant/talent/TalentSearchPage';
import { SkillSynonymPage } from '../../pages/hr-assistant/settings/SkillSynonymPage';
import { AuditPage } from '../../pages/hr-assistant/settings/AuditPage';
import { MatchResultsPage } from '../../pages/hr-assistant/matching/MatchResultsPage';
import { MatchDetailPage } from '../../pages/hr-assistant/matching/MatchDetailPage';
import { FilteredResumesPage } from '../../pages/hr-assistant/matching/FilteredResumesPage';
import { InterviewGeneratePage } from '../../pages/hr-assistant/interviews/InterviewGeneratePage';
import { InterviewQuestionSetPage } from '../../pages/hr-assistant/interviews/InterviewQuestionSetPage';
import { InterviewGuidePreviewPage } from '../../pages/hr-assistant/interviews/InterviewGuidePreviewPage';
import { HrWorkbenchPage } from '../../pages/hr-assistant/workbench/HrWorkbenchPage';
import { PositionBasicPage } from '../../pages/hr-assistant/positions/PositionBasicPage';
import { PositionHardConditionsPage } from '../../pages/hr-assistant/positions/PositionHardConditionsPage';
import { PositionDetailPage } from '../../pages/hr-assistant/positions/PositionDetailPage';
import { PositionListPage } from '../../pages/hr-assistant/positions/PositionListPage';
import { PositionTemplateLibraryPage } from '../../pages/hr-assistant/positions/PositionTemplateLibraryPage';
import { PositionPreviewPage } from '../../pages/hr-assistant/positions/PositionPreviewPage';
import { PositionWizardPage } from '../../pages/hr-assistant/positions/PositionWizardPage';
import { PositionWeightsPage } from '../../pages/hr-assistant/positions/PositionWeightsPage';
import { NotFoundPage } from '../../pages/not-found/NotFoundPage';
import { HrAssistantShell } from '../../widgets/hrAssistantShell';

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate replace to="/ai-assistants/hr/workbench" />} />
      <Route
        path="/ai-assistants/operations/chat"
        element={
          <HrAssistantShell>
            <OperationsChatPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/chat"
        element={
          <HrAssistantShell>
            <HrChatPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/resumes"
        element={<Navigate replace to="/ai-assistants/hr/resumes/upload" />}
      />
      <Route
        path="/ai-assistants/hr/resumes/upload"
        element={
          <HrAssistantShell>
            <ResumeUploadPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/resumes/batches/:batchId"
        element={
          <HrAssistantShell>
            <ResumeProgressPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/resumes/candidates/:candidateId/confirm"
        element={
          <HrAssistantShell>
            <ResumeCorrectionPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/settings/audit"
        element={
          <HrAssistantShell>
            <AuditPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/settings/synonyms"
        element={
          <HrAssistantShell>
            <SkillSynonymPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/talent"
        element={
          <HrAssistantShell>
            <TalentSearchPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/talent/:candidateId"
        element={
          <HrAssistantShell>
            <CandidateProfilePage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/matching"
        element={
          <HrAssistantShell>
            <MatchResultsPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/matching/:candidateId"
        element={
          <HrAssistantShell>
            <MatchDetailPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/matching/filtered"
        element={
          <HrAssistantShell>
            <FilteredResumesPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/interviews/guide"
        element={
          <HrAssistantShell>
            <InterviewGuidePreviewPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/interviews/questions"
        element={
          <HrAssistantShell>
            <InterviewQuestionSetPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/interviews/generate"
        element={
          <HrAssistantShell>
            <InterviewGeneratePage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/interviews"
        element={
          <HrAssistantShell>
            <HrModuleEntryPage
              title="面试准备"
              description="配置、编辑与导出结构化面试指南。"
              nextPage="PAGE-16 面试题生成配置"
            />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/settings"
        element={
          <HrAssistantShell>
            <SkillSynonymPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/workbench"
        element={
          <HrAssistantShell>
            <HrWorkbenchPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/component-states"
        element={
          <HrAssistantShell>
            <HrComponentStatesPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions"
        element={
          <HrAssistantShell>
            <PositionListPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/templates"
        element={
          <HrAssistantShell>
            <PositionTemplateLibraryPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/:positionId"
        element={
          <HrAssistantShell>
            <PositionDetailPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/new"
        element={
          <HrAssistantShell>
            <PositionBasicPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/new/soft-requirements"
        element={
          <HrAssistantShell>
            <PositionWizardPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/new/hard-conditions"
        element={
          <HrAssistantShell>
            <PositionHardConditionsPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/new/preview"
        element={
          <HrAssistantShell>
            <PositionPreviewPage />
          </HrAssistantShell>
        }
      />
      <Route
        path="/ai-assistants/hr/positions/new/weights"
        element={
          <HrAssistantShell>
            <PositionWeightsPage />
          </HrAssistantShell>
        }
      />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
