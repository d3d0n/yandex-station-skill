from __future__ import annotations

from pathlib import Path

from playwright.async_api import async_playwright


async def render_magic_qr_png(url: str, out_path: Path) -> None:
    """Open Yandex Passport magic code page and screenshot the *actual* QR on the page.

    This is the QR that the Yandex app expects (so user doesn't scan a QR that opens a page
    that then shows another QR).

    Strategy:
    - load the url
    - try to locate an obvious QR element (img/canvas/svg)
    - screenshot that element
    - fallback to full-page screenshot if element not found
    """

    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 900, "height": 900})
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        candidates = [
            # common patterns
            "img[src^='data:image']",
            "img[alt*='QR' i]",
            "img[alt*='qr' i]",
            "canvas",
            "svg",
        ]

        el = None
        for sel in candidates:
            loc = page.locator(sel).first
            try:
                if await loc.count():
                    # some pages have tons of svg; try to keep it reasonable
                    if await loc.is_visible():
                        el = loc
                        break
            except Exception:
                continue

        if el is not None:
            try:
                await el.screenshot(path=str(out_path))
            except Exception:
                await page.screenshot(path=str(out_path), full_page=False)
        else:
            await page.screenshot(path=str(out_path), full_page=False)

        await context.close()
        await browser.close()
