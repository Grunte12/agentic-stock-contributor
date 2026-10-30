"""Local evidence checkpoints. Never navigates the portal, uploads, or submits."""
import gzip
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT

PHASES = ('start', 'milestone', 'before-submit', 'user-submitted', 'after-submit', 'results', 'end', 'export')
MAX_AGE_SECONDS = 15 * 60


def _time(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('timestamps must include a timezone')
    return t


def _event(store, eid):
    row = store.db.execute('SELECT * FROM workflow_event WHERE event_id=?', (eid,)).fetchone()
    if not row:
        raise ValueError('unknown checkpoint id')
    return {**dict(row), 'data': json.loads(row['data'])}


def _observations(store, ids, now):
    if store.get_state('stop'):
        raise ValueError('STOP active; record a blocked milestone/end, do not create a successful checkpoint')
    found = {}
    for oid in ids:
        row = store.observation(oid)
        if not row or row['status'] != 'ok':
            raise ValueError('observation missing or not ok: '+oid)
        age = (now - _time(row['read_at'])).total_seconds()
        if age < 0 or age > MAX_AGE_SECONDS:
            raise ValueError('observation must be from the preceding 15 minutes: '+oid)
        raw = gzip.decompress((store.dir / row['raw_path']).read_bytes())
        if hashlib.sha256(raw).hexdigest() != row['payload_sha256']:
            raise ValueError('observation hash mismatch: '+oid)
        payload = json.loads(raw)
        if payload.get('page_state') or payload.get('http_status') in (403, 429):
            raise ValueError('blocked observation: '+oid)
        key = row['kind']
        if key == 'probe':
            key = {'https://contributor.stock.adobe.com/en/uploads': 'new', 'https://contributor.stock.adobe.com/en/uploads/review': 'review'}.get(row['url'])
        if key not in ('new', 'review', 'portfolio', 'outcomes') or key in found:
            raise ValueError('need one observation per supported page')
        named = payload.get('named', []) if key in ('new', 'review', 'portfolio') else payload.get('items', [])
        if any(not isinstance(x.get('asset_id'), int) or isinstance(x['asset_id'], bool) or x['asset_id'] <= 0 for x in named):
            raise ValueError('invalid asset identity: '+oid)
        names = {str(x['asset_id']): x.get('original_name') for x in named}
        if key in ('new', 'review'):
            total = payload.get('named_total')
            m = re.search(r'File types:\s*All\s*\((\d+)\)', payload.get('text', ''), re.I)
            if not isinstance(total, int) or not m or int(m[1]) != total or total != len(named) or len(names) != total or any(not n for n in names.values()):
                raise ValueError('incomplete file identities or count mismatch: '+oid)
            if key == 'review' and any(x.get('status') != 'state_waiting_validation' for x in named):
                raise ValueError('review rows must explicitly be waiting validation')
        elif key == 'portfolio':
            cards = payload.get('cards', [])
            ids_read = {str(c['asset_id']) for c in cards if c.get('asset_id')}
            total = store.db.execute('SELECT all_count FROM pf_overview WHERE obs_id=?', (oid,)).fetchone()
            if not total or total['all_count'] != len(ids_read):
                raise ValueError('portfolio identity coverage is incomplete')
            names = {i: names.get(i) for i in ids_read}
        elif payload.get('ctx_found') is not True or len(names) != len(named):
            raise ValueError('outcomes identity list not found or duplicated')
        found[key] = {'obs_id': oid, 'read_at': row['read_at'], 'payload_sha256': row['payload_sha256'], 'raw_path':str((store.dir / row['raw_path']).resolve()),
                      'names': names, 'statuses': {str(x['asset_id']): x.get('status') for x in named}}
        if key == 'new':
            m = re.search(r'\bSubmit\s+(\d+)\s+files?\b', payload.get('text', ''), re.I)
            found[key]['submit_count'] = int(m[1]) if m else None
        if key == 'outcomes':
            found[key]['causes'] = {str(x['asset_id']): x['cause_label'] or x['cause'] for x in store.db.execute('SELECT * FROM upload_outcome WHERE obs_id=?', (oid,))}
    return found


def record(store, phase, run=None, agent=None, session=None, before=None, obs=(), evidence=(), stage=None,
           user_confirmed=False, out=None, ws=None, now=None):
    ws = Path(ws or ROOT / 'workspace').resolve()
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    if phase not in PHASES:
        raise ValueError('unknown checkpoint phase')
    if phase == 'export':
        target = Path(out or '').resolve()
        if not target.is_relative_to(ws) or target.suffix != '.json':
            raise ValueError('export --out must be a JSON file under workspace/')
        rows = [dict(r) for r in store.db.execute('SELECT * FROM workflow_event ORDER BY recorded_at, rowid')]
        for r in rows:
            r['data'] = json.loads(r['data'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rows, indent=1, ensure_ascii=False)+'\n', encoding='utf-8')
        return {'ok': True, 'events': len(rows), 'artifact_path': str(target)}
    data = {'protocol_version': 1, 'timestamp_basis': 'recorded_at is logging time, never an inferred Submit or decision time'}
    if phase == 'start':
        if not run or not agent or len(run) > 120 or '\n' in run:
            raise ValueError('start requires --run and --agent')
        data['agent'] = agent
        data['workspace_hashes'] = {n: hashlib.sha256((ws / n).read_bytes()).hexdigest() for n in ('STATE.md', 'PLAYBOOK.md', 'LOG.md')}
        previous = store.db.execute("SELECT event_id FROM workflow_event WHERE phase='before-submit' AND run=? ORDER BY recorded_at DESC LIMIT 1", (run,)).fetchone()
        data['previous_before_id'] = previous['event_id'] if previous else None
        if before:
            selected = _event(store, before)
            if selected['phase'] != 'before-submit' or selected['run'] != run:
                raise ValueError('start --before must select a before-submit checkpoint from the same run')
            data['previous_before_id'] = before
    else:
        start = _event(store, session)
        if start['phase'] != 'start' or not 0 <= (now - _time(start['recorded_at'])).total_seconds() <= 12*3600:
            raise ValueError('need a start checkpoint from this session within 12 hours')
        run = start['run']
        if store.db.execute("SELECT 1 FROM workflow_event WHERE session_id=? AND phase='end'", (session,)).fetchone():
            raise ValueError('session has ended; start a new session')
    if phase == 'milestone':
        if not stage or not evidence:
            raise ValueError('milestone requires --stage and --evidence')
        data['stage'] = stage
        data['evidence'] = []
        for e in evidence:
            p = Path(e).resolve()
            if not p.is_relative_to(ws) or not p.is_file():
                raise ValueError('milestone evidence must be an existing file under workspace/')
            data['evidence'].append({'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()})
    if phase in ('before-submit', 'after-submit', 'results'):
        data['observations'] = snaps = _observations(store, obs, now)
        required = ('new', 'review') if phase != 'results' else ('portfolio', 'outcomes')
        if any(k not in snaps for k in required):
            raise ValueError('missing required observations: '+', '.join(required))
    if phase == 'before-submit':
        new = snaps['new']
        if not new['names'] or new['submit_count'] != len(new['names']):
            raise ValueError('New is not fully ready: Submit count must equal exact New identities')
        if set(new['names']) & set(snaps['review']['names']):
            raise ValueError('New and In review identities overlap')
        data['target_ids'] = sorted(new['names'])
        data['exact_submitted_at'] = None
    if phase == 'user-submitted':
        if not user_confirmed:
            raise ValueError('user-submitted requires explicit user confirmation (--user-confirmed)')
        data.update(user_reported_at=stamp, exact_submitted_at=None)
        if not before:
            data['target_scope'] = 'unknown: no before-submit identities retained'
    if phase in ('user-submitted', 'after-submit', 'results') and before:
        prior = _event(store, before)
        if prior['phase'] != 'before-submit' or prior['run'] != run:
            raise ValueError('need --before from a matching run before-submit checkpoint')
        own = store.db.execute("SELECT event_id FROM workflow_event WHERE phase='before-submit' AND session_id=? ORDER BY rowid DESC LIMIT 1", (session,)).fetchone()
        active = own['event_id'] if own else start['data']['previous_before_id']
        if before != active:
            raise ValueError('before id differs from the active session attempt; select an older attempt explicitly with start --before')
        if any(_time(s['read_at']) <= _time(prior['recorded_at']) for s in data.get('observations', {}).values()):
            raise ValueError('post-submit observations must be newer than the before-submit checkpoint')
        if phase == 'user-submitted':
            data['target_scope'] = 'identity-bound before-submit checkpoint'
        else:
            if phase == 'after-submit':
                reported = store.db.execute("SELECT recorded_at FROM workflow_event WHERE phase='user-submitted' AND before_id=? ORDER BY recorded_at DESC LIMIT 1", (before,)).fetchone()
                if not reported:
                    raise ValueError('record the explicit user Submit report before after-submit')
                if any(_time(s['read_at']) < _time(reported['recorded_at']) for s in snaps.values()):
                    raise ValueError('after-submit observations must follow the user report')
            target = set(prior['data']['target_ids'])
            labels = {'new':'new', 'review':'in_review', 'portfolio':'accepted', 'outcomes':'refused'}
            buckets = {labels[k]: sorted(target & set(s['names'])) for k, s in snaps.items()}
            flat = [i for rows in buckets.values() for i in rows]
            if len(flat) != len(set(flat)):
                raise ValueError('conflicting asset states across observations; re-observe before classifying')
            data['target_states'] = buckets
            data['unresolved_ids'] = sorted(target-set(flat))
    if phase == 'after-submit' and not before:
        reported = store.db.execute("SELECT recorded_at FROM workflow_event WHERE phase='user-submitted' AND session_id=? AND before_id IS NULL ORDER BY recorded_at DESC LIMIT 1", (session,)).fetchone()
        if not reported or any(_time(s['read_at']) < _time(reported['recorded_at']) for s in snaps.values()):
            raise ValueError('record the unlinked user report before taking after-submit observations')
        data['observed_counts'] = {'observed_new':len(snaps['new']['names']), 'observed_in_review':len(snaps['review']['names'])}
        data['coverage'] = 'Unknown attempted target identities; observed counts do not prove submission or identify newly submitted files.'
    if phase == 'results' and not before:
        if set(snaps['portfolio']['names']) & set(snaps['outcomes']['names']):
            raise ValueError('accepted/refused snapshots conflict')
        data['observed_counts'] = {k:len(s['names']) for k,s in snaps.items()}
        data['coverage'] = 'Observed identities only; missing IDs are not pending. Complete coverage required for account-wide rates.'
    eid = uuid.uuid4().hex
    session = eid if phase == 'start' else session
    store.db.execute('INSERT INTO workflow_event VALUES(?,?,?,?,?,?,?)', (eid, stamp, phase, run, session, before, json.dumps(data, ensure_ascii=False)))
    counts = {k: len(v) for k, v in data.get('target_states', {}).items()} or data.get('observed_counts', {})
    return {'ok': True, 'event_id': eid, 'session_id': session, 'phase': phase, 'recorded_at': stamp,
            'run': run, 'target_count': len(data.get('target_ids', [])) if phase == 'before-submit' else None,
            'counts': counts, 'unresolved': len(data['unresolved_ids']) if 'unresolved_ids' in data else None,
            'previous_before_id': data.get('previous_before_id'), 'exact_submitted_at': None}
