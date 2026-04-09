import axios from 'axios';
import toast from 'react-hot-toast';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
});

// Request interceptor for auth and headers
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  
  if (config.headers) {
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Only set default Content-Type if not already specified (allows FormData)
    if (!config.headers['Content-Type']) {
      config.headers['Content-Type'] = 'application/json';
    }
  }
  
  return config;
}, (error) => {
  return Promise.reject(error);
});

// Helper to extract error message safely
const getErrorMessage = (error: any): string => {
  const data = error.response?.data;
  
  if (!data) return error.message || 'Something went wrong';
  
  // FastAPI detail can be a string, object, or array
  const detail = data.detail;
  
  if (typeof detail === 'string') return detail;
  
  if (Array.isArray(detail)) {
    // Extract first validation error: [{ "msg": "...", ... }]
    return detail.map(err => {
        if (typeof err === 'string') return err;
        return err?.msg || JSON.stringify(err);
    }).join(', ');
  }
  
  if (typeof detail === 'object' && detail !== null) {
    return JSON.stringify(detail);
  }
  
  return data.message || error.message || 'Something went wrong';
};

// Response interceptor for global error handling and auto-logout
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    const status = error.response?.status;
    const message = getErrorMessage(error);

    if (status === 401) {
      localStorage.removeItem('token');
      if (!window.location.pathname.includes('/login') && !window.location.pathname.includes('/signup')) {
        toast.error('Session expired. Please login again.');
        window.location.href = '/login';
      }
    } else {
      toast.error(message);
    }
    
    return Promise.reject(error);
  }
);

export default api;
