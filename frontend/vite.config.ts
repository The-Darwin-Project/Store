import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/products': 'http://localhost:8080',
      '/orders': 'http://localhost:8080',
      '/customers': 'http://localhost:8080',
      '/suppliers': 'http://localhost:8080',
      '/dashboard': 'http://localhost:8080',
      '/alerts': 'http://localhost:8080',
      '/coupons': 'http://localhost:8080',
      '/invoices': 'http://localhost:8080',
      '/reviews': 'http://localhost:8080',
      '/campaigns': 'http://localhost:8080',
      '/auth': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    cssCodeSplit: true,
  },
});
