let stream,context,processor,socket,source,playback,playbackSource,stopping=false;
const event=e=>chrome.runtime.sendMessage({target:'background',type:'event',event:e}).catch(()=>{});
async function stop(){
  stopping=true;
  if(processor){processor.port.onmessage=null;processor.disconnect();processor=null;}
  if(source){source.disconnect();source=null;}
  if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}
  if(context){await context.close();context=null;}
  if(playbackSource){playbackSource.disconnect();playbackSource=null;}
  if(playback){await playback.close();playback=null;}
  if(socket){socket.onclose=null;socket.onerror=null;socket.close();socket=null;}
}
async function start(message){
  await stop(); stopping=false;
  socket=new WebSocket('ws://127.0.0.1:8765');
  await new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(Error('Local service did not respond. Start the service and retry.')),8000);
    socket.onopen=()=>socket.send(JSON.stringify({token:message.token}));
    socket.onerror=()=>{clearTimeout(timeout);reject(Error('Cannot reach local service at 127.0.0.1:8765.'));};
    socket.onclose=e=>{clearTimeout(timeout);reject(Error(e.reason || 'Pairing failed. Check your token.'));};
    socket.onmessage=e=>{
      const data=JSON.parse(e.data);
      if(data.type==='ready'){clearTimeout(timeout);resolve();}
      if(data.type==='error'){clearTimeout(timeout);reject(Error(data.message));}
    };
  });
  socket.onmessage=e=>{
    const data=JSON.parse(e.data);event(data);
    if(data.type==='error') stop();
  };
  socket.onclose=()=>{if(!stopping){event({type:'error',message:'Local service disconnected. Start it, then reconnect.'});stop();}};
  socket.onerror=()=>{};
  stream=await navigator.mediaDevices.getUserMedia({audio:{mandatory:{chromeMediaSource:'tab',chromeMediaSourceId:message.streamId}},video:false});
  stream.getAudioTracks()[0].onended=()=>{if(!stopping){event({type:'error',message:'Tab audio capture ended.'});stop();}};
  context=new AudioContext({sampleRate:16000});
  if(context.sampleRate!==16000) throw Error('This browser did not provide 16 kHz audio.');
  await context.audioWorklet.addModule('pcm-worklet.js');
  source=context.createMediaStreamSource(stream);
  // Preserve original playback bandwidth; only the analysis context runs at 16 kHz.
  playback=new AudioContext();
  playbackSource=playback.createMediaStreamSource(stream);
  playbackSource.connect(playback.destination);
  await playback.resume();
  processor=new AudioWorkletNode(context,'pcm-capture');
  const mute=context.createGain();mute.gain.value=0;
  source.connect(processor);processor.connect(mute);mute.connect(context.destination);
  processor.port.onmessage=e=>{
    if(socket?.readyState!==WebSocket.OPEN) return;
    if(socket.bufferedAmount>64000){event({type:'error',message:'Audio processing fell behind. Stop and reconnect.'});stop();return;}
    socket.send(e.data);
  };
  await context.resume();
  event({type:'listening'});
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message.target!=='offscreen') return;
  (message.type==='start'?start(message):stop()).then(()=>respond({ok:true}),async e=>{await stop();respond({error:e.message});});
  return true;
});
