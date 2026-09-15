import hashlib, json, os, subprocess, sys, tempfile, unittest, urllib.request, urllib.error
from pathlib import Path
import psycopg
from .fixture import E2EEnvironment
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.orchestrator import run_private_lifecycle
from pipeline.sources.italy.it_853_adapter import Italy853Adapter

ROOT=Path(__file__).resolve().parents[3]
HEADER="precedente_bollo_cee;num_identificativo_produzione_commercializzazione;ragione_sociale;indirizzo;comune;provincia;codice_regione;regione;classificazione_stabilimento;codice_impianto_attivita;descrizione_impianto_attivita;prodotti_abilitati;specifica_prodotti;paesi_export_autorizzato;longitudine;latitudine;stato_localizzazione;cod_fiscale;p_iva;codice_comune;data_inizio_attivita;data_fine_attivita;stato_attivita;data_ultimo_aggiornamento;num_identificativo_produzione_commercializzazione_2"
ROW=";IT-E2E-1;Synthetic Italy Facility;Private Address;Synthetic Town;XX;010;Piemonte;CODE=desc;A1;Synthetic activity;P;S;IT;12;45;1;restricted-tax;restricted-vat;001001;;;AUTORIZZATA;2026-09-14;"

class ItalyCandidateImportE2E(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if os.environ.get("UEC_RUN_E2E")!="1": raise unittest.SkipTest("set UEC_RUN_E2E=1")
  cls.env=E2EEnvironment(); cls.env.test_release_id="e2e-private-candidate"; cls.env=cls.env.start(); cls.temp=tempfile.TemporaryDirectory(); root=Path(cls.temp.name); cls.raw=root/"it.csv"; cls.raw.write_text(HEADER+"\n"+ROW+"\n",encoding="utf-8")
  a=Italy853Adapter(); raw=cls.raw.read_bytes(); artifact=SourceArtifact("https://example.invalid/it-853.csv","2026-09-14T00:00:00Z",hashlib.sha256(raw).hexdigest(),len(raw),code_version=a.adapter_version,config_version=a.schema_version)
  cls.run_dir=root/"lifecycle"; lifecycle=run_private_lifecycle(cls.raw,root/"runs",artifact,a); assert lifecycle["status"]=="candidate-ready", lifecycle; cls.run_dir=Path(lifecycle["run_dir"])
  cls.release_id="candidate-italy-e2e"; cmd=[sys.executable,str(ROOT/"pipeline/scripts/maintenance/import-candidate.py"),"--manifest",str(cls.run_dir/"manifest.json"),"--normalized",str(cls.run_dir/"normalized/records.jsonl"),"--raw",str(cls.raw),"--release-id",cls.release_id,"--database-url",cls.env.database_url,"--disposable-db"]
  for _ in range(2):
   result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True); assert result.returncode==0,result.stderr
  with psycopg.connect(cls.env.database_url) as db:
   db.execute("INSERT INTO uec.releases(release_id,status,ruleset_version,profile,test_only,summary) VALUES ('e2e-private-candidate','candidate','it-e2e','official',true,'{}')")
   facility,observation=db.execute("SELECT facility_id,observation_id FROM uec.observations JOIN uec.facilities USING(facility_id) WHERE source_record_id=(SELECT source_record_id FROM uec.source_records WHERE source_id='it.853-2004' LIMIT 1)").fetchone()
   # The importer-owned observation is linked into the fixed test-only release;
   # the distinct IDs are intentional CLI/API fixture plumbing, not a new row.
   db.execute("INSERT INTO uec.release_members(release_id,facility_id,observation_id,default_visible) VALUES ('e2e-private-candidate',%s,%s,false)",(facility,observation)); db.commit()
   cls.linked=db.execute("SELECT count(*) FROM uec.release_members m JOIN uec.observations o USING(observation_id) JOIN uec.source_records s USING(source_record_id) WHERE m.release_id='e2e-private-candidate' AND s.source_id='it.853-2004'").fetchone()[0]
   cls.counts=db.execute("SELECT (SELECT count(*) FROM uec.source_records WHERE source_id='it.853-2004'),(SELECT count(*) FROM uec.release_members WHERE release_id='e2e-private-candidate'),(SELECT count(*) FROM uec.release_members WHERE release_id='e2e-private-candidate' AND default_visible)").fetchone()
 @classmethod
 def tearDownClass(cls):
  if hasattr(cls,"temp"): cls.temp.cleanup()
  if hasattr(cls,"env"): cls.env.stop()
 def test_import_is_single_private_candidate(self): self.assertEqual(self.counts,(1,1,0)); self.assertEqual(self.linked,1)
 def test_failed_batch_rolls_back_then_valid_import_is_idempotent(self):
  bad_manifest=json.loads((self.run_dir/"manifest.json").read_text()); normalized=(self.run_dir/"normalized/records.jsonl").read_bytes(); bad=self.run_dir/"normalized/bad-records.jsonl"; bad.write_bytes(normalized+b'{"source_id":"it.853-2004","source_row":99}\n'); bad_manifest["normalized_rows"]=2; bad_manifest["normalized_sha256"]=hashlib.sha256(bad.read_bytes()).hexdigest(); bad_manifest_path=self.run_dir/"bad-manifest.json"; bad_manifest_path.write_text(json.dumps(bad_manifest),encoding="utf-8")
  bad_cmd=[sys.executable,str(ROOT/"pipeline/scripts/maintenance/import-candidate.py"),"--manifest",str(bad_manifest_path),"--normalized",str(bad),"--raw",str(self.raw),"--release-id","candidate-italy-recovery","--database-url",self.env.database_url,"--disposable-db","--batch-size","2"]; failed=subprocess.run(bad_cmd,cwd=ROOT,capture_output=True,text=True); self.assertNotEqual(failed.returncode,0)
  with psycopg.connect(self.env.database_url) as db: self.assertEqual(db.execute("SELECT count(*) FROM uec.releases WHERE release_id='candidate-italy-recovery'").fetchone()[0],0)
  good_cmd=[sys.executable,str(ROOT/"pipeline/scripts/maintenance/import-candidate.py"),"--manifest",str(self.run_dir/"manifest.json"),"--normalized",str(self.run_dir/"normalized/records.jsonl"),"--raw",str(self.raw),"--release-id","candidate-italy-recovery","--database-url",self.env.database_url,"--disposable-db"]
  first=subprocess.run(good_cmd,cwd=ROOT,capture_output=True,text=True); second=subprocess.run(good_cmd,cwd=ROOT,capture_output=True,text=True); self.assertEqual(first.returncode,0,first.stderr); self.assertEqual(second.returncode,0,second.stderr); self.assertIn("imported 0 candidate rows",first.stdout); self.assertIn("imported 0 candidate rows",second.stdout)
  with psycopg.connect(self.env.database_url) as db: self.assertEqual(db.execute("SELECT count(*) FROM uec.release_members WHERE release_id='candidate-italy-recovery'").fetchone()[0],1)
 def test_guarded_preview_and_public_exclusion(self):
  base=f"http://127.0.0.1:{self.env.api_port}"
  with urllib.request.urlopen(base+"/api/v2/locations?profile=official") as r: self.assertEqual(json.loads(r.read())["data"],[])
  h={"X-UEC-Dev-Preview-Token":self.env.dev_preview_token}
  req=urllib.request.Request(base+"/api/dev/preview/test-release/locations?profile=official&country_code=IT&limit=1",headers=h)
  with urllib.request.urlopen(req) as r: body=json.loads(r.read())
  self.assertTrue(body["meta"]["test_only"]); self.assertTrue(body["meta"]["private_preview"]); self.assertEqual(body["meta"]["release_status"],"candidate"); self.assertIn("preview_label",body["meta"]); self.assertEqual(len(body["data"]),1); self.assertIn("Italy",json.dumps(body)); self.assertNotIn("source_values",json.dumps(body)); self.assertIsNone(body["data"][0]["latitude"])
  fid=body["data"][0]["facility_id"]
  type(self).facility_id=fid
  with urllib.request.urlopen(urllib.request.Request(base+f"/api/dev/preview/test-release/locations/{fid}?profile=official",headers=h)) as r: detail=r.read().decode(); self.assertIn("Italy",detail); self.assertNotIn("source_values",detail)
  with urllib.request.urlopen(urllib.request.Request(base+"/api/dev/preview/test-release/discovery/facets?profile=official",headers=h)) as r: facets=r.read().decode(); self.assertIn("IT",facets); self.assertNotIn("source_values",facets)
  with urllib.request.urlopen(urllib.request.Request(base+"/api/dev/preview/test-release/locations.csv?profile=official",headers=h)) as r: export=r.read().decode(); self.assertIn("test_only",export); self.assertIn("Italy",export); self.assertNotIn("source_values",export); self.assertIn("uec-test-only",r.headers.get("Content-Disposition",""))
 def test_privacy_restriction_relocks_all_surfaces(self):
  with psycopg.connect(self.env.database_url) as db:
   record=db.execute("SELECT source_record_id FROM uec.source_records WHERE source_id='it.853-2004' LIMIT 1").fetchone()[0]
   db.execute("INSERT INTO uec.record_access_events(source_record_id,action,reason_category,policy_version,maintainer) VALUES (%s,'public_access_revoked','privacy','ethics-v1','authorized-synthetic-operator')",(record,)); db.commit()
  base=f"http://127.0.0.1:{self.env.api_port}"; h={"X-UEC-Dev-Preview-Token":self.env.dev_preview_token}
  with urllib.request.urlopen(urllib.request.Request(base+"/api/dev/preview/test-release/locations?profile=official",headers=h)) as r: self.assertEqual(json.loads(r.read())["data"],[])
  with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(urllib.request.Request(base+"/api/dev/preview/test-release/locations/"+self.facility_id+"?profile=official",headers=h))
  self.assertIn(error.exception.code,(404,410))
  with urllib.request.urlopen(urllib.request.Request(base+"/api/dev/preview/test-release/discovery/facets?profile=official",headers=h)) as r: self.assertNotIn('"IT"',r.read().decode())
  with urllib.request.urlopen(urllib.request.Request(base+"/api/dev/preview/test-release/locations.csv?profile=official",headers=h)) as r: self.assertEqual(len(r.read().decode().splitlines()),1)
  with urllib.request.urlopen(base+"/api/v2/locations?profile=official") as r: self.assertEqual(json.loads(r.read())["data"],[])

if __name__=="__main__": unittest.main()
