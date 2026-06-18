"""For a given selector, list all matching elements and their parents to
see why the sampler picks the wrong group."""
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
    selector = sys.argv[2]
    print(f"Loading: {url}\nSelector: {selector!r}\n")
    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        await wait_for_content(tab, max_wait=20.0)
        await asyncio.sleep(2)

        js = f"""
        const sel = {json.dumps(selector)};
        const matches = Array.from(document.querySelectorAll(sel));
        const byParent = new Map();
        for (const m of matches) {{
          const p = m.parentElement;
          if (!p) continue;
          if (!byParent.has(p)) byParent.set(p, []);
          byParent.get(p).push(m);
        }}
        const out = [];
        for (const [p, list] of byParent.entries()) {{
          out.push({{
            parentClass: (p.className && typeof p.className === 'string') ? p.className : '',
            parentTag: p.tagName.toLowerCase(),
            childCount: list.length,
            firstChildText: (list[0].textContent || '').trim().slice(0, 80),
            firstChildOuter: list[0].outerHTML.slice(0, 200),
          }});
        }}
        return JSON.stringify(out);
        """
        r = await tab.execute_script(js, return_by_value=True)
        out = json.loads(r["result"]["result"]["value"] or "[]")
        out.sort(key=lambda x: -x["childCount"])
        print(f"matched {sum(g['childCount'] for g in out)} elements across {len(out)} parents:\n")
        for g in out[:15]:
            print(f"  parent <{g['parentTag']} class='{g['parentClass'][:60]}'>")
            print(f"    children: {g['childCount']}")
            print(f"    first child text: {g['firstChildText']!r}")
            print(f"    first child outer: {g['firstChildOuter'][:160]}")
            print()
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
