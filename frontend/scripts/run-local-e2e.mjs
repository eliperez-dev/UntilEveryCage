import { spawnSync } from 'node:child_process';

const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const result = spawnSync(npx, ['playwright', 'test', 'tests/e2e/local-backend.spec.ts'], {
  stdio: 'inherit',
  env: { ...process.env, LOCAL_V2_E2E: '1' },
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);
