#!/usr/bin/env python3
"""Offline host: serves the extracted 1.61.7 assets and replays a recorded
game-server session, so the client boots with no network at all."""
import asyncio, json, logging, os, random, time
import pathlib
from pathlib import Path
from aiohttp import web, WSMsgType

ROOT = Path(__file__).resolve().parent
ASSETS = pathlib.Path(os.environ.get('ASSETS_DIR', ROOT / 'assets')).resolve()
PATCHED = ROOT / 'patched'
V1633 = ROOT / '1.63.3'
REPLAY = ROOT / 'replay'
PORT = 18371

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('local')

# ---------------------------------------------------------------- replay data
SCENARIO = {}
for path in sorted(REPLAY.glob('*.bin')):
    cmd = int(path.name[:5])
    SCENARIO.setdefault(cmd, []).append(path.read_bytes())

CLIENT_TO_SERVER = {1: 10001, 708: 10004, 117: 10117, 124: 10124, 126: 10126, 116: 10116, 16: 10017}
STATS = {'connections': [], 'api': []}

SESSION = {
    'api_url': f'http://127.0.0.1:{PORT}/api',
    'api_id': '145085', 'api_settings': '8479',
    'viewer_id': '145085', 'viewer_type': '2',
    'sid': 'local', 'secret': 'local', 'access_token': '',
    'user_id': '145085', 'group_id': '0', 'is_app_user': '1',
    'auth_key': '', 'language': '0', 'parent_language': '0',
    'ad_info': 'dasss==', 'is_secure': '0', 'ads_app_id': 'local',
    'referrer': 'unknown', 'lc_name': 'local', 'hash': '',
    '_social_type': 'vkontakte', '_app_key': 'local', '_app_key2': 'local',
    '_app_link': f'http://127.0.0.1:{PORT}/', '_club_link': f'http://127.0.0.1:{PORT}/',
    '_app_mode': 'local', '_upload_url': f'http://127.0.0.1:{PORT}/upload',
}
PROFILE = {
    'id': 145085, 'uid': '145085', 'user_id': '145085',
    'first_name': 'LocalTest', 'last_name': '', 'nickname': '', 'sex': 1,
    'bdate': '23.11.2000', 'country': 1, 'city': 1, 'timezone': 1,
    'photo': f'http://127.0.0.1:{PORT}/avatar.png',
    'photo_50': f'http://127.0.0.1:{PORT}/avatar.png',
    'photo_100': f'http://127.0.0.1:{PORT}/avatar.png',
    'photo_200': f'http://127.0.0.1:{PORT}/avatar.png',
}

# ---------------------------------------------------------------------- http
async def index(request):
    return web.FileResponse(ROOT / 'index.html')

async def session(request):
    SESSION['auth_key'] = ''.join(random.choice('0123456789abcdef') for _ in range(32))
    return web.json_response(SESSION, headers={'Cache-Control': 'no-store'})

async def api(request):
    pairs = list(request.query.items())
    if request.method == 'POST':
        pairs += list((await request.post()).items())
    method = next((v for k, v in pairs if k == 'method'), '')
    if method in ('users.get', 'getProfiles'):
        body = {'response': [PROFILE]}
    elif method == 'getAppFriends':
        body = {'response': []}
    elif method == 'getUserSettings':
        body = {'response': 2371351}
    else:
        body = {'response': []}
    STATS['api'].append({'method': method, 'args': sorted(k for k, _ in pairs)})
    log.info('api %s -> %s', method, str(body)[:100])
    return web.json_response(body, headers={'Cache-Control': 'no-store'})

async def status(request):
    return web.json_response({'scenario': {k: [len(f) for f in v] for k, v in SCENARIO.items()},
                              'connections': STATS['connections'][-8:], 'api': STATS['api'][-8:]})

async def static_from(base, req, name, ctype=None):
    path = (base / name).resolve()
    if base.resolve() not in path.parents or not path.is_file():
        raise web.HTTPNotFound()
    ct = ctype or ('application/x-shockwave-flash' if name.endswith('.swf') else None)
    return web.Response(body=path.read_bytes(), content_type=ct,
                        headers={'Cache-Control': 'no-store, no-cache, must-revalidate'})

async def game_asset(request):
    name = request.match_info['name']
    if name in ('Wormix.swf', 'preloader_251.swf') and (PATCHED / name).is_file():
        return await static_from(PATCHED, request, name)
    return await static_from(ASSETS, request, name)

async def v1633_asset(request):
    return await static_from(V1633, request, request.match_info['name'])


async def storage_asset(request):
    return await static_from(ASSETS / 'storage', request, request.match_info['name'])

async def avatar(request):
    path = ROOT / 'avatar.png'
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)

# -------------------------------------------------------------------- socket
def frames_of(data):
    """Split a client byte stream into complete 7-byte-header frames."""
    out, pos = [], 0
    while len(data) - pos >= 7:
        length = int.from_bytes(data[pos + 3:pos + 7], 'big') & 0x3FFFFFFF
        if length > 8 << 20:
            break
        if len(data) - pos - 7 < length:
            break
        out.append(data[pos:pos + 7 + length])
        pos += 7 + length
    return out, data[pos:]

async def socket_replay(request):
    port = int(request.match_info['port'])
    rec = {'port': port, 'client': [], 'server': [], 'state': 'open', 't': time.time()}
    STATS['connections'].append(rec)
    ws = web.WebSocketResponse(max_msg_size=16 << 20)
    await ws.prepare(request)
    buf = b''
    async for msg in ws:
        if msg.type != WSMsgType.BINARY:
            continue
        frames, buf = frames_of(buf + msg.data)
        for frame in frames:
            cmd = int.from_bytes(frame[1:3], 'big') & 0x7FFF
            rec['client'].append({'command': cmd, 'bytes': len(frame)})
            log.info('<- %s (%d B)', cmd, len(frame))
            target = CLIENT_TO_SERVER.get(cmd)
            if target is None or target not in SCENARIO:
                continue
            reply = SCENARIO[target][0]
            rec['server'].append({'command': target, 'bytes': len(reply)})
            await ws.send_bytes(reply)
    rec['state'] = 'closed'
    return ws

# ---------------------------------------------------------------------- app
app = web.Application()
app.router.add_get('/', index)
app.router.add_get('/session', session)
app.router.add_route('*', '/api', api)
app.router.add_get('/status', status)
app.router.add_get('/avatar.png', avatar)
app.router.add_get(r'/socket/{port:\d+}', socket_replay)
app.router.add_get(r'/game/{name:.+}', game_asset)
app.router.add_get(r'/v1633/{name:.+}', v1633_asset)
app.router.add_get(r'/storage/{name:.+}', storage_asset)
app.router.add_static('/ruffle/', ROOT / 'ruffle', show_index=False)

@web.middleware
async def logreq(request, handler):
    try:
        resp = await handler(request)
    except web.HTTPException as exc:
        log.info('%s %s -> %s', request.method, request.path_qs[:160], exc.status)
        raise
    log.info('%s %s -> %s', request.method, request.path_qs[:160], resp.status)
    return resp


app.middlewares.append(logreq)

if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=PORT, access_log=None)
