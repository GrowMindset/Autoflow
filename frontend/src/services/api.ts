import axios from 'axios';
import toast from 'react-hot-toast';
import { useAuthStore } from '../store/authStore';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 120000,
});

const ACCESS_TOKEN_KEY = 'token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const AUTH_BYPASS_PATHS = ['/auth/login', '/auth/signup', '/auth/refresh'];

let refreshPromise: Promise<string | null> | null = null;

// Request interceptor for auth and headers
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  
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
    if (typeof detail.message === 'string' && detail.message.trim()) {
      return detail.message;
    }
    return JSON.stringify(detail);
  }
  
  return data.message || error.message || 'Something went wrong';
};

const isAuthPage = () =>
  window.location.pathname.includes('/login') || window.location.pathname.includes('/signup');

const isAuthBypassRequest = (config: any): boolean => {
  const requestUrl = String(config?.url || '');
  return AUTH_BYPASS_PATHS.some((path) => requestUrl.includes(path));
};

const persistTokenPair = (accessToken: string, refreshToken: string): void => {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  try {
    useAuthStore.getState().setTokenPair(accessToken, refreshToken);
  } catch {
    // Keep localStorage as the source-of-truth fallback for interceptor usage.
  }
};

const clearStoredAuth = (): void => {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  try {
    useAuthStore.getState().clearAuth();
  } catch {
    // Store might be unavailable during early boot errors.
  }
};

const refreshAccessToken = async (): Promise<string | null> => {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!refreshToken) return null;

    try {
      const response = await axios.post(
        `${api.defaults.baseURL}/auth/refresh`,
        { refresh_token: refreshToken },
        { timeout: api.defaults.timeout },
      );

      const accessToken = String(response.data?.access_token || '').trim();
      const rotatedRefreshToken = String(response.data?.refresh_token || '').trim();
      if (!accessToken || !rotatedRefreshToken) {
        return null;
      }

      persistTokenPair(accessToken, rotatedRefreshToken);
      return accessToken;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
};

// Response interceptor for global error handling and auto-logout
api.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const status = error.response?.status;
    const message = getErrorMessage(error);
    const originalRequest = error.config || {};

    if (
      status === 401 &&
      !originalRequest._retry &&
      !isAuthBypassRequest(originalRequest)
    ) {
      originalRequest._retry = true;
      const newAccessToken = await refreshAccessToken();
      if (newAccessToken) {
        if (!originalRequest.headers) {
          originalRequest.headers = {};
        }
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      }

      clearStoredAuth();
      if (!isAuthPage()) {
        toast.error('Session expired. Please login again.');
        window.location.href = '/login';
      } else {
        toast.error(message);
      }
      return Promise.reject(error);
    }

    if (status === 401) {
      clearStoredAuth();
      if (isAuthPage()) {
        toast.error(message);
      } else {
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
