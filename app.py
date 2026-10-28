"""Live, read-only Google Sheets analysis and snapshot-consistent PDF exports."""
from __future__ import annotations

import asyncio
import os
import re
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from analytics import Settings, analyze, parse_csv
from generator import SHEET_ID, SHEET_URL
from report import build_pdf

ROOT = Path(__file__).resolve().parent
app = FastAPI(title='Weyland-Yutani Mining Observatory', version='1.0.0')
snapshots = OrderedDict()
results = OrderedDict()
fetch_lock = asyncio.Lock()
report_lock = asyncio.Semaphore(1)
last_fetch = 0.
current_snapshot = None


class AnalysisRequest(Settings):
    snapshot: str | None = Field(default=None, pattern=r'^[a-f0-9]{16}$')
    refresh: bool = False


def remember(cache, key, value, limit=12):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


async def fetch_source(refresh=False):
    global last_fetch, current_snapshot
    async with fetch_lock:
        if current_snapshot is not None and time.monotonic() - last_fetch < (2 if refresh else 30):
            return current_snapshot
        # Fixed public Google document only. There is no arbitrary-URL fetch endpoint.
        url = f'https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq'
        try:
            async with httpx.AsyncClient(timeout=40, trust_env=False) as client:
                response = await client.get(url, params={'tqx': 'out:csv', 'sheet': 'Data', 'headers': 1, '_': int(time.time())})
                for _ in range(4):
                    if not response.is_redirect:
                        break
                    target = str(response.url.join(response.headers['location']))
                    parsed = urlparse(target)
                    if parsed.scheme != 'https' or not (parsed.hostname == 'docs.google.com' or (parsed.hostname or '').endswith('.googleusercontent.com')):
                        raise ValueError('Google returned an unsupported redirect. Ensure link access is enabled.')
                    response = await client.get(target)
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    raise ValueError('The source exceeds the 2 MB limit.')
                snapshot = parse_csv(response.text)
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(502, f'Cannot refresh the Google Sheet: {error}. Previously displayed data is preserved; no simulated fallback is substituted.') from error
        snapshot['sheet_url'] = SHEET_URL
        current_snapshot = snapshot
        last_fetch = time.monotonic()
        remember(snapshots, snapshot['snapshot'], snapshot)
        return snapshot


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    if '/api/' in request.url.path:
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/healthz')
def health():
    return {'status': 'ok'}


@app.get('/')
def index():
    return FileResponse(ROOT/'static/index.html')


@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get('/api/source')
def source():
    return {'sheet_url': SHEET_URL, 'sheet_id': SHEET_ID, 'tab': 'Data', 'generator': 'Cell formulas only; no Apps Script'}


@app.post('/api/analyze')
async def analysis(request: AnalysisRequest):
    if request.snapshot:
        snapshot = snapshots.get(request.snapshot)
        if snapshot is None:
            raise HTTPException(409, 'That snapshot has expired. Refresh the sheet before analyzing or exporting.')
    else:
        snapshot = await fetch_source(request.refresh)
    settings = Settings.model_validate(request.model_dump(exclude={'snapshot', 'refresh'}))
    result = await run_in_threadpool(analyze, snapshot, settings)
    # Immutable result handles make PDF export reproduce precisely the shown settings/data.
    import hashlib, json
    handle = hashlib.sha256(json.dumps([snapshot['snapshot'], snapshot['fetched_at'], settings.model_dump()], sort_keys=True).encode()).hexdigest()[:24]
    remember(results, handle, result)
    return {**result, 'report_id': handle}


@app.get('/api/report/{handle}.pdf')
async def pdf(handle: str, inline: bool = False):
    if not re.fullmatch('[a-f0-9]{24}', handle) or handle not in results:
        raise HTTPException(409, 'The displayed analysis has expired. Run the analysis again before exporting.')
    async with report_lock:
        result = results[handle]
        content = await run_in_threadpool(build_pdf, result)
    disposition = 'inline' if inline else 'attachment'
    return Response(content, media_type='application/pdf', headers={'Content-Disposition': f'{disposition}; filename="weyland-mining-{result["source"]["snapshot"]}.pdf"'})


app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
