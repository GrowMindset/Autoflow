import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';
import { useAuthStore } from './store/authStore';
import { authService } from './services/authService';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const Root = () => {
  const setAuth = useAuthStore((state) => state.setAuth);
  const setTokenPair = useAuthStore((state) => state.setTokenPair);
  const clearAuth = useAuthStore((state) => state.clearAuth);
  const setLoading = useAuthStore((state) => state.setLoading);

  useEffect(() => {
    const initAuth = async () => {
      let accessToken = localStorage.getItem('token') || '';
      let refreshToken = localStorage.getItem('refresh_token') || '';
      if (!accessToken && !refreshToken) {
        setLoading(false);
        return;
      }

      setLoading(true);
      try {
        if (!accessToken && refreshToken) {
          const refreshed = await authService.refresh(refreshToken);
          accessToken = refreshed.access_token;
          refreshToken = refreshed.refresh_token;
          setTokenPair(accessToken, refreshToken);
        }

        const user = await authService.getMe();
        const latestAccessToken = localStorage.getItem('token') || accessToken;
        const latestRefreshToken = localStorage.getItem('refresh_token') || refreshToken;
        if (!latestAccessToken || !latestRefreshToken) {
          throw new Error('Missing token pair after auth initialization.');
        }
        setAuth(user, latestAccessToken, latestRefreshToken);
      } catch (error: any) {
        console.error('Session restoration failed:', error);
        clearAuth();
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, [setAuth, setTokenPair, clearAuth, setLoading]);

  return (
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
