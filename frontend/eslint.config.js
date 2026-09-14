export default [
  { ignores: ['dist/**', 'node_modules/**', 'test-results/**', '**/*.ts', '**/*.svelte'] },
  {
    files: ['**/*.js', '**/*.mjs'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: { console: 'readonly', process: 'readonly', fetch: 'readonly' } },
    rules: { 'no-undef': 'error', 'no-unused-vars': 'warn' },
  },
];
