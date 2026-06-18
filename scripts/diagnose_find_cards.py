"""Locate the HTML structure of scholarshipdb listings by anchoring on a
known title text and walking up the DOM."""
import asyncio, json, os, pathlib, sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

_envfile = pathlib.Path(".env.local")
if _envfile.exists():
    for line in _envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from worker.browser import start_browser, navigate, wait_for_content


async def main():
    url = sys.argv[1]
    needle = sys.argv[2] if len(sys.argv) > 2 else "PhD ESPhil"
    print(f"Loading: {url}\nNeedle: {needle!r}\n")

    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        await wait_for_content(tab, max_wait=20.0)
        await asyncio.sleep(3)

        js = r"""
        const needle = NEEDLE;
        // Walk up from a text-matching element to a "card" parent
        let target = null;
        for (const el of document.querySelectorAll('*')) {
          const t = (el.textContent || '').trim();
          if (t === needle || t.startsWith(needle)) {
            // pick the smallest element that contains exactly the title text
            if (!target || el.contains(target) === false && target.contains(el)) {
              target = el;
            }
            if (t === needle) { target = el; break; }
          }
        }
        if (!target) return JSON.stringify({error: 'needle not found in textContent'});

        // Walk up the tree, recording each ancestor with siblings of similar shape
        const path = [];
        let cur = target;
        for (let i = 0; i < 12 && cur; i++) {
          const tag = cur.tagName.toLowerCase();
          const cls = (cur.className && typeof cur.className === 'string') ? cur.className : '';
          const sibs = cur.parentElement
            ? Array.from(cur.parentElement.children).filter(c => c.tagName === cur.tagName).length
            : 0;
          path.push({
            level: i,
            tag,
            cls: cls.slice(0, 80),
            siblings: sibs,
            outer: cur.outerHTML.slice(0, 300).replace(/\n+/g, ' '),
          });
          cur = cur.parentElement;
        }
        return JSON.stringify(path);
        """
        js = js.replace("NEEDLE", json.dumps(needle))
        r = await tab.execute_script(js, return_by_value=True)
        result = json.loads(r["result"]["result"]["value"] or "[]")

        if isinstance(result, dict) and result.get("error"):
            print(f"ERROR: {result['error']}")
            return

        print(f"Walked {len(result)} ancestors of the title element:\n")
        for n in result:
            marker = "<-- card?" if n["siblings"] >= 3 else ""
            print(f"  L{n['level']:2}  <{n['tag']:6} class='{n['cls']}'>  siblings={n['siblings']:3}  {marker}")
            if n["siblings"] >= 3:
                print(f"        outer: {n['outer'][:200]}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
