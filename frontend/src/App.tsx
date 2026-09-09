import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import DocumentList from './pages/DocumentList'
import DocumentDetails from './pages/DocumentDetails'
import Progress from './pages/Progress'
import TerminologyPage from './pages/Terminology'
import MemoryPage from './pages/Memory'
import CompletedDocuments from './pages/CompletedDocuments'
import SettingsPage from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/documents" element={<DocumentList />} />
          <Route path="/documents/:id" element={<DocumentDetails />} />
          <Route path="/progress/:jobId" element={<Progress />} />
          <Route path="/terminology" element={<TerminologyPage />} />
          <Route path="/memory" element={<MemoryPage />} />
          <Route path="/completed" element={<CompletedDocuments />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Dashboard />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
