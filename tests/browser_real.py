"""End-to-end in Chromium: native auto-start, real tabCapture of real videos, rendered overlay and transcript.

Run after `uv run python install.py --skip-models --profile .build/browser-test-profile`.
--cold stops any running service first so the native host must launch it.
"""
import asyncio, functools, http.server, json, os, signal, socket, subprocess, sys, threading, time
from pathlib import Path
import jiwer
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from real_eval import normalize, reference

EXTENSION_ID = 'pnangodkiechjldahinmjhkmkoaideib'
# (video, start s, seconds played, description)
VIDEOS = [('arj7oStGLkU', 212, 75, 'TED talk with audience laughter'),
          ('nsEq3XDq9gQ', 0, 72, 'Film scene: heated, tearful argument'),
          ('Yvrf-CeBkm4', 0, 80, 'Comedy sketch with laugh track and cheering')]
OVERLAY = "document.querySelector('#tone-caption-overlay')?.shadowRoot"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def handle(self):
        try: super().handle()
        except (BrokenPipeError, ConnectionResetError): pass


def stop_service():
    out = subprocess.run(['lsof', '-t', '-nP', '-iTCP:8765', '-sTCP:LISTEN'], capture_output=True, text=True).stdout.split()
    for pid in out: os.kill(int(pid), signal.SIGINT)
    for _ in range(50):
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1', 8765)): return
        time.sleep(.2)


async def start(sw, control, cdp, target, tab_id):
    await cdp.send('Extensions.triggerAction', {'id': EXTENSION_ID, 'targetId': target})
    began = time.time()
    result = await control.evaluate('(id)=>chrome.runtime.sendMessage({target:"background",type:"start",tabId:id})', tab_id)
    assert not result.get('error'), result
    return time.time() - began


async def main():
    if '--only' in sys.argv:
        vid, t0, secs = sys.argv[sys.argv.index('--only')+1].split(':')
        VIDEOS[:] = [(vid, float(t0), float(secs), 'Requested video')]
    if '--cold' in sys.argv: stop_service()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(
        Quiet, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    results = {'errors': [], 'videos': {}}
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(ROOT/'.build/browser-test-profile'), channel='chromium', headless=False,
            args=['--enable-unsafe-extension-debugging', '--autoplay-policy=no-user-gesture-required',
                  f'--disable-extensions-except={ROOT/"extension"}', f'--load-extension={ROOT/"extension"}'],
            viewport={'width': 1280, 'height': 860})
        try:
            sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event('serviceworker')
            assert sw.url.split('/')[2] == EXTENSION_ID, sw.url
            await sw.evaluate('()=>Promise.all([chrome.storage.local.clear(),chrome.storage.sync.clear()])')
            cdp = await ctx.browser.new_browser_cdp_session()
            control = await ctx.new_page(); await control.goto(f'chrome-extension://{EXTENSION_ID}/popup.html')
            await control.set_viewport_size({'width': 320, 'height': 600})
            await control.screenshot(path=str(ROOT/'.build/screens/popup.png'), full_page=True)
            await control.evaluate('''()=>{window.events=[];chrome.runtime.onMessage.addListener(m=>{if(m.type==='event')window.events.push({...m.event,received_ms:Date.now()});});}''')
            page = await ctx.new_page()
            page.on('pageerror', lambda e: results['errors'].append(str(e)))
            for index, (video, t0, seconds, description) in enumerate(VIDEOS):
                await page.goto(f'http://127.0.0.1:{port}/tests/player.html?id={video}&t={t0}&title={description}')
                await page.wait_for_function(f'(()=>{{const v=document.querySelector("video");return v.readyState>=2&&Math.abs(v.currentTime-{t0})<1}})()')
                targets = (await cdp.send('Target.getTargets', {'filter': [{}]}))['targetInfos']
                target = next(t['targetId'] for t in targets if t['type'] == 'tab' and 'player.html' in t['url'])
                tab_id = await sw.evaluate('async()=> (await chrome.tabs.query({url:"http://127.0.0.1:*/*"})).find(t=>t.url.includes("player.html")).id')
                await control.evaluate('()=>window.events=[]')
                startup = await start(sw, control, cdp, target, tab_id)
                await page.bring_to_front()
                played = await page.evaluate('Date.now()')
                await page.locator('video').evaluate('v=>v.play()')
                shots, first_text = {}, None
                deadline = time.time() + seconds
                while time.time() < deadline:
                    state = await page.evaluate(f'''()=>{{const r={OVERLAY};if(!r)return null;
                        return {{text:r.querySelector('.lines').innerText,sound:!!r.querySelector('.lines .sound'),tag:!!r.querySelector('.lines .tag')}}}}''')
                    if state and state['text'].strip() and first_text is None:
                        first_text = await page.evaluate('Date.now()') - played
                    for kind in ('sound', 'tag'):
                        if state and state[kind] and kind not in shots:
                            shots[kind] = str(ROOT/f'.build/screens/{video}-{kind}.png')
                            await page.screenshot(path=shots[kind])
                    if index == 0 and 'caption' not in shots and time.time() > deadline - seconds/2 and state and state['text'].strip():
                        shots['caption'] = str(ROOT/f'.build/screens/{video}-caption.png'); await page.screenshot(path=shots['caption'])
                    await asyncio.sleep(.25)
                await page.locator('video').evaluate('v=>v.pause()')
                await asyncio.sleep(2)
                # The rendered transcript is what a user can read back; score it against human captions.
                await page.evaluate(f"()=>{OVERLAY}.querySelector('.open').click()")
                await asyncio.sleep(.3)
                shots['transcript'] = str(ROOT/f'.build/screens/{video}-transcript.png'); await page.screenshot(path=shots['transcript'])
                entries = await page.evaluate(f'''()=>[...{OVERLAY}.querySelectorAll('.panel li')].map(li=>({{
                    sound:li.querySelector('.sound')?.textContent||null,tag:li.querySelector('.tag')?.textContent||null,
                    text:[...li.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ')}}))''')
                await page.evaluate(f"()=>{OVERLAY}.querySelector('.hide').click()")
                position = await page.locator('video').evaluate('v=>v.currentTime')
                ref = reference(video, t0 + 1.5, position - 1.5)[0]
                hyp = normalize(' '.join(e['text'] for e in entries))
                # Reference covers only cues fully inside the played span; trim hypothesis edges by alignment.
                out = jiwer.process_words(ref, hyp)
                events = await control.evaluate('window.events')
                results['videos'][video] = {
                    'description': description, 'service_start_s': round(startup, 1), 'first_text_ms': first_text,
                    'played_s': round(position - t0, 1), 'wer_vs_human_captions': round(out.wer, 4),
                    'reference_words': len(ref.split()), 'insertions': out.insertions,
                    'sound_cues_rendered': [e['sound'] for e in entries if e['sound']],
                    'tone_tags_rendered': [e['tag'] for e in entries if e['tag']],
                    'caption_events': sum(e['type'] == 'caption' for e in events), 'screens': shots,
                    'transcript': [e['sound'] or f"{e['tag'] or ''} {e['text']}".strip() for e in entries]}
                print(video, {k: v for k, v in results['videos'][video].items() if k not in ('transcript', 'screens')}, flush=True)

            # Settings apply live to an open overlay.
            await sw.evaluate("()=>chrome.storage.sync.set({settings:{size:46,theme:'yellow',opacity:1,lines:2,position:'top',tone:true,toneLevel:'balanced',sounds:true,timing:false}})")
            await asyncio.sleep(.4)
            style = await page.evaluate(f"()=>{{const c={OVERLAY}.querySelector('.caption');const s=getComputedStyle({OVERLAY}.querySelector('.lines'));return {{size:s.fontSize,color:s.color,top:c.classList.contains('top')}}}}")
            assert style == {'size': '46px', 'color': 'rgb(255, 225, 77)', 'top': True}, style
            results['settings_live'] = style
            await sw.evaluate('()=>chrome.storage.sync.clear()')
            # Fullscreen keeps the overlay visible inside the fullscreen element.
            await page.locator('#fullscreen').click()
            await page.wait_for_function('document.fullscreenElement?.contains(document.querySelector("#tone-caption-overlay"))')
            await page.evaluate('document.exitFullscreen()')
            results['fullscreen'] = True
            await control.evaluate('()=>chrome.runtime.sendMessage({target:"background",type:"stop"})')
            assert await page.locator('#tone-caption-overlay').count() == 0
            results['stop_removes_overlay'] = True
            # A real page load ends capture instead of continuing invisibly.
            await start(sw, control, cdp, target, tab_id)
            await page.reload(); await asyncio.sleep(1.5)
            state = await sw.evaluate('()=>chrome.storage.session.get(["tabId","status"])')
            assert state['tabId'] is None, state
            results['reload_stops_capture'] = True
        finally:
            (ROOT/'.build/evaluation/browser-real.json').write_text(json.dumps(results, indent=2))
            await ctx.close(); server.shutdown()
    print(json.dumps({k: v for k, v in results.items() if k != 'videos'}))


if __name__ == '__main__':
    (ROOT/'.build/screens').mkdir(exist_ok=True)
    asyncio.run(main())
