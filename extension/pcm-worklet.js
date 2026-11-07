// AudioContext performs anti-aliased resampling to 16 kHz before this processor.
class PCMProcessor extends AudioWorkletProcessor {
  constructor(){super();this.packet=new Float32Array(1600);this.index=0;}
  process(inputs){
    const channels=inputs[0];
    if(!channels?.length) return true;
    for(let i=0;i<channels[0].length;i++){
      let sample=0; for(const channel of channels) sample+=channel[i];
      this.packet[this.index++]=Math.max(-1,Math.min(1,sample/channels.length));
      if(this.index===1600){this.port.postMessage(this.packet.buffer,[this.packet.buffer]);this.packet=new Float32Array(1600);this.index=0;}
    }
    return true;
  }
}
registerProcessor('pcm-capture',PCMProcessor);
