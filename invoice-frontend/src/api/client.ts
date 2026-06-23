import axios from 'axios';
import toast from 'react-hot-toast';

// Store the Clerk getToken function dynamically
let getTokenProvider: (() => Promise<string | null>) | null = null;

export const setAuthTokenProvider = (provider: () => Promise<string | null>) => {
  getTokenProvider = provider;
};

const apiClient = axios.create({
  baseURL: "http://localhost:8081/api",
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// INTERCEPTOR 1: Guarantee the freshest token is attached before the request leaves
apiClient.interceptors.request.use(async (config) => {
  if (getTokenProvider) {
    const token = await getTokenProvider();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// INTERCEPTOR 2: Defeat the "Clock Skew" NBF error
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // If Spring Boot throws a 401, wait 2 seconds for its clock to catch up and retry once
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      if (getTokenProvider) {
        const token = await getTokenProvider();
        if (token) {
          originalRequest.headers.Authorization = `Bearer ${token}`;
        }
      }
      return apiClient(originalRequest);
    }

    const message = error.response?.data?.error || error.message || 'Request failed';
    
    // Suppress toasts for 401s (Clerk handles UI for real session expiries)
    if (error.response?.status !== 401) {
      toast.error(message);
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;