import { useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { setAuthToken } from '../api/client';

// This hook runs inside <SignedIn> so Clerk is guaranteed to be ready.
// It fetches the JWT once on mount and refreshes it every 55 seconds
// (Clerk tokens expire after 60s by default).
export function useAuthSetup() {
  const { getToken, isSignedIn } = useAuth();

  useEffect(() => {
    if (!isSignedIn) return;

    async function refreshToken() {
      const token = await getToken();
      setAuthToken(token);
    }

    // Set immediately
    refreshToken();

    // Refresh every 55 seconds before the 60s expiry
    const interval = setInterval(refreshToken, 55_000);
    return () => clearInterval(interval);
  }, [isSignedIn, getToken]);
}