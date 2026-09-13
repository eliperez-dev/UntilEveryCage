import { defineConfig } from 'vitest/config';

// Keep Vitest's Vite 5-compatible runtime isolated from the app's Vite 6 build.
// Component tests can add the Svelte transform once the integration suite lands;
// Phase 2's current tests exercise the framework-independent boundaries.
export default defineConfig({
  test: { environment: 'jsdom', include: ['tests/unit/**/*.test.ts', 'tests/integration/**/*.test.ts'] },
});
