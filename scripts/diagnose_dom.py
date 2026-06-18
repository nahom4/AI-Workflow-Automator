"""Inspect the rendered DOM of a page directly. Looks for elements whose
text contains scholarship/job-like cues to find the listing container.
"""
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
    print(f"Loading: {url}")
    browser, tab = await start_browser(retries=2)
    try:
        await navigate(tab, url)
        await wait_for_content(tab, max_wait=20.0)
        await asyncio.sleep(2)

        # Look for elements with text matching scholarship cues, deduplicated
        # by their immediate parent's outerHTML structure.
        js = r"""
        const cues = ['scholarship', 'phd position', 'fully funded', 'stipend',
                     'doctoral', 'fellowship', 'university of', 'phd in '];
        const matches = [];
        for (const el of document.querySelectorAll('h1,h2,h3,h4,a,article,div,li')) {
          const text = (el.textContent || '').trim();
          if (text.length < 15 || text.length > 300) continue;
          const lc = text.toLowerCase();
          if (!cues.some(c => lc.includes(c))) continue;
          matches.push({
            tag: el.tagName.toLowerCase(),
            cls: el.className,
            text: text.slice(0, 150),
            parentTag: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
            parentCls: el.parentElement ? el.parentElement.className : null,
          });
          if (matches.length >= 30) break;
        }
        return JSON.stringify(matches);
        """
        r = await tab.execute_script(js, return_by_value=True)
        items = json.loads(r["result"]["result"]["value"] or "[]")
        print(f"\nfound {len(items)} elements matching scholarship cues:\n")
        for i in items[:20]:
            print(f"  <{i['tag']} class={i['cls'][:40]!r}> in <{i['parentTag']} class={i['parentCls'][:40]!r}>")
            print(f"    \"{i['text']}\"")

        # Also check page body length and any "no results" message
        body_text_r = await tab.execute_script(
            "return document.body.innerText.length",
            return_by_value=True,
        )
        print(f"\ndocument.body.innerText.length = {body_text_r['result']['result']['value']}")
        for needle in ["no results", "challenge", "captcha", "verify you", "blocked"]:
            r2 = await tab.execute_script(
                f"return document.body.innerText.toLowerCase().includes({json.dumps(needle)})",
                return_by_value=True,
            )
            if r2["result"]["result"]["value"]:
                print(f"  page contains: {needle!r}")
    finally:
        try:
            await browser.stop()
        except Exception:
            pass


asyncio.run(main())
