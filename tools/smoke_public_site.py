#!/usr/bin/env python3
"""Render the V1 public download page at desktop and mobile release sizes."""

from __future__ import annotations

import json
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = ROOT / "server" / "geo.allgood.cn"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return


def main() -> None:
    handler = partial(QuietHandler, directory=str(SERVER_ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    screenshots = []

    try:
        with sync_playwright() as playwright:
            launch = {"headless": True}
            chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            if chrome.exists():
                launch["executable_path"] = str(chrome)
            browser = playwright.chromium.launch(**launch)
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                # The production manifest remains on the current release until
                # the signed packages are atomically published last.
                page.route("**/update.json", lambda route: route.abort())
                page.goto(f"{base_url}/tools/", wait_until="networkidle")
                page.locator("h1").wait_for()
                heading = page.locator("h1").inner_text().strip()
                if not heading or not any(term in heading for term in ("AI", "品牌", "brand")):
                    raise AssertionError(f"unexpected public page heading: {heading}")
                page.locator("#release-badge").wait_for()
                if page.locator("#release-badge").inner_text().strip() != "v1.0.0":
                    raise AssertionError("public release badge is not V1.0.0")

                download_paths = page.locator('a[href^="/downloads/GEO-SOP-"]').evaluate_all(
                    "links => [...new Set(links.map(link => link.getAttribute('href')))]"
                )
                expected = {
                    "/downloads/GEO-SOP-macOS.dmg",
                    "/downloads/GEO-SOP-macOS-Intel.dmg",
                    "/downloads/GEO-SOP-Setup.exe",
                }
                if not expected.issubset(set(download_paths)):
                    raise AssertionError(f"missing permanent downloads: {expected - set(download_paths)}")

                images = page.locator("img")
                for index in range(images.count()):
                    images.nth(index).scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                failed_images = page.locator("img").evaluate_all(
                    "images => images.filter(img => !img.complete || img.naturalWidth < 1).map(img => img.getAttribute('src'))"
                )
                if failed_images:
                    raise AssertionError(f"public page images failed to render: {failed_images}")
                overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if overflow > 1:
                    raise AssertionError(f"public page has {overflow}px horizontal overflow at {width}x{height}")

                screenshot = Path(tempfile.gettempdir()) / f"geo-sop-v1-public-{width}x{height}.png"
                page.screenshot(path=str(screenshot), full_page=True)
                screenshots.append(str(screenshot))
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    print(json.dumps({"success": True, "screenshots": screenshots}, ensure_ascii=False))


if __name__ == "__main__":
    main()
