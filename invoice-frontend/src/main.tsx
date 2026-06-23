import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      <App />
    </ClerkProvider>
  </StrictMode>,
)
