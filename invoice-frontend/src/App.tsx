import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { AppLayout } from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import UploadPage from './pages/UploadPage';
import InvoiceDetailPage from './pages/InvoiceDetailPage';

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />
      <AppLayout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/invoice/:id" element={<InvoiceDetailPage />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}