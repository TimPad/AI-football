import { Navigate, Route, Routes } from 'react-router-dom';
import { CaptainAuthProvider, CaptainLogin, CaptainPrivate, CaptainRegister, CaptainTokenPage } from './CaptainAuth';
import { CaptainApplications, CaptainEntryPage } from './CaptainEntryPage';
import { CaptainIdentityReview, CaptainIdentityTasks } from './CaptainIdentityReview';
import { CaptainShell } from './CaptainShell';
import { CaptainHome, CaptainRosterImportPage, CaptainTeamPage } from './CaptainTeamPage';
export function CaptainRoutes() {
  return (
    <CaptainAuthProvider>
      <Routes>
        <Route path="login" element={<CaptainLogin />} />
        <Route path="register" element={<CaptainRegister />} />
        <Route path="verify" element={<CaptainTokenPage kind="verify" />} />
        <Route path="password-reset" element={<CaptainTokenPage kind="reset" />} />
        <Route path="invitation" element={<CaptainTokenPage kind="invitation" />} />
        <Route
          element={
            <CaptainPrivate>
              <CaptainShell />
            </CaptainPrivate>
          }
        >
          <Route index element={<CaptainHome />} />
          <Route path="identity-tasks" element={<CaptainIdentityTasks />} />
          <Route path="identity-tasks/:taskId" element={<CaptainIdentityReview />} />
          <Route path="teams/new" element={<CaptainTeamPage />} />
          <Route path="teams/:id/applications" element={<CaptainApplications />} />
          <Route path="applications/:id" element={<CaptainEntryPage />} />
          <Route path="teams/:id" element={<CaptainTeamPage />} />
          <Route path="roster-imports/:id" element={<CaptainRosterImportPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/captain" replace />} />
      </Routes>
    </CaptainAuthProvider>
  );
}
