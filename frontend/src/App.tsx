import { Routes, Route, Navigate } from 'react-router-dom'
import { DashboardLayout } from './layouts/DashboardLayout'
import { OverviewPage } from './pages/OverviewPage'
import { ChatPage } from './pages/ChatPage'
import { MemoryExplorerPage } from './pages/MemoryExplorerPage'
import { MemoryDetailPage } from './pages/MemoryDetailPage'
import { EditMemoryPage } from './pages/EditMemoryPage'
import { CreateMemoryPage } from './pages/CreateMemoryPage'
import { ConflictCenterPage } from './pages/ConflictCenterPage'
import { CustomInstructionsPage } from './pages/CustomInstructionsPage'
import { SettingsPage } from './pages/SettingsPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<DashboardLayout />}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="overview" element={<OverviewPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="memories" element={<MemoryExplorerPage />} />
        <Route path="memories/new" element={<CreateMemoryPage />} />
        <Route path="memories/:id" element={<MemoryDetailPage />} />
        <Route path="memories/:id/edit" element={<EditMemoryPage />} />
        <Route path="conflicts" element={<ConflictCenterPage />} />
        <Route path="instructions" element={<CustomInstructionsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  )
}

export default App