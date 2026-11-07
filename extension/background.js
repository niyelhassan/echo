const HOST='com.tonecaption.service';
let starting=false;

async function offscreen() {
  if (!(await chrome.runtime.getContexts({contextTypes:['OFFSCREEN_DOCUMENT']})).length) {
    await chrome.offscreen.createDocument({url:'offscreen.html',reasons:['USER_MEDIA','AUDIO_PLAYBACK'],justification:'Capture selected tab audio for local captions and preserve audible playback.'});
  }
}

async function status(text,extra={}) {
  await chrome.storage.session.set({status:text,...extra});
}

// Prefer the native launcher (starts the service and pairs automatically); fall back to a pasted token.
async function pairingToken() {
  try {
    await status('Starting the local caption service…');
    const reply=await chrome.runtime.sendNativeMessage(HOST,{type:'ensure'});
    if(reply?.ok && reply.token) {
      await chrome.storage.local.set({token:reply.token});
      return reply.token;
    }
    if(reply?.error) throw Error(reply.error);
  } catch(e) {
    if(!/native messaging host not found|Specified native messaging host/i.test(e.message)) throw e;
  }
  const {token}=await chrome.storage.local.get('token');
  if(!token) throw Error('Local service not installed. Run install.py, or start the service and paste its token below.');
  return token;
}

async function stop() {
  const {tabId}=await chrome.storage.session.get('tabId');
  const contexts=await chrome.runtime.getContexts({contextTypes:['OFFSCREEN_DOCUMENT']});
  if(contexts.length) await chrome.runtime.sendMessage({target:'offscreen',type:'stop'});
  if(tabId) await chrome.tabs.sendMessage(tabId,{type:'stopped'}).catch(()=>{});
  await status('Stopped',{tabId:null});
  await chrome.action.setBadgeText({text:''});
}

async function start(tabId) {
  if(starting) throw Error('Already starting.');
  starting=true;
  try {
    await stop();
    await chrome.scripting.executeScript({target:{tabId},files:['overlay.js']});
    await chrome.storage.session.set({tabId});
    await chrome.tabs.sendMessage(tabId,{type:'status',message:'Starting local captions…'}).catch(()=>{});
    const token=await pairingToken();
    // Stream IDs expire within seconds, so request one only after the (possibly slow) service start.
    const streamId=await chrome.tabCapture.getMediaStreamId({targetTabId:tabId});
    await offscreen();
    await status('Connecting…');
    const result=await chrome.runtime.sendMessage({target:'offscreen',type:'start',streamId,token});
    if(result?.error) throw Error(result.error);
    await status('Captioning this tab',{tabId});
    await chrome.action.setBadgeText({text:'CC'});
    await chrome.action.setBadgeBackgroundColor({color:'#1b6f5f'});
  } catch(e) {
    await stop();
    await status(e.message);
    throw e;
  } finally {starting=false;}
}

chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message.target!=='background') return;
  (async()=>{
    if(message.type==='status') return chrome.storage.session.get(['tabId','status']);
    if(message.type==='start') await start(message.tabId);
    else if(message.type==='stop') await stop();
    else if(message.type==='event') {
      const {tabId}=await chrome.storage.session.get('tabId');
      if(tabId) await chrome.tabs.sendMessage(tabId,message.event).catch(()=>{});
      if(message.event.type==='error') {
        await status(message.event.message,{tabId:null});
        await chrome.action.setBadgeText({text:'!'});
      }
    }
    return {ok:true};
  })().then(respond,e=>respond({error:e.message}));
  return true;
});

chrome.commands.onCommand.addListener(async(command,tab)=>{
  if(!tab?.id) return;
  const {tabId}=await chrome.storage.session.get('tabId');
  if(command==='toggle-captions') {
    if(tabId===tab.id) await stop();
    else await start(tab.id).catch(()=>{});
  } else if(command==='toggle-transcript' && tabId===tab.id) {
    await chrome.tabs.sendMessage(tab.id,{type:'toggle-transcript'}).catch(()=>{});
  }
});

chrome.tabs.onRemoved.addListener(async id=>{
  if((await chrome.storage.session.get('tabId')).tabId===id) await stop();
});
// In-page navigation (e.g. YouTube's next video) keeps the overlay alive; a real page load destroys it,
// and Chrome revokes our tab access, so capture stops rather than continuing invisibly.
chrome.tabs.onUpdated.addListener(async(id,change)=>{
  if(change.status!=='complete' || (await chrome.storage.session.get('tabId')).tabId!==id) return;
  const alive=await chrome.tabs.sendMessage(id,{type:'ping'}).catch(()=>null);
  if(!alive?.alive) await stop();
});
