import { describe, expect, it } from 'vitest';
import { detectKey, detectMeter } from './analysis';
import type { RawNote } from './types';

const note=(pitchMidi:number,startTimeSeconds:number,durationSeconds=.45):RawNote=>({pitchMidi,startTimeSeconds,durationSeconds,amplitude:.9});
describe('automatic musical analysis',()=>{
  it('detects C major from a weighted C-major melody',()=>{
    const notes=[note(60,0,1),note(64,1),note(67,2,1),note(72,3,1),note(65,4),note(67,5),note(60,6,2)];
    const result=detectKey(notes);
    expect(result.keyPitchClass).toBe(0);
    expect(result.mode).toBe('major');
  });
  it('detects three-beat accent grouping',()=>{
    const notes:RawNote[]=[];
    for(let bar=0;bar<8;bar++) for(let beat=0;beat<3;beat++) notes.push({...note(60+beat,bar*1.5+beat*.5),amplitude:beat===0?1:.3});
    expect(detectMeter(notes,120).meter).toBe(3);
  });
});
