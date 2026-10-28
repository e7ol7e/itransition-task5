"""Install the prepared cell formulas through the public Google Sheets editor.

Run only when intentionally resetting generator parameters to repository defaults.
This setup automation is not part of the spreadsheet's generation logic.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright
from generator import SHEET_URL, main as build
from sheet_setup import go, paste

ROOT=Path(__file__).resolve().parent


def main():
    build()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(locale='en-US',viewport={'width':1600,'height':1000},permissions=['clipboard-read','clipboard-write'])
        page=context.new_page()
        page.goto(SHEET_URL+'?hl=en',wait_until='domcontentloaded',timeout=60000)
        page.locator('#t-name-box').wait_for(timeout=60000)
        for tab in ['Parameters','Data']:
            page.get_by_role('button',name=tab,exact=True).click()
            paste(page,'A1',(ROOT/'generator'/f'{tab}.html').read_text(encoding='utf8'),html=True)
            page.wait_for_timeout(1200)
            print('Synchronized',tab,flush=True)
        page.get_by_role('button',name='Parameters',exact=True).click()
        go(page,'A1')
        page.wait_for_timeout(1500)
        page.screenshot(path=str(ROOT/'artifacts/generator-final.png'))
        context.close()
        browser.close()


if __name__=='__main__':main()
