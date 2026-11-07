"""Caption a live youtube.com watch page with the real extension (tabCapture of the YouTube tab).

Usage: uv run python tests/browser_youtube.py VIDEO_ID [seconds]
"""
import asyncio, json, sys, time
from pathlib import Path
import jiwer
from playwright.async_api import async_playwright
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from real_eval import normalize, reference

EXTENSION_ID = 'pnangodkiechjldahinmjhkmkoaideib'
OVERLAY = "document.querySelector('#tone-caption-overlay')?.shadowRoot"


async def main(video, seconds):
    out = {'video': video, 'errors': []}
    shots = ROOT/'.build/screens'
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(ROOT/'.build/browser-test-profile'), channel='chromium', headless=False,
            args=['--enable-unsafe-extension-debugging', '--autoplay-policy=no-user-gesture-required',
                  f'--disable-extensions-except={ROOT/"extension"}', f'--load-extension={ROOT/"extension"}'],
            viewport={'width': 1280, 'height': 860})
        try:
            sw = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event('serviceworker')
            cdp = await ctx.browser.new_browser_cdp_session()
            control = await ctx.new_page(); await control.goto(f'chrome-extension://{EXTENSION_ID}/popup.html')
            await control.evaluate('''()=>{window.events=[];chrome.runtime.onMessage.addListener(m=>{if(m.type==='event')window.events.push(m.event);});}''')
            page = await ctx.new_page()
            await page.goto(f'https://www.youtube.com/watch?v={video}', wait_until='domcontentloaded')
            for label in ('Accept all', 'Reject all', 'I agree'):
                button = page.get_by_role('button', name=label)
                if await button.count(): await button.first.click(); break
            await page.wait_for_selector('video', timeout=30000)
            await page.evaluate('()=>{const v=document.querySelector("video");v.pause();}')
            targets = (await cdp.send('Target.getTargets', {'filter': [{}]}))['targetInfos']
            target = next(t['targetId'] for t in targets if t['type'] == 'tab' and 'youtube.com/watch' in t['url'])
            await page.bring_to_front()
            # Clicking the toolbar button grants activeTab for this YouTube tab, exactly as a user would.
            await cdp.send('Extensions.triggerAction', {'id': EXTENSION_ID, 'targetId': target})
            tab_id = await sw.evaluate('async()=>(await chrome.tabs.query({active:true,lastFocusedWindow:true}))[0].id')
            result = await control.evaluate('(id)=>chrome.runtime.sendMessage({target:"background",type:"start",tabId:id})', tab_id)
            assert not result.get('error'), result
            await page.bring_to_front()
            await page.evaluate('()=>{const v=document.querySelector("video");v.currentTime=0;v.muted=false;v.play();}')
            started, first, taken = time.time(), None, set()
            while time.time() - started < seconds:
                state = await page.evaluate(f'''()=>{{const r={OVERLAY};if(!r)return null;
                    return {{text:r.querySelector('.lines').innerText,sound:!!r.querySelector('.lines .sound'),tag:!!r.querySelector('.lines .tag'),
                    ad:!!document.querySelector('.ad-showing'),t:document.querySelector('video').currentTime}}}}''')
                if state and state['text'].strip() and first is None: first = round(time.time() - started, 2)
                for kind in ('sound', 'tag'):
                    if state and state[kind] and kind not in taken and not state['ad']:
                        taken.add(kind); await page.screenshot(path=str(shots/f'youtube-{video}-{kind}.png'))
                if state and 'caption' not in taken and not state['ad'] and state['t'] > 45 and state['text'].strip():
                    taken.add('caption'); await page.screenshot(path=str(shots/f'youtube-{video}-caption.png'))
                await asyncio.sleep(.25)
            position = await page.evaluate('document.querySelector("video").currentTime')
            await page.evaluate(f"()=>{OVERLAY}.querySelector('.open').click()"); await asyncio.sleep(.4)
            await page.screenshot(path=str(shots/f'youtube-{video}-transcript.png'))
            entries = await page.evaluate(f'''()=>[...{OVERLAY}.querySelectorAll('.panel li')].map(li=>({{
                sound:li.querySelector('.sound')?.textContent||null,tag:li.querySelector('.tag')?.textContent||null,
                text:[...li.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ')}}))''')
            ref = reference(video, 0, position - 1)[0]
            hyp = normalize(' '.join(e['text'] for e in entries))
            measures = jiwer.process_words(ref, hyp)
            events = await control.evaluate('window.events')
            out.update({'first_text_s': first, 'video_position_s': round(position, 1), 'wer_vs_youtube_human_captions': round(measures.wer, 4),
                        'substitutions': measures.substitutions, 'deletions': measures.deletions, 'insertions': measures.insertions,
                        'reference_words': len(ref.split()), 'errors_from_service': [e for e in events if e['type'] == 'error'],
                        'transcript': [e['sound'] or f"{e['tag'] or ''} {e['text']}".strip() for e in entries]})
            await control.evaluate('()=>chrome.runtime.sendMessage({target:"background",type:"stop"})')
        finally:
            (ROOT/f'.build/evaluation/youtube-{video}.json').write_text(json.dumps(out, indent=2))
            await ctx.close()
    print(json.dumps({k: v for k, v in out.items() if k != 'transcript'}, indent=1))
    print('\n'.join(out.get('transcript', [])))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 150))
