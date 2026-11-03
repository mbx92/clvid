import {build} from 'esbuild';
import {spawnSync} from 'node:child_process';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
await build({entryPoints: [resolve(root, 'tests/captions.test.ts')], outfile: resolve(root, '.test-build/captions.test.mjs'), bundle: true, platform: 'node', format: 'esm', packages: 'external'});
const result = spawnSync(process.execPath, ['--test', '.test-build/captions.test.mjs', 'tests/runtime.test.mjs'], {cwd: root, stdio: 'inherit'});
process.exitCode = result.status ?? 1;
