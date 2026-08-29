import { mkdir, writeFile } from 'node:fs/promises';
const rate=22050,duration=4,frames=rate*duration,data=Buffer.alloc(44+frames*2);
data.write('RIFF');data.writeUInt32LE(36+frames*2,4);data.write('WAVE',8);data.write('fmt ',12);data.writeUInt32LE(16,16);data.writeUInt16LE(1,20);data.writeUInt16LE(1,22);data.writeUInt32LE(rate,24);data.writeUInt32LE(rate*2,28);data.writeUInt16LE(2,32);data.writeUInt16LE(16,34);data.write('data',36);data.writeUInt32LE(frames*2,40);
const melody=[261.63,329.63,392,523.25];for(let i=0;i<frames;i++){const t=i/rate,f=melody[Math.min(3,Math.floor(t))],phase=t%1,env=Math.min(1,phase*20)*Math.min(1,(1-phase)*8);const vocal=(Math.sin(2*Math.PI*f*t)+.28*Math.sin(4*Math.PI*f*t)+.12*Math.sin(6*Math.PI*f*t))*.32*env;data.writeInt16LE(Math.max(-32767,Math.min(32767,Math.round(vocal*32767))),44+i*2)}
await mkdir('test-data',{recursive:true});await writeFile('test-data/synthetic-vocal.wav',data);
