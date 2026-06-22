import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { SignedIn, SignedOut, SignIn } from '@clerk/clerk-react';
import { AppLayout } from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import InvoiceDetailPage from './pages/InvoiceDetailPage';
import BatchUpload from './components/upload/BatchUpload';

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />
      <SignedOut>
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <SignIn />
        </div>
      </SignedOut>
      <SignedIn>
        <AppLayout>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/batch-upload" element={<BatchUpload />} />
            <Route path="/invoice/:id" element={<InvoiceDetailPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppLayout>
      </SignedIn>
    </BrowserRouter>
  );
}