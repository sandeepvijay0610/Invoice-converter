import axios from 'axios';
import toast from 'react-hot-toast';

const apiClient = axios.create({
  baseURL: "http://localhost:8081/api",
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Token is set externally by useAuthSetup hook once Clerk is ready.
// This avoids the window.Clerk polling race condition entirely.
export function setAuthToken(token: string | null) {
  if (token) {
    apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common['Authorization'];
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Don't redirect on 401 — just show the error and reject.
    // Clerk handles session expiry via its own UI.
    const message = error.response?.data?.error || error.message || 'Request failed';
    toast.error(message);
    return Promise.reject(error);
  }
);

export default apiClient;