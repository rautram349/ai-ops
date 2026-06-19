import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { MainLayout } from "./components/layout/MainLayout";
import { Spinner } from "./components/ui/Spinner";

const ChatView = lazy(() => import("./views/ChatView"));
const ApprovalsView = lazy(() => import("./views/ApprovalsView"));
const IncidentsView = lazy(() => import("./views/IncidentsView"));
const IncidentDetailView = lazy(() => import("./views/IncidentDetailView"));

function PageFallback() {
  return (
    <div className="flex items-center justify-center h-full min-h-[60vh]">
      <Spinner size="lg" />
    </div>
  );
}

export default function App() {
  return (
    <MainLayout>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatView />} />
          <Route path="/chat/:conversationId" element={<ChatView />} />
          <Route path="/approvals" element={<ApprovalsView />} />
          <Route path="/incidents" element={<IncidentsView />} />
          <Route
            path="/incidents/:incidentId"
            element={<IncidentDetailView />}
          />
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </Suspense>
    </MainLayout>
  );
}
