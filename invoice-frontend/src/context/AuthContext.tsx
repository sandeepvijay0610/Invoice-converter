import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { setAuthToken } from '../api/client';

interface AuthContextValue {
  tokenReady: boolean;
}

const AuthContext = createContext<AuthContextValue>({ tokenReady: false });

// Wrap this around your app inside <SignedIn>.
// It fetches the Clerk token ONCE, puts it on axios, then sets tokenReady=true.
// Nothing renders until that's done — so no component can ever fire an API
// call without a valid Authorization header.
export function AuthProvider({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn } = useAuth();
  const [tokenReady, setTokenReady] = useState(false);

  useEffect(() => {
    if (!isSignedIn) return;

    async function init() {
      const token = await getToken();
      setAuthToken(token);
      setTokenReady(true);
    }

    init();

    // Refresh every 55s before Clerk's 60s token expiry
    const interval = setInterval(async () => {
      const token = await getToken();
      setAuthToken(token);
    }, 55_000);

    return () => {
      clearInterval(interval);
      setTokenReady(false);
    };
  }, [isSignedIn, getToken]);

  return (
    <AuthContext.Provider value={{ tokenReady }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useTokenReady() {
  return useContext(AuthContext).tokenReady;
}