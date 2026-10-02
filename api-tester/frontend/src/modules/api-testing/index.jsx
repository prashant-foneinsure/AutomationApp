import { Route, Routes } from 'react-router-dom'
import GroupDetailPage from './GroupDetailPage.jsx'
import GroupsPage from './GroupsPage.jsx'
import RunHistoryPage from './RunHistoryPage.jsx'
import TestEditorPage from './TestEditorPage.jsx'

// Routes for the API Testing module. This component is what App.jsx mounts
// under /api-testing, and it is the only place that knows these URLs.
export function ApiTestingRoutes() {
  return (
    <Routes>
      <Route index element={<GroupsPage />} />
      <Route path="groups/:groupId" element={<GroupDetailPage />} />
      <Route path="groups/:groupId/tests/new" element={<TestEditorPage />} />
      <Route path="groups/:groupId/tests/:testId" element={<TestEditorPage />} />
      <Route path="tests/:testId/history" element={<RunHistoryPage />} />
      <Route path="*" element={<div className="notice warn">Page not found.</div>} />
    </Routes>
  )
}
