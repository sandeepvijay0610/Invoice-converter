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
    // FIX: every error body the backend actually sends uses {"error": "..."}
    // (see request-upload, /process, /retry in InvoiceController) — but this
    // only ever looked for `.message`, so real backend error text (like
    // "Upload not found in storage...") never reached the toast and fell
    // back to a generic Axios message instead.
    const message =
      error.response?.data?.error ||
      error.response?.data?.message ||
      error.message ||
      'Request failed';
    toast.error(message);
    return Promise.reject(error);
  }
);

export default apiClient;