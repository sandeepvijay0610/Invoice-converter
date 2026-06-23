import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { SignedIn, SignedOut, SignIn, useAuth } from '@clerk/clerk-react';
import { AppLayout } from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import InvoiceDetailPage from './pages/InvoiceDetailPage';
import BatchUpload from './components/upload/BatchUpload';
import { setAuthTokenProvider } from './api/client';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let isMounted = true;

    const initSecureSession = async () => {
      // 1. Give Axios the ability to fetch tokens
      setAuthTokenProvider(getToken);
      
      // 2. Await the token to guarantee Clerk is fully hydrated
      const token = await getToken();
      
      // 3. ONLY unlock the UI if the token successfully loaded
      if (isMounted && token) {
        setIsReady(true);
      }
    };

    initSecureSession();

    return () => { isMounted = false; };
  }, [isLoaded, isSignedIn, getToken]);

  // Block all rendering until Axios is primed and ready
  if (!isReady) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50">
        <div className="w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin mb-4"></div>
        <div className="text-gray-500 font-medium text-sm">Securing session...</div>
      </div>
    );
  }

  return <>{children}</>;
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
        <AuthGuard>
          <AppLayout>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/batch-upload" element={<BatchUpload />} />
              <Route path="/invoice/:id" element={<InvoiceDetailPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </AppLayout>
        </AuthGuard>
      </SignedIn>
    </BrowserRouter>
  );
}