import unittest
import tempfile, json, hashlib
from .it_853_adapter import Italy853Adapter
from pipeline.contracts.adapter_contract import SourceArtifact
from pipeline.common.orchestrator import run_private_lifecycle
H="precedente_bollo_cee;num_identificativo_produzione_commercializzazione;ragione_sociale;indirizzo;comune;provincia;codice_regione;regione;classificazione_stabilimento;codice_impianto_attivita;descrizione_impianto_attivita;prodotti_abilitati;specifica_prodotti;paesi_export_autorizzato;longitudine;latitudine;stato_localizzazione;cod_fiscale;p_iva;codice_comune;data_inizio_attivita;data_fine_attivita;stato_attivita;data_ultimo_aggiornamento;num_identificativo_produzione_commercializzazione_2"
def row(n="A",a="10",s="Autorizzata"): return f";{n};Name;;Town;;010;Piemonte;X;{a};Activity;P;S;IT;12;45;1;tax;vat;001001;;;{s};2026-09-13;\n"
class Test(unittest.TestCase):
 def test_safe_mapping(self):
  r=Italy853Adapter().parse_bytes((H+"\n"+row()).encode())["accepted"][0]; self.assertIsNone(r["normalized"]["coordinates"]); self.assertIsNone(r["normalized"]["address"]); self.assertIn("p_iva",r["source_values"]); self.assertEqual(r["normalized"]["location_role"],"recognized-establishment-location"); self.assertEqual(r["normalized"]["registered_location_state"],"not-supplied-by-source"); self.assertEqual(r["normalized"]["operating_location_state"],"source-location-not-operating-proof"); self.assertEqual(r["normalized"]["rights_gate"],"review_required")
 def test_quarantine(self):
  r=Italy853Adapter().parse_bytes((H+"\n"+row()+row("A","10","Unknown")).encode()); self.assertEqual(len(r["accepted"]),1); self.assertIn("unknown_status",r["quarantined"][0]["reasons"])
 def test_sensitive_and_deterministic_identity(self):
  content=(H+"\n"+row()).encode(); a=Italy853Adapter(); x=a.parse_bytes(content)["accepted"][0]; y=a.parse_bytes(content)["accepted"][0]; self.assertEqual(x["source_row_id"],y["source_row_id"]); self.assertNotIn("p_iva",x["normalized"]); self.assertIsNone(x["normalized"]["coordinates"])
 def test_shape_drift_quarantine(self):
  content=(H+"\n"+row().replace("Name","Name;extra")).encode(); self.assertRaises(ValueError,Italy853Adapter().parse_bytes,content)
  def test_missing_date_and_geography_are_explicit(self):
   r=Italy853Adapter().parse_bytes((H+"\n"+row().replace("001001","001").replace("2026-09-13","")).encode())["accepted"][0]
   self.assertEqual(r["normalized"]["date_state"]["data_inizio_attivita"],"unknown"); self.assertEqual(r["normalized"]["geography_precision"],"unknown"); self.assertEqual(r["normalized"]["coordinate_state"],"source-value-present-pending-review")
 def test_source_category_and_activity_coverage_are_explicit(self):
   result=Italy853Adapter().parse_bytes((H+"\n"+row()).encode()); self.assertEqual(result["source_category_counts"], {"X": 1}); self.assertEqual(result["source_activity_counts"], {"10": 1}); self.assertTrue(result["schema_fingerprint"])
 def test_current_catalog_abbreviated_dates_normalize_without_losing_source_values(self):
  content=(H+"\n"+row().replace("2026-09-13","14-LUG-22")).encode(); result=Italy853Adapter().parse_bytes(content); record=result["accepted"][0]
  self.assertEqual(record["normalized"]["dates"]["data_ultimo_aggiornamento"],"2022-07-14"); self.assertEqual(record["source_values"]["data_ultimo_aggiornamento"],"14-LUG-22")
 def test_catalog_dash_dates_are_unknown_not_invalid(self):
  record=Italy853Adapter().parse_bytes((H+"\n"+row().replace(";;;Autorizzata;2026-09-13;",";;-;Autorizzata;2026-09-13;")).encode())["accepted"][0]
  self.assertEqual(record["normalized"]["date_state"]["data_fine_attivita"],"unknown")
 def test_repeated_activity_quarantines_collision_without_merge(self):
  result=Italy853Adapter().parse_bytes((H+"\n"+row()+row()).encode()); self.assertEqual(len(result["accepted"]),1); self.assertEqual(len(result["quarantined"]),1); self.assertIn("ambiguous_repeated_recognition_activity",result["quarantined"][0]["reasons"])
 def test_run_writes_contract_manifest_and_row_quarantine(self):
  from pipeline.contracts.adapter_contract import assert_manifest
  content=(H+"\n"+row()+row("","10")).encode()
  with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
   f.write(content); f.flush(); sha=hashlib.sha256(content).hexdigest(); a=Italy853Adapter(); m=a.run(f.name,d,SourceArtifact("u","2026-09-14T00:00:00Z",sha,len(content),code_version="c",config_version="k")); assert_manifest(m,content,a.schema_version); self.assertTrue((__import__('pathlib').Path(d)/"normalized/records.jsonl").exists()); self.assertEqual(m["quarantined_rows"],1); self.assertNotIn("accepted",m); self.assertNotIn("source_values",json.dumps(m))
 def test_candidate_handoff_uses_shared_writer(self):
  content=(H+"\n"+row()).encode(); sha=hashlib.sha256(content).hexdigest(); a=Italy853Adapter()
  with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
   f.write(content); f.flush(); m=a.write_candidate_handoff(d,SourceArtifact("u","2026-09-14T00:00:00Z",sha,len(content)),a.parse_bytes(content)); self.assertEqual(m["contract_version"],"candidate-handoff-v1"); self.assertEqual(m["normalized_rows"],1)
 def test_shared_lifecycle_emits_private_health_and_candidate(self):
  content=(H+"\n"+row()+row("B","11")).encode(); sha=hashlib.sha256(content).hexdigest(); a=Italy853Adapter()
  with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
   f.write(content); f.flush(); artifact=SourceArtifact("https://example.invalid/it.csv","2026-09-14T00:00:00Z",sha,len(content),publication_date="2026-09-14",code_version=a.adapter_version,config_version=a.schema_version); status=run_private_lifecycle(f.name,__import__('pathlib').Path(d)/"runs",artifact,a); root=__import__('pathlib').Path(status["run_dir"]); self.assertEqual(status["status"],"candidate-ready"); self.assertEqual(status["manifest"]["contract_version"],"source-lifecycle-v1"); self.assertTrue((root/"qa.json").exists()); self.assertTrue((root/"source-health.json").exists()); self.assertTrue((root/"release-candidate/records.jsonl").exists()); self.assertNotIn("source_values",(root/"qa.json").read_text())
