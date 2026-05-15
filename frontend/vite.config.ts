import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const apiTarget = env.VITE_API_URL || 'http://localhost:8000';
  const isNgrokTarget = /https?:\/\/[^/]*ngrok(-free)?\.app|https?:\/\/[^/]*ngrok-free\.dev/i.test(
    apiTarget,
  );

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
          headers: isNgrokTarget
            ? { 'ngrok-skip-browser-warning': 'true' }
            : undefined,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  };
});
