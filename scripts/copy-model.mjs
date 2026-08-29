import { cp, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const modelRoot = join(repoRoot, 'node_modules', '@spotify', 'basic-pitch', 'model');
const publicRoot = join(repoRoot, 'apps', 'web', 'public', 'basic-pitch-model');

await mkdir(publicRoot, { recursive: true });
await cp(join(modelRoot, 'model.json'), join(publicRoot, 'model.json'));
await cp(join(modelRoot, 'group1-shard1of1.bin'), join(publicRoot, 'group1-shard1of1.bin'));
