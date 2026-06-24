import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
// 1. Import React Query
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

// FIX: Guard against missing env var — previously this silently passed
// undefined to ClerkProvider which caused a blank/broken screen with no error.
if (!PUBLISHABLE_KEY) {
  throw new Error(
    'Missing VITE_CLERK_PUBLISHABLE_KEY. ' +
    'Create a .env file in invoice-frontend/ with your Clerk publishable key:\n' +
    'VITE_CLERK_PUBLISHABLE_KEY=pk_test_...'
  )
}

// 2. Create the QueryClient instance
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Optional but highly recommended: Prevents the app from re-fetching data 
      // every single time you click away and click back to the browser tab.
      refetchOnWindowFocus: false, 
      retry: 1, // Only retry failed API requests once before throwing an error
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      {/* 3. Wrap your App with the Provider */}
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
)