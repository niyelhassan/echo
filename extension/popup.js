const DEFAULTS={size:28,theme:'dark',opacity:0.85,lines:3,position:'bottom',tone:true,toneLevel:'balanced',sounds:true,timing:false};
const status=document.querySelector('#status');
const token=document.querySelector('#token');
const fields=Object.keys(DEFAULTS).map(id=>document.getElementById(id));

chrome.storage.local.get('token').then(s=>token.value=s.token||'');
token.onchange=()=>chrome.storage.local.set({token:token.value.trim()});

chrome.storage.sync.get('settings').then(({settings})=>{
  const values={...DEFAULTS,...settings};
  for(const field of fields) field.type==='checkbox'?field.checked=values[field.id]:field.value=String(values[field.id]);
});
for(const field of fields) field.onchange=async()=>{
  const settings={};
  for(const f of fields) settings[f.id]=f.type==='checkbox'?f.checked:(typeof DEFAULTS[f.id]==='number'?Number(f.value):f.value);
  await chrome.storage.sync.set({settings});
};

const refresh=()=>chrome.runtime.sendMessage({target:'background',type:'status'}).then(s=>{if(s?.status) status.textContent=s.status;});
refresh();
chrome.storage.onChanged.addListener((c,area)=>{if(area==='session'&&c.status) status.textContent=c.status.newValue;});

document.querySelector('#start').onclick=async()=>{
  const button=document.querySelector('#start');button.disabled=true;
  try{
    if(token.value.trim()) await chrome.storage.local.set({token:token.value.trim()});
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    const result=await chrome.runtime.sendMessage({target:'background',type:'start',tabId:tab.id});
    if(result?.error) throw Error(result.error);
    status.textContent='Captioning this tab';
  }catch(e){status.textContent=e.message;}
  finally{button.disabled=false;}
};
document.querySelector('#stop').onclick=async()=>{
  await chrome.runtime.sendMessage({target:'background',type:'stop'});
  status.textContent='Stopped';
};
