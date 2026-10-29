"""Add/update only the Audit tab. Existing Parameters and Data are preserved."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from generator import SHEET_URL, audit, clipboard_html
from sheet_setup import paste

ROOT = Path(__file__).resolve().parent


def main():
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(locale="en-US", viewport={"width": 1600, "height": 1000}, permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        page.goto(SHEET_URL + "?hl=en", wait_until="domcontentloaded", timeout=60000)
        page.locator("#t-name-box").wait_for(timeout=60000)
        tab = page.get_by_role("button", name="Audit", exact=True)
        if not tab.count():
            page.get_by_role("button", name="Add Sheet", exact=True).click()
            page.wait_for_timeout(600)
            selected = page.locator('.docs-sheet-tab.docs-sheet-active-tab')
            selected.dblclick()
            page.keyboard.press("Control+a")
            page.keyboard.type("Audit")
            page.keyboard.press("Enter")
        tab.click()
        page.wait_for_timeout(500)
        print("AUDIT URL", page.url, flush=True)
        paste(page, "A1", clipboard_html(audit(), "Audit"), html=True)
        page.wait_for_timeout(3500)
        page.screenshot(path=str(ROOT / "artifacts/audit-installed.png"))
        (ROOT / "artifacts/audit-install.json").write_text(json.dumps({"url": page.url, "tab": "Audit", "existing_tabs_preserved": True}, indent=2) + "\n", encoding="utf8")
        print("Audit formulas installed; existing tabs untouched.", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
