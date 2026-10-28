"""Browser setup helpers for the public Google Sheet (no generation script)."""
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
from generator import SHEET_URL
WIDTHS = {chr(65+i):160 for i in range(26)}


def go(page, cell):
    box=page.locator('#t-name-box')
    box.click()
    box.fill(cell)
    box.press('Enter')
    page.wait_for_timeout(350)


def paste(page, cell, text, html=False):
    page.keyboard.press('Escape')
    go(page,cell)
    if html:
        page.evaluate("""async text => navigator.clipboard.write([new ClipboardItem({
            'text/html':new Blob([text],{type:'text/html'}),
            'text/plain':new Blob(['Sheet cells'],{type:'text/plain'})})])""", text)
    else:
        page.evaluate('async text => navigator.clipboard.writeText(text)',text)
    page.keyboard.press('Control+v')
    page.wait_for_timeout(500)


def resize(page,columns,width):
    go(page,columns)
    first,last=columns.split(':')
    x=46+sum(WIDTHS[chr(i)] for i in range(65,ord(first)))+min(30,WIDTHS[first]/2)
    page.mouse.click(x,151,button='right')
    try:
        page.get_by_role('menuitem',name=re.compile(r'Resize column|Изменить размер столб')).click(timeout=5000)
    except Exception:
        page.screenshot(path='artifacts/setup-error.png')
        print(page.locator('[role=menu]').all_text_contents(),flush=True)
        raise
    dialog=page.get_by_role('dialog')
    dialog.get_by_role('textbox').fill(str(width))
    dialog.get_by_role('button',name=re.compile(r'^(OK|ОК)$')).click()
    for code in range(ord(first),ord(last)+1):WIDTHS[chr(code)]=width


def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(locale='en-US',viewport={'width':1600,'height':1000},permissions=['clipboard-read','clipboard-write'])
        page=context.new_page()
        page.goto(SHEET_URL+'?hl=en',wait_until='domcontentloaded',timeout=60000)
        page.locator('#t-name-box').wait_for(timeout=60000)
        page.get_by_role('button',name='Parameters',exact=True).click()
        for column,width in [('A:A',220),('B:B',160),('C:C',350),('D:E',110),('F:F',30),('G:G',180),('H:H',140)]:
            resize(page,column,width)
            print('Sized',column,width,flush=True)
        paste(page,'B42','https://task5.evgeniy.win/')
        go(page,'A1')
        page.screenshot(path='artifacts/generator-parameters.png')
        print('Parameters formatted',flush=True)
        page.get_by_role('button',name='Data',exact=True).click()
        WIDTHS.update({chr(65+i):100 for i in range(26)})
        resize(page,'A:N',115)
        go(page,'A1')
        page.wait_for_timeout(1500)
        page.screenshot(path='artifacts/generator-data.png')
        context.close()
        browser.close()


if __name__=='__main__': main()
