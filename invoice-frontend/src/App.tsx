import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { SignedIn, SignedOut, SignIn } from '@clerk/clerk-react';
import { AuthProvider, useTokenReady } from './context/AuthContext';
import { AppLayout } from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import InvoiceDetailPage from './pages/InvoiceDetailPage';
import BatchUpload from './components/upload/BatchUpload';

// Inner component — only renders pages once the token is on axios
function AuthenticatedApp() {
  const tokenReady = useTokenReady();

  if (!tokenReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400 text-sm">Loading...</div>
      </div>
    );
  }

  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/batch-upload" element={<BatchUpload />} />
        <Route path="/invoice/:id" element={<InvoiceDetailPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppLayout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" />

      <SignedOut>
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <Routes>
            <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />
            <Route path="*" element={<Navigate to="/sign-in" replace />} />
          </Routes>
        </div>
      </SignedOut>

      <SignedIn>
        {/* AuthProvider fetches the token and puts it on axios.
            AuthenticatedApp waits for tokenReady before rendering any page.
            This makes it impossible for any hook to fire an API call
            without a valid Authorization header — no retries needed. */}
        <AuthProvider>
          <AuthenticatedApp />
        </AuthProvider>
      </SignedIn>
    </BrowserRouter>
  );
}