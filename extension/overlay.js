(()=>{
  if(globalThis.__toneCaptionOverlay){globalThis.__toneCaptionOverlay.reset();return;}

  const DEFAULTS={size:28,theme:'dark',opacity:0.85,lines:3,position:'bottom',tone:true,toneLevel:'balanced',sounds:true,timing:false};
  // Minimum top score / margin over the runner-up before a tone label is shown (tuned on MELD, see VALIDATION.md).
  const TONE_LEVELS={strict:{score:0.9,margin:0.8},balanced:{score:0.75,margin:0.55},more:{score:0.6,margin:0.35}};
  const TONES={Angry:['😠','sounds angry'],Happy:['😊','sounds happy'],Sad:['😢','sounds sad'],Surprised:['😮','sounds surprised'],Fearful:['😨','sounds scared'],Disgusted:['😖','sounds disgusted']};
  const SOUND_TEXT={music:'♪ music ♪',singing:'♪ singing ♪'};
  const THEMES={dark:['#ffffff','0,0,0','#9fe8d6','255,255,255'],yellow:['#ffe14d','0,0,0','#ffffff','255,225,77'],light:['#111111','255,255,255','#00594c','0,0,0']};
  // Delivery cues change how the words look (as in SDH and Google's Expressive Captions) instead of adding a line.
  const LOUD=new Set(['shouting','screaming']),SOFT=new Set(['whispering']);
  const IDLE_MS=7000;

  const host=document.createElement('div');host.id='tone-caption-overlay';
  const root=host.attachShadow({mode:'open'});
  root.innerHTML=`<style>
  :host{all:initial!important;position:fixed!important;inset:0!important;z-index:2147483647!important;pointer-events:none!important;display:block!important}
  *{box-sizing:border-box}
  .caption{position:absolute;width:min(900px,90vw);left:50%;transform:translateX(-50%);bottom:8%;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--fg);pointer-events:none;display:flex;flex-direction:column;align-items:center}
  .caption.top{top:5%;bottom:auto}
  .caption.moved{transform:none}
  .box{position:relative;background:rgba(var(--bg),var(--opacity));border-radius:8px;padding:8px 16px 10px;pointer-events:auto;max-width:100%}
  .bar{position:absolute;top:-30px;right:0;display:flex;align-items:center;gap:6px;font-size:12px;color:#fff;opacity:0;transition:opacity .15s;cursor:grab;user-select:none;background:rgba(0,0,0,.7);border-radius:6px;padding:3px 6px}
  .box:hover .bar,.box:focus-within .bar{opacity:1}
  .bar .state{white-space:nowrap}
  .bar .timing{opacity:.7}
  button{font:inherit;font-size:12px;color:#fff;background:transparent;border:0;border-radius:4px;padding:2px 6px;cursor:pointer}
  button:hover,button:focus-visible{background:rgba(255,255,255,.15);outline:none}
  .lines{display:flex;flex-direction:column;justify-content:flex-end;overflow:hidden;max-height:calc(var(--size) * 1.36 * var(--lines));font-size:var(--size);line-height:1.36;font-weight:550;text-align:center}
  .lines p{margin:0}
  .tag{display:inline-block;vertical-align:.12em;font-size:.6em;font-weight:600;letter-spacing:.2px;color:var(--fg);background:rgba(var(--chip),.16);border:1px solid rgba(var(--chip),.35);border-radius:999px;padding:.05em .6em .1em;margin-right:.45em;white-space:nowrap}
  .lines p:not(:last-child){opacity:.62}
  .lines p.loud{font-weight:800;text-transform:uppercase;letter-spacing:.3px}
  .lines p.soft{font-style:italic;font-weight:400;opacity:.85}
  .sound{font-style:italic;font-weight:450;color:var(--accent)}
  .pill{display:none;font-size:12px;font-weight:600;letter-spacing:.5px;color:#fff;background:rgba(0,0,0,.6);border-radius:999px;padding:3px 10px;align-items:center;gap:6px}
  .pill .dot{width:7px;height:7px;border-radius:50%;background:#e5484d}
  .caption.idle .box{display:none}
  .caption.idle .pill{display:inline-flex}
  .panel{position:absolute;top:16px;right:16px;bottom:16px;width:min(420px,90vw);background:#0d1418;color:#f2f5f6;border:1px solid #3b4d55;border-radius:10px;display:flex;flex-direction:column;pointer-events:auto;font:15px/1.45 system-ui,-apple-system,sans-serif;box-shadow:0 8px 40px rgba(0,0,0,.5)}
  .panel[hidden]{display:none}
  .panel header{display:flex;gap:6px;align-items:center;padding:10px 12px;border-bottom:1px solid #2a3940}
  .panel header strong{flex:1}
  .panel button{color:#f2f5f6}
  .panel input{margin:8px 12px 0;padding:6px 8px;border-radius:6px;border:1px solid #3b4d55;background:#162228;color:inherit;font:inherit}
  .panel ol{list-style:none;margin:0;padding:8px 12px 16px;overflow:auto;flex:1}
  .panel li{padding:4px 0;border-bottom:1px solid #1c2a30}
  .panel time{color:#8fa3ab;font-size:12px;margin-right:6px;font-variant-numeric:tabular-nums}
  .panel .tag,.panel .sound{color:#9fe8d6}
  .sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
  </style>
  <div class="caption idle" part="caption"><span class="pill" aria-hidden="true"><span class="dot"></span><span class="pilltext">CC</span></span><div class="box">
    <div class="bar" title="Drag to move · double-click to reset"><span class="state"><span class="now">Starting</span><span class="extra"></span></span><span class="timing"></span>
      <button class="open" aria-label="Show transcript (Alt+Shift+T)">Transcript</button><button class="close" aria-label="Stop captions">✕</button></div>
    <div class="lines"></div>
  </div></div>
  <aside class="panel" hidden aria-label="Caption transcript"><header><strong>Echo transcript</strong><button class="copy">Copy</button><button class="save">Save</button><button class="hide" aria-label="Hide transcript">✕</button></header>
    <input type="search" placeholder="Search transcript" aria-label="Search transcript"><ol></ol></aside>
  <div class="sr" role="log" aria-live="polite"></div>`;

  const $=s=>root.querySelector(s);
  const caption=$('.caption'),lines=$('.lines'),panel=$('.panel'),list=$('.panel ol'),live=$('.sr');
  let settings={...DEFAULTS},rows=new Map(),active=true,idleTimer,started=Date.now(),soundCount=0,activeSounds=[],transcript=[];

  function applySettings(){
    const [fg,bg,accent,chip]=THEMES[settings.theme]||THEMES.dark;
    for(const [k,v] of Object.entries({'--fg':fg,'--bg':bg,'--accent':accent,'--chip':chip,'--opacity':settings.opacity,'--size':`${settings.size}px`,'--lines':settings.lines}))caption.style.setProperty(k,v);
    caption.classList.toggle('top',settings.position==='top');
    $('.timing').hidden=!settings.timing;
    render();
  }
  chrome.storage.sync.get('settings').then(s=>{settings={...DEFAULTS,...s.settings};applySettings();});
  chrome.storage.onChanged.addListener((c,area)=>{if(area==='sync'&&c.settings){settings={...DEFAULTS,...c.settings.newValue};applySettings();}});

  const clock=ms=>{const s=Math.max(0,Math.round(ms/1000));return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;};
  const soundText=c=>`[${SOUND_TEXT[c]||c}]`;
  function toneTag(tone){
    if(!settings.tone||!tone?.scores) return null;
    const ranked=Object.entries(tone.scores).sort((a,b)=>b[1]-a[1]);
    if(!ranked.length) return null;
    const [[best,score],[,second=0]=[]]=ranked;
    const level=TONE_LEVELS[settings.toneLevel]||TONE_LEVELS.balanced;
    if(!TONES[best]||score<level.score||score-second<level.margin) return null;
    return TONES[best];
  }
  function setState(text){$('.now').textContent=text;$('.pilltext').textContent=text==='Live'||text==='Listening'?'CC':text;}

  function render(){
    const visible=[...rows.values()].filter(r=>r.kind==='sound'?settings.sounds:r.text).sort((a,b)=>a.at-b.at).slice(-6);
    lines.replaceChildren(...visible.map(r=>{
      const p=document.createElement('p');
      if(r.kind==='sound'){p.className='sound';p.textContent=soundText(r.cue);return p;}
      const tag=toneTag(r.tone);
      if(settings.sounds&&r.delivery) p.className=r.delivery;
      if(tag){const t=document.createElement('span');t.className='tag';t.textContent=`${tag[0]} ${tag[1]}`;p.append(t);}
      p.append(r.text);return p;
    }));
    const idle=!visible.length;
    caption.classList.toggle('idle',idle);
    const sounds=settings.sounds&&activeSounds.length?` · ${activeSounds.map(soundText).join(' ')}`:'';
    $('.extra').textContent=sounds;
  }
  function touch(){
    clearTimeout(idleTimer);
    idleTimer=setTimeout(()=>{rows.clear();render();},IDLE_MS);
  }

  function renderTranscript(){
    const query=$('.panel input').value.trim().toLowerCase();
    list.replaceChildren(...transcript.filter(e=>!query||e.plain().toLowerCase().includes(query)).map(e=>{
      const li=document.createElement('li'),time=document.createElement('time');time.textContent=e.time;li.append(time);
      if(e.cue){const s=document.createElement('span');s.className='sound';s.textContent=soundText(e.cue);li.append(s);}
      else{const tag=toneTag(e.row.tone);const label=[e.row.delivery==='loud'?'shouting':e.row.delivery==='soft'?'whispering':null,tag?.[1]].filter(Boolean).join(', ');if(label){const t=document.createElement('span');t.className='tag';t.textContent=`[${label}]`;li.append(t);}li.append(e.row.text);}
      return li;
    }));
    list.scrollTop=list.scrollHeight;
  }
  function plainLine(e){
    if(e.cue) return `${e.time}  ${soundText(e.cue)}`;
    const tag=toneTag(e.row.tone);
    const label=[e.row.delivery==='loud'?'shouting':e.row.delivery==='soft'?'whispering':null,tag?.[1]].filter(Boolean).join(', ');
    return `${e.time}  ${label?`[${label}] `:''}${e.row.text}`;
  }
  function addTranscript(entry){
    entry.plain=()=>plainLine(entry);
    transcript.push(entry);
    if(!panel.hidden) renderTranscript();
  }
  function announce(text){live.textContent=text;}

  function onCaption(e){
    const key=`seg-${e.segment}`;
    const row=rows.get(key)||{kind:'speech',segment:e.segment,at:e.start};
    if(e.text||!row.text) row.text=e.text||'';
    row.final=e.final;row.end=e.end;rows.set(key,row);
    if(e.final&&row.text&&!row.logged){
      row.logged=true;
      addTranscript({time:clock(e.start*1000),row});
      announce(row.text);
    }
    if(settings.timing) $('.timing').textContent=`${e.queue_and_processing_ms} ms`;
    setState('Live');render();touch();
  }
  function onTone(e){
    const key=`seg-${e.segment}`;
    const row=rows.get(key)||transcript.find(t=>t.row?.segment===e.segment)?.row;
    if(!row) return;
    if(e.final||!row.tone?.final) row.tone={...e.tone,final:e.final};
    render();if(!panel.hidden) renderTranscript();
  }
  function onSound(e){
    activeSounds=e.active||[];
    const speech=[...rows.values()].filter(r=>r.kind==='speech'&&r.text).at(-1);
    for(const cue of e.started||[]){
      const delivery=LOUD.has(cue)?'loud':SOFT.has(cue)?'soft':null;
      // Attach delivery to the line being spoken; only standalone shouting gets its own [shouting] line.
      if(delivery&&speech&&speech.end>=e.start){speech.delivery=delivery;if(!panel.hidden)renderTranscript();continue;}
      rows.set(`snd-${soundCount++}`,{kind:'sound',cue,at:Math.max(e.start,e.end-1.5)});
      addTranscript({time:clock((e.end-1.5)*1000),cue});
      if(settings.sounds) announce(soundText(cue));
    }
    render();if(e.started?.length) touch();
  }

  const attach=()=>{
    if(!active) return;
    const full=document.fullscreenElement;
    // A bare <video> in fullscreen cannot contain other elements; fall back to the document.
    (full && full.tagName!=='VIDEO' ? full : document.documentElement).appendChild(host);
  };
  function reset(){
    active=true;rows.clear();activeSounds=[];started=Date.now();clearTimeout(idleTimer);
    setState('Starting');render();attach();
  }
  globalThis.__toneCaptionOverlay={reset};
  document.addEventListener('fullscreenchange',attach);

  // Dragging: remember the position as viewport fractions.
  const bar=$('.box');let drag=null;
  bar.addEventListener('pointerdown',e=>{
    if(e.target.closest('button')||e.button!==0) return;
    const r=caption.getBoundingClientRect();drag={dx:e.clientX-r.left,dy:e.clientY-r.top};bar.setPointerCapture(e.pointerId);
  });
  bar.addEventListener('pointermove',e=>{
    if(!drag) return;
    const x=Math.min(Math.max(0,e.clientX-drag.dx),innerWidth-caption.offsetWidth),y=Math.min(Math.max(0,e.clientY-drag.dy),innerHeight-40);
    Object.assign(caption.style,{left:`${x}px`,top:`${y}px`,bottom:'auto'});caption.classList.add('moved');
  });
  bar.addEventListener('pointerup',()=>{
    if(!drag) return;drag=null;
    chrome.storage.local.set({overlayPosition:{x:parseFloat(caption.style.left)/innerWidth,y:parseFloat(caption.style.top)/innerHeight}});
  });
  bar.addEventListener('dblclick',()=>{
    Object.assign(caption.style,{left:'',top:'',bottom:''});caption.classList.remove('moved');chrome.storage.local.remove('overlayPosition');
  });
  chrome.storage.local.get('overlayPosition').then(({overlayPosition:p})=>{
    if(p) {Object.assign(caption.style,{left:`${p.x*innerWidth}px`,top:`${p.y*innerHeight}px`,bottom:'auto'});caption.classList.add('moved');}
  });

  const toggleTranscript=()=>{panel.hidden=!panel.hidden;if(!panel.hidden){renderTranscript();$('.panel input').focus();}};
  $('.open').onclick=toggleTranscript;
  $('.hide').onclick=toggleTranscript;
  $('.panel input').oninput=renderTranscript;
  $('.close').onclick=()=>chrome.runtime.sendMessage({target:'background',type:'stop'});
  const text=()=>transcript.map(e=>e.plain()).join('\n');
  $('.copy').onclick=async()=>{await navigator.clipboard.writeText(text());$('.copy').textContent='Copied';setTimeout(()=>$('.copy').textContent='Copy',1500);};
  $('.save').onclick=()=>{
    const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([`${document.title}\n${location.href}\n\n${text()}\n`],{type:'text/plain'}));
    a.download=`echo-transcript-${new Date().toISOString().slice(0,16).replace(/[:T]/g,'-')}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
  };

  chrome.runtime.onMessage.addListener((e,sender,respond)=>{
    if(e.type==='ping'){respond({alive:active});return;}
    if(e.type==='stopped'){active=false;clearTimeout(idleTimer);host.remove();return;}
    if(e.type==='toggle-transcript'){toggleTranscript();return;}
    if(e.type==='status'){setState(e.message);return;}
    if(e.type==='error'){rows.clear();rows.set('error',{kind:'speech',at:0,text:e.message});setState('Disconnected');render();return;}
    if(e.type==='listening'){reset();setState('Listening');return;}
    if(!active) return;
    if(e.type==='caption') onCaption(e);
    else if(e.type==='tone') onTone(e);
    else if(e.type==='sound') onSound(e);
  });
  reset();
})();
