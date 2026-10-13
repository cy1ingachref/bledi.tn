import { defineConfig } from "vite";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    tailwindcss(),
    sveltekit(),
    VitePWA({
      registerType: "autoUpdate",
      // SvelteKit owns the built HTML, so the default 'auto' injection never
      // lands a <script> in the output and the service worker is silently
      // never registered. 'script' emits the registerSW.js tag explicitly.
      injectRegister: "script",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "bledi.tn — Tunisia Transit",
        short_name: "bledi",
        description: "Tunisia public transport routing: bus, metro, train, RFR, louage.",
        theme_color: "#070d18",
        background_color: "#070d18",
        display: "standalone",
        orientation: "portrait",
        start_url: "/",
        icons: [{ src: "favicon.svg", sizes: "any", type: "image/svg+xml" }]
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/server\.arcgisonline\.com\/.*/i,
            handler: "CacheFirst",
            options: {
              cacheName: "esri-tiles",
              expiration: { maxEntries: 800, maxAgeSeconds: 60 * 60 * 24 * 30 }
            }
          },
          {
            urlPattern: /\/api\/v1\/(stations|lines|route).*/i,
            handler: "NetworkFirst",
            options: {
              cacheName: "transit-data",
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 }
            }
          }
        ]
      }
    })
  ],
  build: {
    outDir: "build",
    target: ["es2022", "edge88", "firefox115", "chrome115"],
    minify: "esbuild"
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  },
  preview: {
    port: 8080,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
});
