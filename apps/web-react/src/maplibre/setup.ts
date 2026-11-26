import { setWorkerUrl } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

// Vite pre-bundles maplibre-gl into a single dependency chunk, so its default
// worker (which relies on `new URL(import.meta.url)`) resolves to the wrong
// path. Point MapLibre at the real worker asset explicitly.
export function setupMapLibreWorker() {
  setWorkerUrl(workerUrl);
}
