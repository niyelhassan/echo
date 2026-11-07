const DEFAULTS={size:28,theme:'dark',opacity:0.85,lines:3,position:'bottom',tone:true,toneLevel:'balanced',sounds:true,speakers:true,timing:false};
const THEMES={dark:['#ffffff','0,0,0','#9fe8d6','255,255,255'],yellow:['#ffe14d','0,0,0','#ffffff','255,225,77'],light:['#111111','255,255,255','#00594c','0,0,0']};
const $=s=>document.querySelector(s);
const toggle=$('#toggle'),status=$('#status'),token=$('#token');
const fields=['theme','opacity','lines','position','tone','toneLevel','sounds','speakers','timing'].map(id=>document.getElementById(id));
let settings={...DEFAULTS},tab,capturedTab=null;

function preview(){
  const [fg,bg,accent,chip]=THEMES[settings.theme]||THEMES.dark,p=$('#preview');
  // The popup preview is scaled down so every size still fits.
  for(const [k,v] of Object.entries({'--pfg':fg,'--pbg':bg,'--paccent':accent,'--pchip':chip,'--popacity':settings.opacity,'--psize':`${Math.round(settings.size*0.55)}px`})) p.style.setProperty(k,v);
  p.querySelector('.snd').hidden=!settings.sounds;
  p.querySelector('.tag').hidden=!settings.tone;
  p.querySelector('.who').hidden=!settings.speakers;
  document.querySelectorAll('.seg button').forEach(b=>b.setAttribute('aria-checked',String(Number(b.dataset.size)===settings.size)));
}
async function save(){await chrome.storage.sync.set({settings});preview();}

chrome.storage.sync.get('settings').then(s=>{
  settings={...DEFAULTS,...s.settings};
  for(const f of fields) f.type==='checkbox'?f.checked=settings[f.id]:f.value=String(settings[f.id]);
  preview();
});
for(const f of fields) f.onchange=()=>{settings[f.id]=f.type==='checkbox'?f.checked:(typeof DEFAULTS[f.id]==='number'?Number(f.value):f.value);save();};
document.querySelectorAll('.seg button').forEach(b=>{b.setAttribute('role','radio');b.onclick=()=>{settings.size=Number(b.dataset.size);save();};});

chrome.storage.local.get('token').then(s=>token.value=s.token||'');
token.onchange=()=>chrome.storage.local.set({token:token.value.trim()});

function show(session){
  capturedTab=session?.tabId??null;
  const here=capturedTab!==null&&capturedTab===tab?.id;
  toggle.textContent=here?'Stop captions':capturedTab!==null?'Caption this tab instead':'Start captions';
  toggle.classList.toggle('stop',here);
  $('#state').classList.toggle('on',capturedTab!==null);
  $('#state span').textContent=here?'Live':capturedTab!==null?'Live in another tab':'Off';
  const message=session?.status||'';
  status.textContent=/^(Stopped|Captioning this tab)$/.test(message)?'':message;
  status.classList.toggle('error',capturedTab===null&&!!message&&!/^(Stopped|Ready)$/.test(message)&&!/…$/.test(message));
}
async function refresh(){show(await chrome.storage.session.get(['tabId','status']));}
chrome.tabs.query({active:true,currentWindow:true}).then(([t])=>{tab=t;refresh();});
chrome.storage.onChanged.addListener((c,area)=>{if(area==='session')refresh();});

toggle.onclick=async()=>{
  toggle.disabled=true;
  try{
    if(capturedTab===tab.id) await chrome.runtime.sendMessage({target:'background',type:'stop'});
    else{
      if(token.value.trim()) await chrome.storage.local.set({token:token.value.trim()});
      const result=await chrome.runtime.sendMessage({target:'background',type:'start',tabId:tab.id});
      if(result?.error) throw Error(result.error);
    }
  }catch(e){status.textContent=e.message;status.classList.add('error');}
  finally{toggle.disabled=false;refresh();}
};
