import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers
from adobe_stock_analytics import checkpoints as C, workspace as W
from adobe_stock_analytics.store import Store


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.ws = self.root / 'workspace'
        W.init(self.ws)
        self.now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
        self.store = Store(self.root / 'data', now=lambda:self.now.isoformat().replace('+00:00','Z'))
        self.sid = self.record('start',run='R1',agent='test')['session_id']

    def record(self,phase,**kwargs):
        return C.record(self.store,phase,ws=self.ws,now=self.now,**kwargs)

    def tick(self,seconds=1):
        self.now += timedelta(seconds=seconds)

    def probe(self,page,ids,submit=None):
        rows=[{'asset_id':i,'original_name':str(i)+'.jpg','status':'state_waiting_validation' if page=='review' else 'new'} for i in ids]
        p={'named':rows,'named_total':len(rows),'page_state':None,'http_status':200,
           'text':f"File types: All ({len(rows)}) Submit {len(rows) if submit is None else submit} files"}
        return self.store.add_observation('probe','https://contributor.stock.adobe.com/en/uploads'+('/review' if page=='review' else ''),{},p,{'status':'ok','parser_version':'p1'})

    def before(self):
        self.tick()
        ids=[self.probe('new',[1,2]),self.probe('review',[9])]
        self.tick()
        return self.record('before-submit',session=self.sid,obs=ids)['event_id']

    def test_partial_submit_matches_ids_and_excludes_previous_review(self):
        bid=self.before()
        self.tick()
        report=self.record('user-submitted',session=self.sid,before=bid,user_confirmed=True)
        self.assertIsNone(report['exact_submitted_at'])
        self.tick()
        ids=[self.probe('new',[2]),self.probe('review',[9,1])]
        self.tick()
        out=self.record('after-submit',session=self.sid,before=bid,obs=ids)
        self.assertEqual(out['counts'],{'new':1,'in_review':1})
        self.assertEqual(out['unresolved'],0)
        self.record('end',session=self.sid)
        with self.assertRaisesRegex(ValueError,'ended'):
            self.record('milestone',session=self.sid,stage='qc',evidence=[])

    def test_missing_from_new_does_not_mean_review(self):
        bid=self.before()
        self.tick();self.record('user-submitted',session=self.sid,before=bid,user_confirmed=True)
        self.tick();ids=[self.probe('new',[]),self.probe('review',[9])]
        self.tick();out=self.record('after-submit',session=self.sid,before=bid,obs=ids)
        self.assertEqual(out['counts'],{'new':0,'in_review':0})
        self.assertEqual(out['unresolved'],2)

    def test_readiness_requires_all_new_to_be_ready(self):
        self.tick();ids=[self.probe('new',[1,2],submit=1),self.probe('review',[])]
        with self.assertRaisesRegex(ValueError,'not fully ready'):
            self.record('before-submit',session=self.sid,obs=ids)

    def test_missing_or_duplicate_identity_is_rejected(self):
        self.tick();ids=[self.probe('new',[1,1]),self.probe('review',[])]
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.record('before-submit',session=self.sid,obs=ids)

    def test_before_requires_both_pages_and_no_overlap(self):
        self.tick();new=self.probe('new',[1])
        with self.assertRaisesRegex(ValueError,'missing required'):
            self.record('before-submit',session=self.sid,obs=[new])
        with self.assertRaisesRegex(ValueError,'overlap'):
            self.record('before-submit',session=self.sid,obs=[new,self.probe('review',[1])])

    def test_observations_must_be_fresh_and_post_after_pre(self):
        bid=self.before()
        self.record('user-submitted',session=self.sid,before=bid,user_confirmed=True)
        old=[self.probe('new',[1,2]),self.probe('review',[9])]
        with self.assertRaisesRegex(ValueError,'newer'):
            self.record('after-submit',session=self.sid,before=bid,obs=old)
        self.tick(901)
        with self.assertRaisesRegex(ValueError,'15 minutes'):
            self.record('after-submit',session=self.sid,before=bid,obs=old)

    def test_tampered_raw_and_active_stop_are_refused(self):
        self.tick();oid=self.probe('new',[1]);review=self.probe('review',[])
        row=self.store.observation(oid)
        (self.store.dir/row['raw_path']).write_bytes(gzip.compress(b'{}'))
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            self.record('before-submit',session=self.sid,obs=[oid,review])
        self.store.set_state('stop',{'reason':'captcha'})
        with self.assertRaisesRegex(ValueError,'STOP'):
            self.record('before-submit',session=self.sid,obs=[review])
        self.assertTrue(self.record('end',session=self.sid)['ok'])

    def test_session_and_explicit_user_report_are_required(self):
        with self.assertRaisesRegex(ValueError,'unknown checkpoint'):
            self.record('before-submit',session='missing')
        bid=self.before()
        with self.assertRaisesRegex(ValueError,'explicit user confirmation'):
            self.record('user-submitted',session=self.sid,before=bid)
        self.tick();ids=[self.probe('new',[]),self.probe('review',[1,2,9])]
        self.tick()
        with self.assertRaisesRegex(ValueError,'explicit user Submit report'):
            self.record('after-submit',session=self.sid,before=bid,obs=ids)

    def test_new_session_can_resume_same_run_but_not_other_run(self):
        bid=self.before()
        same=self.record('start',run='R1',agent='other')
        self.assertEqual(same['previous_before_id'],bid)
        self.assertTrue(self.record('user-submitted',session=same['session_id'],before=bid,user_confirmed=True)['ok'])
        other=self.record('start',run='R2',agent='other')['session_id']
        with self.assertRaisesRegex(ValueError,'matching run'):
            self.record('user-submitted',session=other,before=bid,user_confirmed=True)

    def test_attempt_cannot_silently_change_to_an_older_before(self):
        older=self.before();newer=self.before()
        resumed=self.record('start',run='R1',agent='other')
        self.assertEqual(resumed['previous_before_id'],newer)
        with self.assertRaisesRegex(ValueError,'active session attempt'):
            self.record('user-submitted',session=resumed['session_id'],before=older,user_confirmed=True)
        historical=self.record('start',run='R1',agent='other',before=older)
        self.assertEqual(historical['previous_before_id'],older)
        self.assertTrue(self.record('user-submitted',session=historical['session_id'],before=older,user_confirmed=True)['ok'])

    def test_unlinked_legacy_report_never_infers_new_submissions(self):
        self.record('user-submitted',session=self.sid,user_confirmed=True)
        self.tick();ids=[self.probe('new',[]),self.probe('review',[9])]
        self.tick();out=self.record('after-submit',session=self.sid,obs=ids)
        self.assertEqual(out['counts'],{'observed_new':0,'observed_in_review':1})
        self.assertIsNone(out['unresolved'])
        self.assertIsNone(out['target_count'])
        saved=C._event(self.store,out['event_id'])
        self.assertNotIn('target_states',saved['data'])

    def test_expired_session_and_private_evidence(self):
        self.tick(12*3600+1)
        with self.assertRaisesRegex(ValueError,'12 hours'):
            self.record('end',session=self.sid)
        sid=self.record('start',run='R1',agent='test')['session_id']
        ev=self.ws/'proof.json';ev.write_text('{"ok":true}')
        self.assertTrue(self.record('milestone',session=sid,stage='package',evidence=[str(ev)])['ok'])
        outside=self.root/'token';outside.write_text('private')
        with self.assertRaisesRegex(ValueError,'under workspace'):
            self.record('milestone',session=sid,stage='package',evidence=[str(outside)])

    def test_results_keep_first_seen_separate_from_decision_time(self):
        bid=self.before();self.tick()
        p={'cards':[{'asset_id':1}],'named':[{'asset_id':1,'original_name':'1.jpg'}]}
        accepted=self.store.add_observation('portfolio','https://contributor.stock.adobe.com/en/portfolio',{},p,
            {'status':'ok','parser_version':'p1','overview_downloads':0,'overview_earnings':0,'all_count':1,'time_frame':'year','sort_text':'date',
             'rows':[{'asset_id':1,'downloads':0}]})
        refused=self.store.add_observation('outcomes','https://contributor.stock.adobe.com/en/uploads/rejected',{},
            {'ctx_found':True,'items':[]},{'status':'ok','parser_version':'p1','rows':[]})
        self.tick();out=self.record('results',session=self.sid,before=bid,obs=[accepted,refused])
        self.assertEqual(out['counts'],{'accepted':1,'refused':0})
        self.assertEqual(out['unresolved'],1)
        target=self.ws/'outcomes'/'timeline.json'
        exported=self.record('export',out=str(target))
        records=json.loads(target.read_text())
        self.assertEqual(exported['events'],len(records))
        self.assertEqual(records[-1]['data']['observations']['portfolio']['read_at'],'2026-10-28T12:00:03Z')
        self.assertNotIn('decision_at',records[-1]['data'])
        self.assertIsNone(records[1]['data']['exact_submitted_at'])
        with self.assertRaisesRegex(ValueError,'under workspace'):
            self.record('export',out=str(self.root/'outside.json'))

    def test_refusal_preserves_adobe_cause_in_timeline(self):
        bid=self.before();self.tick()
        accepted=self.store.add_observation('portfolio','https://contributor.stock.adobe.com/en/portfolio',{},
            {'cards':[],'named':[]},{'status':'ok','parser_version':'p1','overview_downloads':0,'overview_earnings':0,'all_count':0,'time_frame':'year','sort_text':'date','rows':[]})
        refused=self.store.add_observation('outcomes','https://contributor.stock.adobe.com/en/uploads/rejected',{},
            {'ctx_found':True,'items':[{'asset_id':2,'original_name':'2.jpg','status':'state_refused'}]},
            {'status':'ok','parser_version':'p1','rows':[{'asset_id':2,'original_name':'2.jpg','status':'state_refused','created_ms':1,'width':4000,'height':3000,'cause':9,'cause_label':'Tech problems','outcome_class':'quality'}]})
        self.tick();out=self.record('results',session=self.sid,before=bid,obs=[accepted,refused])
        self.assertEqual(out['counts'],{'accepted':0,'refused':1})
        saved=C._event(self.store,out['event_id'])
        self.assertEqual(saved['data']['observations']['outcomes']['causes'],{'2':'Tech problems'})
        self.assertEqual(out['unresolved'],1)
