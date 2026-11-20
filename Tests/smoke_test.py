"""
CFA study site — automatic safety checks (no accounts, no internet, nothing is changed in your real data).

Run:   pip install playwright && playwright install chromium
       python tests/smoke_test.py            (from the folder that holds index.html)

It opens the site in a real browser with a pretend cloud and checks the things that must never break:
every screen opens · Complete / Readiness numbers · two devices do not erase each other · old versions cannot overwrite new data · dialogs.
Exit code 0 = all good, 1 = something broke.
"""
import json, os, sys, threading, time, http.server, socketserver, functools
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..'))
INDEX = os.path.join(ROOT, 'index.html')

# ---------------- a tiny web server; /__t.html = index.html plus a small door for the tests ----------------
def test_copy():
    s = open(INDEX, encoding='utf8').read(); i = s.find('const kv = {'); b = s.find('</script>', i)
    return (s[:b] + "\ntry{window.__t={kv,local,route,flush,pull,db};}catch(e){console.error('inj',e)}\n" + s[b:]).encode('utf8')
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.split('?')[0] == '/__t.html':
            body = test_copy(); self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
        return super().do_GET()
socketserver.TCPServer.allow_reuse_address = True
SRV = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(H, directory=ROOT)); PORT = SRV.server_address[1]
threading.Thread(target=SRV.serve_forever, daemon=True).start()

# ---------------- a pretend cloud (one table "items") ----------------
CLOUD = {}
def cloud_call(s):
    q = json.loads(s); T = CLOUD
    def ok(r):
        return all((r.get(c) == v) if k == 'eq' else (r.get(c) in v) for k, c, v in q['f'])
    if q['op'] == 'upsert':
        for r in q['rows']: T[(r['store'], str(r['id']))] = r
        return json.dumps({'data': None, 'error': None})
    if q['op'] == 'delete':
        for k, r in list(T.items()):
            if ok(r): del T[k]
        return json.dumps({'data': None, 'error': None})
    sel = [r for r in T.values() if ok(r)]
    for c in reversed(q['ord']): sel.sort(key=lambda r: r.get(c))
    n = len(sel)
    if q['rng']: sel = sel[q['rng'][0]:q['rng'][1] + 1]
    if q['cols'] != '*':
        cs = [c.strip() for c in q['cols'].split(',')]; sel = [{c: r.get(c) for c in cs} for r in sel]
    return json.dumps({'data': sel, 'error': None, 'count': n if q['count'] else None})
MOCK = """
window.__SB_MOCK=function(){
  const call=(q)=>window.__cloudCall(JSON.stringify(q)).then(r=>JSON.parse(r));
  const mk=()=>{const q={op:'select',cols:'*',f:[],ord:[],rng:null,count:false,rows:null};
    const b={select(c,o){if(q.op==='select'){q.cols=c||'*';if(o&&o.count)q.count=true;}return b;},eq(c,v){q.f.push(['eq',c,v]);return b;},in(c,v){q.f.push(['in',c,v]);return b;},order(c){q.ord.push(c);return b;},range(a,z){q.rng=[a,z];return b;},upsert(rows){q.op='upsert';q.rows=rows;return b;},delete(){q.op='delete';return b;},then(res,rej){return call(q).then(res,rej);}};return b;};
  const chain=()=>new Proxy(function(){},{get:(_,k)=>k==='then'?(res=>res({data:[],error:null,count:0})):chain(),apply:()=>chain()});
  const session={access_token:'x',user:{id:'u-test',email:'t@t.t'}};
  return {from:(t)=>t==='items'?mk():chain(),storage:{from:()=>chain()},rpc:()=>chain(),channel:()=>chain(),removeChannel(){},auth:{getSession:async()=>({data:{session},error:null}),onAuthStateChange:()=>({data:{subscription:{unsubscribe(){}}}}),signOut:async()=>({error:null}),getUser:async()=>({data:{user:session.user},error:null})}};
};"""
class Dev:
    def __init__(self, p=None, w=1300, h=850):
        self.b = PW.chromium.launch(args=['--no-sandbox'], executable_path=os.environ.get('CHROME_PATH') or None)
        self.c = self.b.new_context(viewport={'width': w, 'height': h}, service_workers='block')
        self.c.expose_function('__cloudCall', cloud_call); self.c.add_init_script(MOCK)
        self.pg = self.c.new_page(); self.errs = []
        self.pg.on('pageerror', lambda e: self.errs.append(str(e)[:200]))
        self.pg.goto(f'http://127.0.0.1:{PORT}/__t.html'); self.pg.wait_for_timeout(3000)
    def kvget(self, k, d='null'): return json.loads(self.pg.evaluate("(async k=>JSON.stringify(await __t.kv.get(k,%s)))" % d, k))
    def kvset(self, k, v): self.pg.evaluate("async([k,v])=>{await __t.kv.set(k,v)}", [k, v]); self.pg.wait_for_timeout(500)
    def sync(self): self.pg.evaluate("__t.flush()"); self.pg.wait_for_timeout(1200)
    def go(self, h, w=900): self.pg.evaluate("h=>{location.hash=h}", h); self.pg.wait_for_timeout(w)
    def reload(self): self.pg.reload(); self.pg.wait_for_timeout(3200)
    def text(self, sel): return self.pg.locator(sel).inner_text().replace('\n', ' | ')
    def close(self): self.b.close()

PW = sync_playwright().start()
RESULTS = []
def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail)); print(('PASS  ' if cond else 'FAIL  ') + name + (('   ' + detail) if (detail and not cond) else ''))

ROUTES = ['#/', '#/progress', '#/study', '#/study/fsa', '#/study/fsa/1/map', '#/study/fsa/1/schweser', '#/study/fsa/1/cards', '#/study/fsa/1/ai', '#/study/fsa/1/mohd', '#/study/fsa/1/qbank', '#/study/fsa/1/perf', '#/study/econ', '#/qbank', '#/qbank/mocks', '#/qbank/stats', '#/plan', '#/search', '#/cards', '#/library', '#/summary', '#/formulas', '#/settings', '#/health', '#/errors', '#/quick', '#/weekly', '#/lecnotes', '#/remember', '#/calc', '#/ethics', '#/examday', '#/traps', '#/explore', '#/layout']
def syn_questions(n):
    L = ['27.a', '27.b', '27.c', '27.d', '27.e']
    return [{'id': f'SYN-{i}', 'ref': f'S #{i}', 'qno': i, 'm': 'fsa-1', 'src': 'cur', 'los': L[i % 5], 'scope': 'In module', 'q': f'Question {i}?', 'o': ['A', 'B', 'C'], 'a': i % 3, 'x': 'x'} for i in range(n)]

def t_routes():
    A = Dev(); empty = []
    for r in ROUTES:
        A.go(r, 600)
        if A.pg.evaluate("(document.querySelector('#view')||document.body).innerText.length") < 30: empty.append(r)
    check('every screen opens (%d screens)' % len(ROUTES), not empty, 'empty: %s' % empty)
    check('no JavaScript errors while opening them', not A.errs, str(A.errs[:3])); A.close()

def t_complete_and_readiness():
    A = Dev(); A.go('#/study/fsa/1/map', 2000)
    head0 = A.text('#mTrack')
    A.kvset('lessonSteps', {'fsa-1': {k: 1 for k in ['map', 'schweser', 'curriculum', 'xtra', 'conf', 'cards', 'ai', 'mohd']}}); A.go('#/study/fsa/1/cards', 1800)
    check('Complete reaches 100 % when every part that exists is done (no video / no questions loaded = left out)', '100% | Complete' in A.text('#mTrack'), A.text('#mTrack')[:160])
    qs = syn_questions(150); A.kvset('qbank:fsa-1', qs); now = int(time.time() * 1000)
    st = {q['id']: {'n': 2, 'c': 2, 'last': True, 'ts': now - 864e5 * 10, 'first': now - 864e5 * 20, 'hist': [{'t': now - 864e5 * 20, 'ok': True, 'cf': 'sure'}, {'t': now - 864e5 * 10, 'ok': True, 'cf': 'sure'}], 'box': 2, 'due': now} for q in qs[:30]}
    A.kvset('qstats', st); A.kvset('rdFull', True); A.reload(); A.go('#/study/fsa/1/map', 2000)
    import re
    m = re.search(r'(\d+)% \| Readiness', A.text('#mTrack')); full = int(m.group(1)) if m else -1
    A.kvset('rdFull', False); A.reload(); A.go('#/study/fsa/1/map', 2000)
    m = re.search(r'(\d+)% \| Readiness', A.text('#mTrack')); old = int(m.group(1)) if m else -1
    check('Readiness counts unanswered questions (30 of 150 answered, all right → well below 70 %)', 40 <= full <= 60, 'got %s' % full)
    check('the “answered only” option still shows the higher figure', old > full, 'full=%s old=%s' % (full, old)); A.close()

def t_two_devices():
    A = Dev(); B = Dev()
    cases = [('mockRes', {'m1': {'score': 61}}, {'m2': {'score': 72}}, ['"m1"', '"m2"']),
             ('plan', {'cfg': {}, 'tasks': [{'id': 't1', 'done': True}], 'created': 1}, {'cfg': {}, 'tasks': [{'id': 't2', 'done': False}], 'created': 1}, ['"t1"', '"t2"']),
             ('cards:fsa-1', [{'id': 'c1', 'box': 1, 'ts': 100}], [{'id': 'c2', 'box': 2, 'ts': 200}], ['"c1"', '"c2"']),
             ('modTrack', {'fsa-1': {'videos': [{'id': 'a1', 'name': 'x'}]}}, {'fsa-1': {'videos': [{'id': 'b1', 'name': 'y'}]}}, ['"a1"', '"b1"'])]
    for key, va, vb, need in cases:
        A.kvset(key, va); A.sync(); B.kvset(key, vb); B.sync()
        keep = json.dumps(CLOUD.get(('kv', key), {}).get('data'), sort_keys=True)
        check('two devices keep each other\'s changes: ' + key, all(x in keep for x in need), keep[:120])
    A.kvset('plan', {'cfg': {}, 'tasks': [{'id': 't1', 'done': False}, {'id': 't2', 'done': False}, {'id': 't3', 'done': False}], 'created': 1}); A.sync(); B.reload()
    pa = A.kvget('plan'); pa['tasks'] = [t for t in pa['tasks'] if t['id'] != 't1']; A.kvset('plan', pa)
    pb = B.kvget('plan'); [t.update(done=True) for t in pb['tasks'] if t['id'] == 't3']; B.kvset('plan', pb); A.sync(); B.sync()
    tasks = CLOUD[('kv', 'plan')]['data']['tasks']
    check('a deletion on one device and a tick on the other both survive', [t['id'] for t in tasks] == ['t2', 't3'] and tasks[1]['done'] is True, str(tasks))
    CLOUD[('kv', 'schemaVer')] = {'user_id': 'u-test', 'store': 'kv', 'id': 'schemaVer', 'data': 99, 'updated_at': '2030-01-01T00:00:00Z'}
    B.pg.evaluate("localStorage.removeItem('lastFullPull')"); B.reload()
    check('a site version older than the data shows the Update bar', B.pg.locator('#schemaBar').count() == 1)
    B.kvset('examChk', {'zz': True}); B.sync(); check('…and stops uploading', ('kv', 'examChk') not in CLOUD or 'zz' not in json.dumps(CLOUD[('kv', 'examChk')]['data']))
    check('no JavaScript errors in the two-device run', not (A.errs + B.errs), str((A.errs + B.errs)[:3])); A.close(); B.close()

def t_dialogs():
    A = Dev()
    A.kvset('modTrack', {'fsa-1': {'videos': [{'id': 'v1', 'name': 'L1', 'url': 'https://example.com/a.mp4', 'src': 'Other'}]}}); A.go('#/study/fsa/1/map', 1800)
    A.pg.locator('.lp-gm').first.click(); A.pg.wait_for_timeout(1000); A.pg.locator('[data-del="0"]').click(); A.pg.wait_for_timeout(400)
    check('delete asks first, in a page dialog (not the browser box)', A.pg.locator('.modal-bg[role=alertdialog]').count() == 1)
    A.pg.keyboard.press('Escape'); A.pg.wait_for_timeout(300)
    check('Esc cancels: nothing deleted', len(A.kvget('modTrack')['fsa-1']['videos']) == 1)
    A.pg.locator('[data-del="0"]').click(); A.pg.wait_for_timeout(300); A.pg.locator('.modal-bg[role=alertdialog] [data-d=ok]').click(); A.pg.wait_for_timeout(600)
    check('OK deletes', len(A.kvget('modTrack')['fsa-1']['videos']) == 0); A.close()

if __name__ == '__main__':
    t0 = time.time()
    for fn in (t_routes, t_complete_and_readiness, t_two_devices, t_dialogs):
        try: fn()
        except Exception as e: check(fn.__name__ + ' ran without crashing', False, repr(e)[:200])
    bad = [r for r in RESULTS if not r[1]]
    print('\n%d checks · %d failed · %.0f s' % (len(RESULTS), len(bad), time.time() - t0)); sys.exit(1 if bad else 0)
