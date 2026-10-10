import { writable } from 'svelte/store';
import { browser } from '$app/environment';

function createLocationStore() {
  const { subscribe, set } = writable<{ lat: number; lon: number } | null>(null);

  return {
    subscribe,
    async locate(): Promise<{ lat: number; lon: number }> {
      return new Promise((resolve, reject) => {
        if (!browser || !navigator.geolocation) {
          reject(new Error('Geolocation not supported'));
          return;
        }
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const loc = { lat: pos.coords.latitude, lon: pos.coords.longitude };
            set(loc);
            resolve(loc);
          },
          (err) => reject(err),
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
      });
    },
    set
  };
}

export const userLocation = createLocationStore();
