import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
	plugins: [sveltekit()],
	test: {
		environment: 'jsdom',
		include: ['src/**/*.test.ts'],
		globals: true,
	},
	resolve: {
		alias: {
			$app: 'src/lib/app'
		}
	}
});
