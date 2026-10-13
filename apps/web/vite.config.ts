import { defineConfig } from "vitest/config";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

const ACCOUNTS_PREFIXES = [
  "/api/v1/auth/",
  "/api/v1/users/",
  "/api/v1/memories",
  "/api/v1/favorites",
  "/api/v1/friendships",
  "/api/v1/location-shares",
];

// Same prefix map as nginx.conf. Vite tries the keys in order, so the
// accounts prefixes must come before the catch-all /api.
const proxy = {
  ...Object.fromEntries(
    ACCOUNTS_PREFIXES.map((p) => [p, { target: "http://localhost:3000", changeOrigin: true }])
  ),
  "/api": { target: "http://localhost:8000", changeOrigin: true },
};

export default defineConfig({
  plugins: [
    tailwindcss(),
    sveltekit(),
    VitePWA({
      registerType: "autoUpdate",
      // SvelteKit writes index.html after the plugin's HTML transform, so an
      // injected registration never lands; +layout.svelte registers instead.
      injectRegister: false,
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
    proxy
  },
  preview: {
    port: 8080,
    host: "127.0.0.1",
    proxy
  }
});
