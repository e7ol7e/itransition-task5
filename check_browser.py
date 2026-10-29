"""Live end-to-end investigation checks: uv run python check_browser.py [base URL]."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765'
    output = Path(__file__).parent/'artifacts'
    output.mkdir(exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        page = browser.new_page(viewport={'width':1440, 'height':1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(base, wait_until='networkidle')
        page.wait_for_function('window.currentAnalysis?.report_id', timeout=60000)
        data = page.evaluate('window.currentAnalysis')
        print('VALIDATION', page.locator('.validation-score').inner_text())
        assert data['series'][0]['validation']['available']
        page.locator('#show-counterfactual').check()
        assert 'same-seed output without events' in page.locator('#chart-legend').inner_text()
        page.locator('.investigation-card').scroll_into_view_if_needed()
        page.screenshot(path=str(output/'investigation-desktop.png'))
        day = data['series'][0]['anomalies'][0]['date'] if data['series'][0]['anomalies'] else data['source']['dates'][0]
        page.locator('#inspect-date').fill(day)
        page.get_by_role('button', name='Show calculations', exact=True).click()
        page.wait_for_function("document.querySelector('#inspector-body').innerText.includes('Snapshot')")
        assert page.locator('.evidence-rule').count() == 4
        assert 'Which mines contributed?' in page.locator('#inspector-body').inner_text()
        page.screenshot(path=str(output/'investigation-inspector.png'))
        page.locator('#close-inspector').click()
        page.locator('#production-chart').click(position={'x':350, 'y':120})
        page.wait_for_function("document.querySelector('#point-inspector').open")
        page.keyboard.press('Escape')
        if data['series'][0]['anomalies']:
            page.locator('.inspect-point').first.click()
            page.wait_for_function("document.querySelector('#point-inspector').open")
            page.locator('#close-inspector').click()
        mine = data['source']['mines'][0]
        page.get_by_role('button', name=mine, exact=True).click()
        page.wait_for_function('(name)=>document.querySelector("#investigation-name").innerText===name', arg=mine)
        page.locator('#inspect-date-form button').click()
        page.wait_for_function("document.querySelector('#inspector-body').innerText.includes('Snapshot')")
        assert 'Which mines contributed?' not in page.locator('#inspector-body').inner_text()
        page.keyboard.press('Escape')
        for kind in ['bar', 'stacked', 'line']:
            page.locator('#chart-type').select_option(kind)
            page.wait_for_function('(kind)=>window.currentAnalysis.settings.chart_type===kind', arg=kind)
        # Disabled detectors remain visible but cannot add to the enabled union.
        page.locator('input[name=method][value=iqr]').uncheck()
        page.get_by_role('button', name='Apply analysis', exact=True).click()
        page.wait_for_function('!window.currentAnalysis.settings.methods.includes("iqr")')
        assert 'Disabled' in page.locator('#comparison-body').inner_text()
        preserved = page.evaluate('window.currentAnalysis.report_id')
        page.route('**/api/analyze', lambda route: route.fulfill(status=502, json={'detail':'Controlled refresh failure'}))
        page.locator('#refresh').click()
        page.wait_for_function('!document.querySelector("#error").hidden')
        assert page.evaluate('window.currentAnalysis.report_id') == preserved
        page.unroute('**/api/analyze')
        page.locator('#refresh').click()
        page.wait_for_function('!document.body.classList.contains("busy")')
        assert page.locator('#error').is_hidden()
        with page.expect_download(timeout=120000) as download:
            page.locator('#pdf').click()
        download.value.save_as(output/'browser-investigation.pdf')
        assert (output/'browser-investigation.pdf').read_bytes().startswith(b'%PDF')
        page.set_viewport_size({'width':390, 'height':844})
        page.locator('.investigation-card').scroll_into_view_if_needed()
        page.screenshot(path=str(output/'investigation-mobile.png'))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Page overflows mobile width'
        assert not errors, errors
        print('PASS: chart / register / date inspector; per-mine evidence; chart modes; method selection; refresh; PDF; mobile; no browser errors')
        browser.close()


if __name__ == '__main__': main()
