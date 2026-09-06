#!/usr/bin/env python3
"""CDP frame capturer: one headless-Chromium session, deterministic frames.

Page implements window.__advance() -> draws one frame. Each cycle:
  Runtime.evaluate('__advance()'); Page.captureScreenshot
Usage: cdp_capture.py <url> <outdir> <nframes> [skip] [png|jpeg]

Format: 'png' (default; lossless — REQUIRED for the framecheck regression
baselines) or 'jpeg' (~2x faster screenshots, q92 — visually lossless for
the MP4 path; use for production captures).
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import websocket


def json_get(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())


PORT = 9333
OUT = sys.argv[2]
N = int(sys.argv[3])
URL = sys.argv[1]
# positional [skip] [png|jpeg] — tolerant of either being omitted/elided:
# a non-integer 4th arg is treated as the format
SKIP = 0
FMT = 'png'
for a in sys.argv[4:]:
    if a in ('png', 'jpeg'):
        FMT = a
    else:
        try:
            SKIP = int(a)
        except ValueError:
            pass
assert FMT in ('png', 'jpeg'), 'format must be png or jpeg'
EXT = 'png' if FMT == 'png' else 'jpg'
os.makedirs(OUT, exist_ok=True)

P = subprocess.Popen([
    'chromium', '--headless=new', '--no-sandbox', '--disable-gpu',
    '--hide-scrollbars', '--force-device-scale-factor=1',
    '--window-size=900,1200', f'--remote-debugging-port={PORT}',
    '--remote-allow-origins=*', '--user-data-dir=/tmp/cdp_liquid', 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
ws = None
try:
    targets = None
    for _ in range(50):
        try:
            targets = json_get(f'http://127.0.0.1:{PORT}/json')
            break
        except Exception:
            time.sleep(0.2)
    page = next((x for x in targets if x.get('type') == 'page'), targets[0])
    u = page['webSocketDebuggerUrl'].replace('localhost', '127.0.0.1').replace('[::1]', '127.0.0.1')
    ws = websocket.create_connection(u, timeout=20)
    ws.settimeout(60)

    _msg_id = 0
    def cmd(method, params=None):
        global _msg_id
        _msg_id += 1
        ws.send(json.dumps({'id': _msg_id, 'method': method, 'params': params or {}}))
        while True:
            m = json.loads(ws.recv())
            if m.get('id') == _msg_id:
                if 'error' in m:
                    raise RuntimeError(f'{method}: {m["error"]}')
                return m.get('result', {})

    cmd('Page.enable')
    cmd('Runtime.enable')
    cmd('Emulation.setDeviceMetricsOverride',
        {'width': 900, 'height': 1200, 'deviceScaleFactor': 1, 'mobile': False})
    cmd('Page.navigate', {'url': URL})
    time.sleep(2.0)
    t0 = time.time()
    shot_params = {'format': FMT}
    if FMT == 'jpeg':
        shot_params['quality'] = 92
    for i in range(SKIP):
        cmd('Runtime.evaluate', {'expression': '__advance()'})
    for i in range(N):
        cmd('Runtime.evaluate', {'expression': '__advance()'})
        shot = cmd('Page.captureScreenshot', shot_params)
        with open(f'{OUT}/f{i:05d}.{EXT}', 'wb') as fh:
            fh.write(base64.b64decode(shot['data']))
        if i % 50 == 0:
            print(f'frame {i}/{N}  {int(time.time()-t0)}s', flush=True)
    print(f'done ({time.time()-t0:.0f}s)', flush=True)
finally:
    try:
        if ws:
            ws.close()
    except Exception:
        pass
    P.terminate()
