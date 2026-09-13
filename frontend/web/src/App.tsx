import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AuthPage } from "./pages/AuthPage";
import { DashboardPage } from "./pages/DashboardPage";
import {
  EvidenceReviewPage,
  RewriteReviewPage,
} from "./pages/EvidenceRewriteReviewPage";
import { LandingPage } from "./pages/LandingPage";
import { MembersPage } from "./pages/MembersPage";
import { ExportPage } from "./pages/ExportPage";
import { OrganizationSetupPage } from "./pages/OrganizationSetupPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ProtocolLibraryPage } from "./pages/ProtocolLibraryPage";
import { ReadinessPage } from "./pages/ReadinessPage";
import { RevisionsPage } from "./pages/RevisionsPage";
import { SectionReaderReviewPage } from "./pages/SectionReaderReviewPage";
import { SessionCheckPage } from "./pages/SessionCheckPage";
import { SourceLibraryPage } from "./pages/SourceLibraryPage";
import { WorkspaceInstructionsPage } from "./pages/WorkspaceInstructionsPage";
import { WorkspaceProgressPage } from "./pages/WorkspaceProgressPage";
import { UsagePage } from "./pages/UsagePage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<AuthPage key="signin" mode="signin" />} />
      <Route path="/signup" element={<AuthPage key="signup" mode="signup" />} />
      {import.meta.env.DEV && (
        <>
          <Route
            path="/review/session-check"
            element={<SessionCheckPage />}
          />
          <Route
            path="/review/organization-setup"
            element={<OrganizationSetupPage review />}
          />
          <Route
            path="/review/protocol-library"
            element={<ProtocolLibraryPage review="populated" />}
          />
          <Route
            path="/review/protocol-library/empty"
            element={<ProtocolLibraryPage review="empty" />}
          />
          <Route
            path="/review/protocol-library/create"
            element={<ProtocolLibraryPage review="create" />}
          />
          <Route
            path="/review/workspace-instructions"
            element={<WorkspaceInstructionsPage review="populated" />}
          />
          <Route
            path="/review/workspace-instructions/empty"
            element={<WorkspaceInstructionsPage review="empty" />}
          />
          <Route
            path="/review/workspace-progress"
            element={<WorkspaceProgressPage review="populated" />}
          />
          <Route
            path="/review/workspace-progress/complete"
            element={<WorkspaceProgressPage review="complete" />}
          />
          <Route
            path="/review/workspace-progress/attention"
            element={<WorkspaceProgressPage review="attention" />}
          />
          <Route
            path="/review/workspace-progress/not-started"
            element={<WorkspaceProgressPage review="not-started" />}
          />
          <Route
            path="/review/workbench"
            element={<DashboardPage review="populated" />}
          />
          <Route
            path="/review/workbench/empty"
            element={<DashboardPage review="empty" />}
          />
          <Route
            path="/review/section-reader"
            element={<SectionReaderReviewPage review="draft" />}
          />
          <Route
            path="/review/section-reader/done"
            element={<SectionReaderReviewPage review="done" />}
          />
          <Route
            path="/review/section-reader/empty"
            element={<SectionReaderReviewPage review="empty" />}
          />
          <Route
            path="/review/sources"
            element={<SourceLibraryPage review="populated" />}
          />
          <Route
            path="/review/sources/empty"
            element={<SourceLibraryPage review="empty" />}
          />
          <Route
            path="/review/evidence/pdf"
            element={<EvidenceReviewPage initialKind="pdf" />}
          />
          <Route
            path="/review/evidence/json"
            element={<EvidenceReviewPage initialKind="json" />}
          />
          <Route
            path="/review/evidence/web"
            element={<EvidenceReviewPage initialKind="web" />}
          />
          <Route
            path="/review/evidence/section"
            element={<EvidenceReviewPage initialKind="section" />}
          />
          <Route
            path="/review/rewrite/selection"
            element={<RewriteReviewPage initialStage="selection" />}
          />
          <Route
            path="/review/rewrite/whole"
            element={<RewriteReviewPage initialStage="whole" />}
          />
          <Route
            path="/review/rewrite/alternatives"
            element={<RewriteReviewPage initialStage="alternatives" />}
          />
          <Route
            path="/review/rewrite/confirm"
            element={<RewriteReviewPage initialStage="confirm" />}
          />
          <Route
            path="/review/compare"
            element={<RewriteReviewPage initialStage="compare" />}
          />
          <Route
            path="/review/revisions"
            element={<RevisionsPage review="timeline" />}
          />
          <Route
            path="/review/revisions/preview"
            element={<RevisionsPage review="preview" />}
          />
          <Route
            path="/review/revisions/empty"
            element={<RevisionsPage review="empty" />}
          />
          <Route
            path="/review/revisions/compare"
            element={<RevisionsPage review="compare" />}
          />
          <Route
            path="/review/revisions/restore"
            element={<RevisionsPage review="restore" />}
          />
          <Route
            path="/review/revisions/restored"
            element={<RevisionsPage review="restored" />}
          />
          <Route
            path="/review/readiness"
            element={<ReadinessPage review="incomplete" />}
          />
          <Route
            path="/review/readiness/attention"
            element={<ReadinessPage review="attention" />}
          />
          <Route
            path="/review/readiness/filtered"
            element={<ReadinessPage review="filtered" />}
          />
          <Route
            path="/review/readiness/ready"
            element={<ReadinessPage review="ready" />}
          />
          <Route
            path="/review/readiness/retry"
            element={<ReadinessPage review="retry" />}
          />
          <Route
            path="/review/export"
            element={<ExportPage review="configuration" />}
          />
          <Route
            path="/review/export/drafts"
            element={<ExportPage review="drafts" />}
          />
          <Route
            path="/review/export/building"
            element={<ExportPage review="building" />}
          />
          <Route
            path="/review/export/ready"
            element={<ExportPage review="ready" />}
          />
          <Route
            path="/review/export/failed"
            element={<ExportPage review="failed" />}
          />
          <Route
            path="/review/export/empty"
            element={<ExportPage review="empty" />}
          />
          <Route
            path="/review/usage"
            element={<UsagePage review="populated" />}
          />
          <Route
            path="/review/usage/expanded"
            element={<UsagePage review="expanded" />}
          />
          <Route
            path="/review/usage/running"
            element={<UsagePage review="running" />}
          />
          <Route
            path="/review/usage/empty"
            element={<UsagePage review="empty" />}
          />
          <Route
            path="/review/usage/error"
            element={<UsagePage review="error" />}
          />
          <Route
            path="/review/usage/filtered"
            element={<UsagePage review="filtered" />}
          />
          <Route
            path="/review/profile"
            element={<ProfilePage review="populated" />}
          />
          <Route
            path="/review/profile/loading"
            element={<ProfilePage review="loading" />}
          />
          <Route
            path="/review/profile/error"
            element={<ProfilePage review="error" />}
          />
          <Route
            path="/review/profile/inactive"
            element={<ProfilePage review="inactive" />}
          />
          <Route
            path="/review/members"
            element={<MembersPage review="owner" />}
          />
          <Route
            path="/review/members/admin"
            element={<MembersPage review="admin" />}
          />
          <Route
            path="/review/members/member"
            element={<MembersPage review="member" />}
          />
          <Route
            path="/review/members/success"
            element={<MembersPage review="success" />}
          />
          <Route
            path="/review/members/error"
            element={<MembersPage review="error" />}
          />
        </>
      )}
      <Route element={<ProtectedRoute />}>
        <Route path="/protocols" element={<ProtocolLibraryPage />} />
        <Route
          path="/workspace"
          element={<Navigate to="/protocols" replace />}
        />
        <Route path="/workspace/:conversationId" element={<DashboardPage />} />
        <Route
          path="/workspace/:conversationId/instructions"
          element={<WorkspaceInstructionsPage />}
        />
        <Route
          path="/workspace/:conversationId/progress"
          element={<WorkspaceProgressPage />}
        />
        <Route
          path="/workspace/:conversationId/sources"
          element={<SourceLibraryPage />}
        />
        <Route
          path="/workspace/:conversationId/revisions"
          element={<RevisionsPage />}
        />
        <Route
          path="/workspace/:conversationId/readiness"
          element={<ReadinessPage />}
        />
        <Route
          path="/workspace/:conversationId/export"
          element={<ExportPage />}
        />
        <Route
          path="/workspace/:conversationId/usage"
          element={<UsagePage />}
        />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/organization/members" element={<MembersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
