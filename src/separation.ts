/** Local, deterministic center-vocal extraction for conventional stereo mixes. */
export async function isolateCenterVocal(input: AudioBuffer, amount = .82): Promise<AudioBuffer> {
  if (input.numberOfChannels < 2 || amount <= 0) return input;
  const offline = new OfflineAudioContext(1, input.length, input.sampleRate);
  const mono = offline.createBuffer(1, input.length, input.sampleRate);
  const out = mono.getChannelData(0), left=input.getChannelData(0), right=input.getChannelData(1);
  for(let i=0;i<input.length;i++) {
    const center=(left[i]+right[i])*.5;
    const side=Math.abs(left[i]-right[i])*.5;
    const centerMask=Math.max(.12,1-side/(Math.abs(center)+side+.0001));
    out[i]=center*((1-amount)+amount*centerMask);
  }
  const source=offline.createBufferSource(); source.buffer=mono;
  const highpass=offline.createBiquadFilter(); highpass.type='highpass'; highpass.frequency.value=90; highpass.Q.value=.7;
  const lowpass=offline.createBiquadFilter(); lowpass.type='lowpass'; lowpass.frequency.value=9000; lowpass.Q.value=.7;
  const presence=offline.createBiquadFilter(); presence.type='peaking'; presence.frequency.value=2200; presence.Q.value=.8; presence.gain.value=3.5*amount;
  source.connect(highpass).connect(lowpass).connect(presence).connect(offline.destination); source.start();
  return offline.startRendering();
}

export async function resampleAudio(input:AudioBuffer,sampleRate=22050):Promise<AudioBuffer>{
  if(input.sampleRate===sampleRate)return input;
  const frames=Math.ceil(input.duration*sampleRate),offline=new OfflineAudioContext(input.numberOfChannels,frames,sampleRate);
  const source=offline.createBufferSource();source.buffer=input;source.connect(offline.destination);source.start();
  return offline.startRendering();
}
