"""Real tabCapture -> offscreen AudioWorklet -> local models -> overlay, isolated profile."""
import asyncio, functools, http.server, json, threading, time, sys
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]

async def main():
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    port=server.server_port
    case='heldout' if '--heldout' in sys.argv else 'expressive'
    results={'case':case,'events':[],'errors':[]}
    async with async_playwright() as p:
        ctx=await p.chromium.launch_persistent_context(str(ROOT/'.build/browser-test-profile'),channel='chromium',headless=False,
            args=['--enable-unsafe-extension-debugging','--autoplay-policy=no-user-gesture-required',f'--disable-extensions-except={ROOT / "extension"}',f'--load-extension={ROOT / "extension"}'],
            viewport={'width':1200,'height':850})
        try:
            sw=ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event('serviceworker')
            extension_id=sw.url.split('/')[2]
            cdp=await ctx.browser.new_browser_cdp_session()
            await sw.evaluate('(token)=>chrome.storage.local.set({token})',(ROOT/'.build/local-token').read_text().strip())
            control=await ctx.new_page();await control.goto(f'chrome-extension://{extension_id}/popup.html')
            page=await ctx.new_page()
            page.on('pageerror',lambda e:results['errors'].append(str(e)))
            await page.goto(f'http://127.0.0.1:{port}/tests/video.html')
            if case=='heldout': await page.locator('video').evaluate("v=>v.src='../.build/browser-cases/heldout.mp4'")
            session=await ctx.new_cdp_session(page)
            targets=(await cdp.send('Target.getTargets',{'filter':[{}]}))['targetInfos']
            target=next(t['targetId'] for t in targets if t['type']=='tab' and 'video.html' in t['url'])
            await cdp.send('Extensions.triggerAction',{'id':extension_id,'targetId':target})
            tab_id=await sw.evaluate('async()=> (await chrome.tabs.query({url:"http://127.0.0.1:*/*"})).find(t=>t.url.includes("video.html")).id')
            await control.evaluate('''()=>{window.events=[];chrome.runtime.onMessage.addListener(m=>{if(m.type==='event')window.events.push({...m.event,received_ms:Date.now()});});}''')
            result=await control.evaluate('(id)=>chrome.runtime.sendMessage({target:"background",type:"start",tabId:id})',tab_id)
            assert not result.get('error'),result
            await page.bring_to_front()
            results['play_started_ms']=await page.evaluate('Date.now()')
            await page.locator('video').evaluate('(v)=>v.play()')
            expected='wonder' if case=='heldout' else 'jacket'
            await page.wait_for_function("word=>document.querySelector('#tone-caption-overlay')?.shadowRoot.querySelector('#text').textContent.toLowerCase().includes(word)",arg=expected,timeout=20000)
            await page.screenshot(path=str(ROOT/f'.build/extension-{case}.png'))
            await page.wait_for_function('document.querySelector("video").ended',timeout=30000)
            await asyncio.sleep(1)
            results['events']=await control.evaluate('window.events')
            results['overlay']=await page.locator('#tone-caption-overlay').evaluate('(e)=>e.shadowRoot.textContent')
            assert any(e.get('tone',{}).get('leading') for e in results['events'])
            # Fullscreen moves the real overlay into the fullscreen container.
            await page.locator('#fullscreen').click()
            await page.wait_for_function('document.fullscreenElement?.contains(document.querySelector("#tone-caption-overlay"))')
            results['fullscreen']=True
            await page.evaluate('document.exitFullscreen()')
            await control.evaluate('()=>chrome.runtime.sendMessage({target:"background",type:"stop"})')
            assert await page.locator('#tone-caption-overlay').count()==0
            results['stopped']=True
            # Restart, then navigate: capture must end instead of continuing invisibly.
            await cdp.send('Extensions.triggerAction',{'id':extension_id,'targetId':target})
            r=await control.evaluate('(id)=>chrome.runtime.sendMessage({target:"background",type:"start",tabId:id})',tab_id)
            assert not r.get('error'),r
            await page.reload();await asyncio.sleep(.5)
            state=await sw.evaluate('()=>chrome.storage.session.get(["tabId","status"])')
            assert state['tabId'] is None,state
            results['restart_and_navigation']=True
        finally:
            (ROOT/f'.build/evaluation/browser-{case}.json').write_text(json.dumps(results,indent=2))
            await ctx.close();server.shutdown()
    print(json.dumps({k:v for k,v in results.items() if k not in ('events','overlay')}))
    print('caption events',len(results['events']))

asyncio.run(main())
