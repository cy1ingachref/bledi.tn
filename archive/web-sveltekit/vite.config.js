import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    port: 8080,
    strictPort: true,
    proxy: {
      // The accounts service comes first: Vite matches proxy contexts in insertion
      // order and takes the first hit, so the catch-all '/api' has to come last or it
      // would swallow every accounts route and send it to the transit service.
      '/api/v1/auth': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      '/api/v1/users': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      '/api/v1/memories': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      '/api/v1/media': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      '/api/v1/favorites': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      '/api/v1/friendships': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      '/api/v1/location-shares': {
        target: 'http://localhost:3000',
        changeOrigin: true,
        secure: false
      },
      // Rust routing service (transit-routing :8081). Strip /routing so
      // /routing/route -> :8081/route and /routing/health -> :8081/health.
      '/routing': {
        target: 'http://localhost:8081',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path.replace(/^\/routing/, '')
      },
      // Everything else is the transit service.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  }
});
