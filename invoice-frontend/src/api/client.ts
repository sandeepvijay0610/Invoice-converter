import axios from 'axios';
import toast from 'react-hot-toast';

const apiClient = axios.create({
  baseURL: "http://localhost:8081/api",
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.message || error.message || 'Request failed';
    toast.error(message);
    return Promise.reject(error);
  }
);

export default apiClient;