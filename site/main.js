// Tonal landing page: hero caption demo and the install Copy button.
(() => {
  'use strict';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Hero demo. Matches the overlay: one caption line at a time that revises in place,
     sound cues on their own line, and a tone label appended after the line once it arrives.
     Finished lines are added to the transcript in the same format. */
  const box = document.querySelector('[data-captions]');
  const idle = document.querySelector('[data-idle]');
  const list = document.querySelector('[data-transcript]');
  const toggle = document.querySelector('[data-toggle]');
  const toggleLabel = document.querySelector('[data-toggle-label]');

  const LOOP_MS = 14500;
  const VISIBLE = 1;
  const EARLIER = [['00:55', 'Have you seen the new schedule?'], ['00:58', 'They moved everything up.']];
  const SCRIPT = [
    [400, { id: 'a', text: 'So the client' }],
    [800, { id: 'a', text: 'So the client called this morning' }],
    [1200, { id: 'a', text: 'So the client called this morning about the lunch' }],
    [1600, { id: 'a', text: 'So the client called this morning about the launch date.', final: '01:02' }],
    [3400, { id: 'b', text: 'Two weeks?' }],
    [3800, { id: 'b', text: 'Two weeks? You’re kidding me.', final: '01:05' }],
    [4500, { id: 'b', tag: 'surprised' }],
    [6200, { id: 'c', text: 'I wish' }],
    [6600, { id: 'c', text: 'I wish I was.', final: '01:08' }],
    [8000, { id: 'd', sound: 'laughter', final: '01:09' }],
    [9600, { id: 'e', text: 'Tight is' }],
    [10000, { id: 'e', text: 'Tight is one word for it.', final: '01:11' }],
    [10700, { id: 'e', tag: 'frustrated' }],
    [13000, { clear: true }],
  ];

  if (box && list && toggle) {
    let rows = new Map();
    const logged = new Map();
    let step = 0;
    let elapsed = 0;
    let last = 0;
    let playing = !reduce;
    let onscreen = true;
    let frame = 0;

    const tagEl = (tag) => { const s = document.createElement('span'); s.className = 'tag'; s.textContent = `(${tag})`; return s; };
    const fill = (li, row) => {
      li.replaceChildren(li.querySelector('time'));
      if (row.sound) { const s = document.createElement('span'); s.className = 'sound'; s.textContent = `[${row.sound}]`; li.append(s); return; }
      li.append(row.text);
      if (row.tag) li.append(tagEl(row.tag));
    };
    const line = (time, row) => {
      const li = document.createElement('li');
      const t = document.createElement('time');
      t.textContent = time;
      li.append(t);
      fill(li, row);
      return li;
    };
    const resetTranscript = () => {
      logged.clear();
      list.replaceChildren(...EARLIER.map(([time, text]) => line(time, { text })));
    };

    const render = () => {
      const shown = [...rows.values()].slice(-VISIBLE);
      box.replaceChildren(...shown.map((row) => {
        const p = document.createElement('p');
        if (row.sound) { p.className = 'sound'; p.textContent = `[${row.sound}]`; return p; }
        p.append(row.text);
        if (row.tag) p.append(tagEl(row.tag));
        return p;
      }));
      box.hidden = !shown.length;
      idle.hidden = shown.length > 0;
    };

    const apply = ([, event]) => {
      if (event.clear) { rows = new Map(); return; }
      const row = { ...rows.get(event.id), ...event };
      rows.set(event.id, row);
      const existing = logged.get(event.id);
      if (existing) { fill(existing, row); return; }
      if (row.final) {
        const li = line(row.final, row);
        list.append(li);
        logged.set(event.id, li);
      }
    };

    const tick = (now) => {
      frame = 0;
      if (!playing || !onscreen) return;
      elapsed += Math.min(now - (last || now), 100);
      last = now;
      if (elapsed >= LOOP_MS) { elapsed = 0; step = 0; rows = new Map(); resetTranscript(); render(); }
      let changed = false;
      while (step < SCRIPT.length && SCRIPT[step][0] <= elapsed) { apply(SCRIPT[step++]); changed = true; }
      if (changed) render();
      frame = requestAnimationFrame(tick);
    };
    const run = () => { if (!frame && playing && onscreen) { last = 0; frame = requestAnimationFrame(tick); } };

    const setPlaying = (value) => {
      playing = value;
      toggle.setAttribute('aria-pressed', String(!value));
      toggleLabel.textContent = value ? 'Pause' : 'Play';
      if (value) run();
    };
    toggle.addEventListener('click', () => setPlaying(!playing));

    // With motion, start from the beginning of the bit; otherwise keep the finished frame from the HTML.
    if (playing) { resetTranscript(); render(); }
    setPlaying(playing);

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(([entry]) => { onscreen = entry.isIntersecting; run(); }, { threshold: 0.05 }).observe(box.closest('.demo'));
    }
  }

  /* Copy install commands. */
  for (const button of document.querySelectorAll('[data-copy]')) {
    button.addEventListener('click', async () => {
      const code = button.closest('.code').querySelector('code');
      try {
        await navigator.clipboard.writeText(code.textContent);
        button.textContent = 'Copied';
      } catch {
        button.textContent = 'Press ⌘C';
        const range = document.createRange();
        range.selectNodeContents(code);
        getSelection().removeAllRanges();
        getSelection().addRange(range);
      }
      setTimeout(() => { button.textContent = 'Copy'; }, 1800);
    });
  }
})();
