"""Verify and optionally record the real Sheets -> deployed dashboard -> PDF flow.

uv run python record_demo.py          # headless live end-to-end verification
uv run python record_demo.py --record # actual Chrome window, portable OBS, no audio
Original generator cell contents are restored in finally, including failed checks.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

os.environ['OPENBLAS_NUM_THREADS']='1'
sys.stdout.reconfigure(encoding='utf8')
import obsws_python as obs
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

from generator import SHEET_URL
from sheet_setup import go, paste

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'video'
OBS=Path('D:/Run/OBS-Studio-32.1.2-Windows-x64')
FFMPEG=Path('D:/Run/ffmpeg/ffmpeg-7.1.1-essentials_build/bin/ffmpeg.exe')
URL='https://task5.evgeniy.win/'
NAME='Task 5 Mining Observatory'


class Recorder:
    def __init__(self):
        self.client=None
        self.process=None
        self.config_path=OBS/'config/obs-studio/plugin_config/obs-websocket/config.json'
        self.original=self.config_path.read_bytes()
        self.recording=False

    def start(self):
        if 'obs64.exe' in subprocess.check_output(['tasklist','/FI','IMAGENAME eq obs64.exe'],text=True).lower():
            raise RuntimeError('OBS is already running. Close it before the dedicated demonstration capture.')
        config=json.loads(self.original.decode('utf-8-sig'))
        password=secrets.token_urlsafe(24)
        config.update(server_enabled=True,server_port=4458,auth_required=True,server_password=password)
        self.config_path.write_text(json.dumps(config),encoding='utf8')
        startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
        self.process=subprocess.Popen([str(OBS/'bin/64bit/obs64.exe'),'--portable','--minimize-to-tray','--disable-updater','--disable-shutdown-check'],cwd=OBS/'bin/64bit',startupinfo=startup,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                self.client=obs.ReqClient(host='127.0.0.1',port=4458,password=password,timeout=5)
                self.client.send('GetVersion',raw=True)
                break
            except Exception:time.sleep(1)
        if self.client is None:raise RuntimeError('Portable OBS did not start')
        c=self.client
        profiles=c.send('GetProfileList',raw=True)
        self.old_profile=profiles['currentProfileName']
        if self.old_profile==NAME and 'Task 3.5 VS Code' in profiles['profiles']:self.old_profile='Task 3.5 VS Code'
        if NAME not in profiles['profiles']:c.send('CreateProfile',{'profileName':NAME})
        c.send('SetCurrentProfile',{'profileName':NAME})
        for category,key,value in [('Output','Mode','Simple'),('SimpleOutput','FilePath',str(OUT)),('SimpleOutput','RecFormat2','mkv'),('SimpleOutput','RecQuality','HQ'),('SimpleOutput','RecEncoder','x264')]:
            c.send('SetProfileParameter',{'parameterCategory':category,'parameterName':key,'parameterValue':value})
        alternate=next(p for p in profiles['profiles'] if p!=NAME)
        c.send('SetCurrentProfile',{'profileName':alternate});c.send('SetCurrentProfile',{'profileName':NAME})
        c.send('SetVideoSettings',{'baseWidth':1920,'baseHeight':1080,'outputWidth':1920,'outputHeight':1080,'fpsNumerator':30,'fpsDenominator':1})
        collections=c.send('GetSceneCollectionList',raw=True)
        self.old_collection=collections['currentSceneCollectionName']
        if self.old_collection==NAME and 'Task 3.5 VS Code' in collections['sceneCollections']:self.old_collection='Task 3.5 VS Code'
        if NAME not in collections['sceneCollections']:c.send('CreateSceneCollection',{'sceneCollectionName':NAME})
        else:c.send('SetCurrentSceneCollection',{'sceneCollectionName':NAME})
        if not any(s['sceneName']==NAME for s in c.send('GetSceneList',raw=True)['scenes']):c.send('CreateScene',{'sceneName':NAME})
        source='Actual Task 5 Chrome window'
        if not any(i['inputName']==source for i in c.send('GetInputList',raw=True)['inputs']):
            c.send('CreateInput',{'sceneName':NAME,'inputName':source,'inputKind':'window_capture','inputSettings':{},'sceneItemEnabled':True})
        windows=c.send('GetInputPropertiesListPropertyItems',{'inputName':source,'propertyName':'window'},raw=True)['propertyItems']
        window=next(w['itemValue'] for w in windows if w['itemEnabled'] and 'Mining Observatory' in w['itemName'] and 'chrome.exe' in w['itemValue'].lower())
        c.send('SetInputSettings',{'inputName':source,'inputSettings':{'window':window,'priority':1,'method':2,'cursor':False,'client_area':True},'overlay':True})
        c.send('SetCurrentProgramScene',{'sceneName':NAME})
        item=c.send('GetSceneItemId',{'sceneName':NAME,'sourceName':source},raw=True)['sceneItemId']
        c.send('SetSceneItemTransform',{'sceneName':NAME,'sceneItemId':item,'sceneItemTransform':{'positionX':0,'positionY':0,'boundsType':'OBS_BOUNDS_SCALE_INNER','boundsWidth':1920,'boundsHeight':1080}})
        # Only one window-capture source, no microphones or desktop audio.
        for source_info in c.send('GetInputList',raw=True)['inputs']:
            if source_info['inputKind'] in {'wasapi_input_capture','wasapi_output_capture'}:c.send('SetInputMute',{'inputName':source_info['inputName'],'inputMuted':True})
        time.sleep(3)
        shot=c.send('GetSourceScreenshot',{'sourceName':NAME,'imageFormat':'png','imageWidth':1920,'imageHeight':1080},raw=True)
        data=base64.b64decode(shot['imageData'].split(',',1)[1]);(OUT/'capture-preview.png').write_bytes(data)
        if max(ImageStat.Stat(Image.open(io.BytesIO(data))).stddev)<2:raise RuntimeError('OBS preview is blank; refusing to record it')
        c.send('StartRecord');self.recording=True
        print('RECORDING STARTED',flush=True)

    def stop(self):
        if not self.recording:return None
        response=self.client.send('StopRecord',raw=True);self.recording=False
        filename=Path(response['outputPath'])
        print('Recording saved:',filename,flush=True)
        return filename

    def close(self):
        try:
            self.stop()
            if self.client:
                if getattr(self,'old_collection',None):self.client.send('SetCurrentSceneCollection',{'sceneCollectionName':self.old_collection})
                if getattr(self,'old_profile',None):self.client.send('SetCurrentProfile',{'profileName':self.old_profile})
        finally:
            if self.process:
                # WM_CLOSE requests a normal exit for this specific helper process.
                user32=ctypes.windll.user32
                callback=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
                def close_window(hwnd,_):
                    pid=ctypes.c_ulong();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                    if pid.value==self.process.pid:user32.PostMessageW(hwnd,0x0010,0,0)
                    return True
                user32.EnumWindows(callback(close_window),0)
                try:self.process.wait(timeout=12)
                except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=8)
            self.config_path.write_bytes(self.original)


def main(record=False):
    OUT.mkdir(exist_ok=True)
    recorder=None;raw_video=None
    changes={'B4':'8','B6':'=DATE(2099,5,30)','B7':'Uniform','B10':'70','B11':'140','B12':'0.92','D23':'2.0','E23':'1','G10':'Calpamos North'}
    originals={}
    def hold(seconds):time.sleep(seconds if record else .25)
    def pdf_page(page,number):
        frame=next((f for f in page.frames if f.url.startswith('chrome-extension:')),None)
        if frame:
            selector=frame.locator('#pageSelector')
            selector.wait_for(timeout=60000)
            selector.fill(str(number));selector.press('Enter')
        else:
            # Some headed Chrome builds hide the PDF extension target, although
            # its native toolbar is rendered. Its page-number field has a fixed
            # offset within the centered toolbar; this path is visually verified.
            width=page.evaluate('innerWidth')
            page.mouse.click(width/2-185,28)
            page.keyboard.press('Control+a')
            page.keyboard.insert_text(str(number));page.keyboard.press('Enter')
        time.sleep(.6)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=not record,args=['--start-fullscreen','--window-size=1920,1080','--enable-features=PdfOopif'],ignore_default_args=['--enable-automation'])
        options={'locale':'en-US','permissions':['clipboard-read','clipboard-write'],'accept_downloads':True}
        if record:options['no_viewport']=True
        else:options['viewport']={'width':1600,'height':1000}
        context=browser.new_context(**options)
        dashboard=context.new_page();dashboard.goto(URL,wait_until='domcontentloaded',timeout=60000)
        dashboard.wait_for_function('window.currentAnalysis',timeout=60000)
        if record:
            window=context.new_cdp_session(dashboard)
            window_id=window.send('Browser.getWindowForTarget')['windowId']
            window.send('Browser.setWindowBounds',{'windowId':window_id,'bounds':{'windowState':'fullscreen'}})
            dashboard.wait_for_function('Math.abs(innerHeight-screen.height)<=2 && Math.abs(innerWidth-screen.width)<=2')
            window.detach()
        baseline=dashboard.evaluate('currentAnalysis.source.snapshot')
        sheet=context.new_page();sheet.goto(SHEET_URL+'?hl=en',wait_until='domcontentloaded',timeout=60000)
        sheet.locator('#t-name-box').wait_for(timeout=60000)
        sheet.get_by_role('button',name='Parameters',exact=True).click()
        for cell in changes:
            go(sheet,cell)
            originals[cell]=sheet.locator('#t-formula-bar-input').inner_text().rstrip('\n')
        (OUT/'original-inputs.json').write_text(json.dumps({'snapshot':baseline,'cells':originals},ensure_ascii=False,indent=2),encoding='utf8')
        go(sheet,'A1')
        changed=False
        try:
            dashboard.bring_to_front()
            if record:recorder=Recorder();recorder.start()
            hold(5)
            sheet.bring_to_front();hold(5)
            for cell,value in changes.items():
                changed=True
                paste(sheet,cell,value)
                hold(1.4 if cell in ['B4','B7','B12'] else .7)
            go(sheet,'A15:B19');hold(4)
            sheet.get_by_role('button',name='Data',exact=True).click();go(sheet,'A1');hold(6)
            sheet.screenshot(path=str(OUT/'generated-sheet.png'))
            dashboard.bring_to_front();hold(3)
            for _ in range(12):
                dashboard.locator('#refresh').click()
                dashboard.wait_for_function("!document.body.classList.contains('busy')",timeout=60000)
                source=dashboard.evaluate('currentAnalysis.source')
                if len(source['mines'])==8 and len(source['dates'])==150:break
                time.sleep(2)
            assert len(source['mines'])==8 and len(source['dates'])==150,source
            assert source['snapshot']!=baseline
            assert 'Calpamos North' in source['mines']
            print('LIVE SHEET CHECK PASSED: 8 mines, 150 days, renamed mine, changed distribution and event',flush=True)
            hold(6)
            dashboard.get_by_role('button',name='Calpamos North',exact=True).click();hold(5)
            dashboard.locator('[name="z_threshold"]').fill('2.5');hold(2)
            dashboard.get_by_role('button',name='Apply analysis',exact=True).click()
            dashboard.wait_for_function("!document.body.classList.contains('busy')")
            dashboard.locator('.chart-card').scroll_into_view_if_needed();hold(3)
            dashboard.locator('#chart-type').select_option('bar')
            dashboard.wait_for_function("!document.body.classList.contains('busy')");hold(4)
            dashboard.locator('#trend-degree').select_option('3')
            dashboard.wait_for_function("!document.body.classList.contains('busy')");hold(4)
            dashboard.get_by_role('button',name='Network total',exact=True).click()
            dashboard.locator('#chart-type').select_option('stacked')
            dashboard.wait_for_function("!document.body.classList.contains('busy')");hold(5)
            dashboard.locator('#show-counterfactual').check();hold(4)
            dashboard.locator('.investigation-card').evaluate('e=>scrollTo({top:e.getBoundingClientRect().top+scrollY-24,behavior:"smooth"})');hold(4)
            dashboard.locator('#inspect-date-form button').click()
            dashboard.wait_for_function("document.querySelector('#inspector-body').innerText.includes('Snapshot')")
            hold(5)
            dashboard.locator('#point-inspector').evaluate('e=>e.scrollTo({top:e.scrollHeight,behavior:"smooth"})');hold(4)
            dashboard.locator('#close-inspector').click()
            dashboard.locator('.validation-details').evaluate('e=>scrollTo({top:e.getBoundingClientRect().top+scrollY-24,behavior:"smooth"})');hold(5)
            dashboard.locator('#statistics').scroll_into_view_if_needed();hold(6)
            dashboard.locator('#anomalies').scroll_into_view_if_needed();hold(5)
            if dashboard.locator('#next').is_enabled():dashboard.locator('#next').click();hold(3)
            dashboard.evaluate('window.scrollTo(0,0)');hold(3)
            with dashboard.expect_download(timeout=180000) as event:
                dashboard.locator('#pdf').click()
                hold(.8)
                if recorder:recorder.client.send('PauseRecord')
            report=OUT/'Task5-demonstration-report.pdf';event.value.save_as(report)
            if recorder:recorder.client.send('ResumeRecord')
            data=dashboard.evaluate('currentAnalysis')
            (OUT/'demonstration-analysis.json').write_text(json.dumps(data),encoding='utf8')
            text_reader=PdfReader(report)
            case_page=next((i+1 for i,page in enumerate(text_reader.pages) if '04 / Anomaly casebook' in page.extract_text()),12)
            validation_page=next(i+1 for i,page in enumerate(text_reader.pages) if '05 / Detector investigation' in page.extract_text())
            print('PDF CHECK PASSED:',len(text_reader.pages),'pages,',report.stat().st_size,'bytes',flush=True)
            hold(3)
            pdf=context.new_page()
            pdf.goto(report.resolve().as_uri()+'#zoom=85',wait_until='domcontentloaded',timeout=60000)
            pdf.bring_to_front();time.sleep(4);pdf_page(pdf,1);hold(8)
            pdf.screenshot(path=str(OUT/'report-cover.png'))
            pdf_page(pdf,2);hold(5)
            pdf_page(pdf,case_page);hold(6)
            pdf.screenshot(path=str(OUT/'report-anomalies.png'))
            pdf_page(pdf,validation_page);hold(5)
            pdf.screenshot(path=str(OUT/'report-validation.png'))
            dashboard.bring_to_front();dashboard.evaluate('window.scrollTo(0,0)');hold(4)
            if recorder:raw_video=recorder.stop()
            print('End-to-end demonstration complete',flush=True)
        finally:
            try:
                if recorder:recorder.close()
            finally:
                try:
                    if changed:
                        sheet.bring_to_front();sheet.get_by_role('button',name='Parameters',exact=True).click()
                        for cell,value in originals.items():paste(sheet,cell,value)
                        go(sheet,'A1');time.sleep(3)
                        dashboard.locator('#refresh').click();dashboard.wait_for_function("!document.body.classList.contains('busy')",timeout=60000)
                        restored=dashboard.evaluate('currentAnalysis.source.snapshot')
                        if restored!=baseline:
                            for _ in range(8):
                                time.sleep(2)
                                dashboard.locator('#refresh').click();dashboard.wait_for_function("!document.body.classList.contains('busy')",timeout=60000)
                                restored=dashboard.evaluate('currentAnalysis.source.snapshot')
                                if restored==baseline:break
                        if restored!=baseline:raise RuntimeError('Generator restoration did not reproduce the original snapshot; original cells are saved in video/original-inputs.json.')
                        print('Restored exact original generator inputs and snapshot',flush=True)
                finally:
                    context.close();browser.close()
    if raw_video:
        target=OUT/'Task5-demonstration.mp4'
        subprocess.run([str(FFMPEG),'-y','-i',str(raw_video),'-map','0:v:0','-c:v','copy','-an','-movflags','+faststart',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        print('SUBMISSION VIDEO:',target,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true')
    main(parser.parse_args().record)
