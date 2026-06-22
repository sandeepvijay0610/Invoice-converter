import axios from 'axios';
import toast from 'react-hot-toast';

const apiClient = axios.create({
  baseURL: "http://localhost:8081/api",
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use(async (config) => {
  try {
    const clerkModule = await import('@clerk/clerk-react') as any;
    const token = await clerkModule.Clerk?.session?.getToken();
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
  } catch (e) {
    // Clerk not available
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      toast.error("Session expired. Please login again.");
      return Promise.reject(error);
    }
    const message = error.response?.data?.error || error.message || 'Request failed';
    toast.error(message);
    return Promise.reject(error);
  }
);

export default apiClient;