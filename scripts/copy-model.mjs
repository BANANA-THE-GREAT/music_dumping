import { cp, mkdir } from 'node:fs/promises';

await mkdir('public/basic-pitch-model', { recursive: true });
await cp('node_modules/@spotify/basic-pitch/model/model.json', 'public/basic-pitch-model/model.json');
await cp('node_modules/@spotify/basic-pitch/model/group1-shard1of1.bin', 'public/basic-pitch-model/group1-shard1of1.bin');
