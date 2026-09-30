import concurrent.futures
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from flowcheck.engine import ValidationError, parse_export, reconcile
from flowcheck.store import Store
from server import handler_for

ROOT = Path(__file__).resolve().parents[1]
WMS = (ROOT/'samples/warehouse.csv').read_text()
TMS = (ROOT/'samples/transport.csv').read_text()
FIXED = (ROOT/'samples/transport-fixed.csv').read_text()
HEADER = 'record_id,shipment_id,sku,quantity\n'


class RulesTests(unittest.TestCase):
    def test_seeded_discrepancies_and_split_aggregation(self):
        result = reconcile(parse_export(WMS,'WMS'), parse_export(TMS,'TMS'))
        self.assertEqual(result['summary']['matched_keys'], 6)
        self.assertEqual(result['summary']['line_keys'], 9)
        self.assertEqual(result['summary']['warehouse_units'], 540)
        self.assertEqual(result['summary']['transport_units'], 525)
        self.assertEqual({i['rule'] for i in result['issues']}, {'MISSING_IN_TMS','MISSING_IN_WMS','QUANTITY_MISMATCH'})
        mismatch = next(i for i in result['issues'] if i['rule']=='QUANTITY_MISMATCH')
        self.assertEqual(mismatch['delta'], -8)

    def test_corrected_exports_all_match(self):
        result = reconcile(parse_export(WMS,'WMS'),parse_export(FIXED,'TMS'))
        self.assertEqual(result['summary']['matched_keys'],8)
        self.assertEqual(result['issues'],[])

    def test_duplicate_not_silently_double_counted(self):
        with self.assertRaisesRegex(ValidationError,'duplicate'):
            parse_export(HEADER+'A,S,K,1\nA,S,K,1\n','WMS')

    def test_invalid_quantities_rejected(self):
        for qty in ['0','-1','2.5','NaN','1000001','1e2','']:
            with self.subTest(qty=qty), self.assertRaises(ValidationError):
                parse_export(HEADER+f'A,S,K,{qty}\n','WMS')

    def test_invalid_structure_and_formula_identifiers_rejected(self):
        for text in ['',HEADER,'record_id,shipment_id,sku\nA,S,K\n',HEADER+'A,S,K,1,extra\n',HEADER+'A,S,K\n',HEADER+'A,=SUM(A1),K,1\n']:
            with self.subTest(text=text),self.assertRaises(ValidationError):
                parse_export(text,'WMS')

    def test_bom_and_trim_supported(self):
        rows=parse_export('\ufeff'+HEADER+' A ,S,K,2\n','WMS')
        self.assertEqual(rows[0]['record_id'],'A')

    def test_shipment_and_sku_are_composite_key(self):
        w=parse_export(HEADER+'A,S,K1,2\nB,S,K2,3\n','WMS')
        t=parse_export(HEADER+'C,S,K1,5\n','TMS')
        self.assertEqual(len(reconcile(w,t)['issues']),2)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.db')

    def tearDown(self):
        self.tmp.cleanup()

    def test_idempotency_ignores_row_order_and_label(self):
        first=self.store.run('Original',WMS,TMS)
        reordered=HEADER+'\n'.join(reversed(WMS.splitlines()[1:]))+'\n'
        second=self.store.run('Different label',reordered,TMS)
        self.assertEqual(first['id'],second['id'])
        self.assertTrue(second['reused'])
        self.assertEqual(second['label'],'Original')
        self.assertEqual(len(second['audit']),2)
        self.assertEqual(len(self.store.history()),1)

    def test_correction_preserves_original_and_source_rows(self):
        before=self.store.run('Original',WMS,TMS)
        after=self.store.run('Corrected',WMS,FIXED)
        self.assertNotEqual(before['id'],after['id'])
        self.assertEqual(self.store.get(before['id'])['summary']['exception_keys'],3)
        self.assertEqual(after['summary']['exception_keys'],0)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM source_records WHERE run_id=?',(before['id'],)).fetchone()[0],17)

    def test_invalid_batch_writes_nothing(self):
        with self.assertRaises(ValidationError):
            self.store.run('Bad',WMS,TMS+'T001,S,K,1\n')
        self.assertEqual(self.store.history(),[])

    def test_simultaneous_retries_create_one_run(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.store.run('Retry',WMS,TMS),range(4)))
        self.assertEqual(len({r['id'] for r in results}),1)
        self.assertEqual(len(self.store.history()),1)


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(Store(Path(self.tmp.name)/'api.db')))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def post(self,payload,origin=None):
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        return urlopen(Request(self.base+'/api/runs',json.dumps(payload).encode(),headers))

    def test_complete_api_flow_and_csv_export(self):
        with self.post(dict(label='Test',warehouse=WMS,transport=TMS)) as response:
            self.assertEqual(response.status,201)
            run=json.load(response)
        with urlopen(self.base+f"/api/runs/{run['id']}/export") as response:
            csv_text=response.read().decode()
            self.assertIn('QUANTITY_MISMATCH',csv_text)
            self.assertIn('attachment',response.headers['Content-Disposition'])
        with urlopen(self.base+'/api/runs') as response:
            self.assertEqual(len(json.load(response)),1)

    def test_invalid_payload_returns_400(self):
        with self.assertRaises(HTTPError) as caught:self.post([])
        self.assertEqual(caught.exception.code,400)

    def test_cross_origin_write_rejected(self):
        with self.assertRaises(HTTPError) as caught:self.post({},'https://untrusted.example')
        self.assertEqual(caught.exception.code,403)

    def test_unknown_run_and_path_are_404(self):
        for path in ['/api/runs/999','/../server.py','/flowcheck/schema.sql']:
            with self.subTest(path=path),self.assertRaises(HTTPError) as caught:urlopen(self.base+path)
            self.assertEqual(caught.exception.code,404)


if __name__=='__main__': unittest.main()
