import csv, json, tempfile, unittest
from pathlib import Path
from pipeline.scripts.diagnostics.geospatial_readiness_audit import audit

class GeospatialAuditTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); (self.d/'xx').mkdir()
        with (self.d/'xx'/'locations.csv').open('w', newline='', encoding='utf8') as f:
            w=csv.DictWriter(f, fieldnames=['establishment_id','street','city','zip','state','latitude','longitude']); w.writeheader()
            w.writerow(dict(establishment_id='1',street='Main 1',city='Town',zip='1',state='',latitude='55',longitude='12'))
            w.writerow(dict(establishment_id='2',street='',city='Town',zip='',state='',latitude='',longitude=''))
            w.writerow(dict(establishment_id='3',street='Private farmhouse',city='Town',zip='1',state='',latitude='',longitude=''))
    def test_funnel_and_row_free_sample(self):
        r=audit(self.d, sample_size=10, as_of='2026-09-16T00:00:00Z')
        self.assertEqual(r['funnel']['total'], 3); self.assertEqual(r['funnel']['source_coordinate_valid'], 1)
        self.assertEqual(r['funnel']['map_ready_under_current_rules'], 1); self.assertEqual(r['funnel']['privacy_restricted'], 1)
        payload=json.dumps(r); self.assertNotIn('Main 1', payload); self.assertNotIn('Private farmhouse', payload)
    def test_is_deterministic(self): self.assertEqual(audit(self.d, 2, 'x'), audit(self.d, 2, 'x'))
