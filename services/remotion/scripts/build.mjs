import {mkdir, copyFile, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {build} from 'esbuild';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
await mkdir(resolve(root, 'public/fonts'), {recursive: true});
await copyFile(resolve(root, '../backend/fonts/NotoSans-Regular.ttf'), resolve(root, 'public/fonts/NotoSans-Regular.ttf'));
await copyFile(resolve(root, '../backend/fonts/OFL.txt'), resolve(root, 'public/fonts/OFL.txt'));
await bundle({entryPoint: resolve(root, 'src/index.tsx'), outDir: resolve(root, 'dist/composition'), publicDir: resolve(root, 'public')});
await build({entryPoints: [resolve(root, 'src/player.tsx')], outfile: resolve(root, 'dist/player.js'), bundle: true,
  format: 'iife', platform: 'browser', target: ['es2022'], minify: true,
  define: {'process.env.NODE_ENV': '"production"'}, legalComments: 'eof'});
await build({entryPoints: [resolve(root, 'src/story-player.tsx')], outfile: resolve(root, 'dist/story-player.js'), bundle: true,
  format: 'iife', platform: 'browser', target: ['es2022'], minify: true,
  define: {'process.env.NODE_ENV': '"production"'}, legalComments: 'eof'});
const notices = await Promise.all([
  ['Remotion', 'node_modules/remotion/LICENSE.md'],
  ['React and React DOM', 'node_modules/react/LICENSE'],
  ['Scheduler', 'node_modules/scheduler/LICENSE'],
  ['Noto Sans', 'public/fonts/OFL.txt'],
].map(async ([name, file]) => `${name}\n${'='.repeat(name.length)}\n${await readFile(resolve(root, file), 'utf8')}`));
await writeFile(resolve(root, 'dist/THIRD-PARTY-NOTICES.txt'), notices.join('\n\n'));
console.log('Remotion composition and preview built.');
