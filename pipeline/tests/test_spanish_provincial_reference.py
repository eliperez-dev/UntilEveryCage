"""Synthetic negative controls for local CartoCiudad package comparisons."""
import hashlib
import copy
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
from urllib.parse import urlsplit
import zipfile

from pipeline.geocoding import spanish_provincial_reference as p
from pipeline.geocoding.spanish_address_reference import exact_matches


def geometry(srid=4258, x=-3.7, y=40.4):
    return b'GP\x00\x01' + struct.pack('<iBI2d', srid, 1, 1, x, y)


class ProvincialReferenceTests(unittest.TestCase):
    def archive(self, root, *, kind='Portal', srid=4258, changes=None, duplicate=False):
        db = Path(root)/'test.gpkg'
        with closing(sqlite3.connect(db)) as c:
            c.execute('CREATE TABLE gpkg_geometry_columns(table_name,column_name,geometry_type_name,srs_id,z,m)')
            c.execute("INSERT INTO gpkg_geometry_columns VALUES('portalpk_publi','geom','POINT',?,0,0)", (srid,))
            c.execute('CREATE TABLE gpkg_spatial_ref_sys(srs_id,organization,organization_coordsys_id)')
            c.execute("INSERT INTO gpkg_spatial_ref_sys VALUES(?,'EPSG',?)", (srid,srid))
            c.execute('CREATE TABLE portalpk_publi('+','.join(p.FIELDS)+')')
            row = dict(zip(p.FIELDS, ['synthetic-1',kind,'CALLE','Example','4',None,'28001',
                'Example Town','Madrid','Synthetic provider','2026-01-01',geometry(srid)]))
            row.update(changes or {})
            c.execute('INSERT INTO portalpk_publi VALUES('+','.join('?' for _ in p.FIELDS)+')',tuple(row.values()))
            if duplicate:
                c.execute('INSERT INTO portalpk_publi SELECT * FROM portalpk_publi')
            c.commit()
        archive = Path(root)/'test.zip'
        with zipfile.ZipFile(archive,'w') as z: z.write(db, 'nested/test.gpkg')
        return archive, dict(province='Madrid', source_url='https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=123',
            retrieved_at='2026-10-31T00:00:00Z',expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_numbered_portal_matches_and_keeps_native_crs(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root)
            rows,report=p.read_archive(archive,**args)
            self.assertEqual(report['numbered_reference_points'],1)
            self.assertEqual(rows[0]['crs'],'EPSG:4258')
            primary=[{'case_id':'synthetic','context':{'address':'Calle Example 4',
                'locality':'Example Town','province':'Madrid','postcode':'28001'}}]
            self.assertEqual(exact_matches(primary,rows)[1]['matched'],1)
            self.assertFalse(report['facility_addresses_sent'])
            self.assertEqual(report['points_imported'],0)

    def test_empty_plan_validates_archive_without_retaining_unrelated_points(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root)
            rows,report=p.read_archive(archive,**args,municipalities=set(),matching_inputs=[])
            self.assertEqual(rows,[])
            self.assertEqual(report['source_points'],1)
            self.assertEqual(report['numbered_reference_points'],0)
            self.assertEqual(report['provider_calls'],0)
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root,changes={'provincia':'Other Province'})
            with self.assertRaisesRegex(ValueError,'identity_or_province'):
                p.read_archive(archive,**args,municipalities=set(),matching_inputs=[])

    def test_pk_and_zero_house_are_never_numbered_portals(self):
        for changes in ({'tipo':'PK'},{'numero':'0'},{'numero':'S/N'},{'extension':'Nave 9'}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as root:
                archive,args=self.archive(root,changes=changes)
                self.assertEqual(p.read_archive(archive,**args)[0],[])
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root,kind='PK de vía de servicio')
            rows,report=p.read_archive(archive,**args,include_kilometres=True)
            self.assertEqual(rows,[])
            self.assertEqual(report['service_road_kilometre_points_excluded'],1)

    def test_municipality_scope_does_not_load_unrelated_portals(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root)
            rows,report=p.read_archive(archive,**args,municipalities={'Other Town'})
            self.assertEqual(rows,[])
            self.assertEqual(report['source_points'],1)
            self.assertEqual(report['other_municipality_portals'],1)
            self.assertEqual(len(p.read_archive(archive,**args,municipalities={'Example Town'})[0]),1)
            with self.assertRaises(ValueError):p.read_archive(archive,**args,municipalities=set())

    def test_streaming_scope_keeps_all_matching_road_types_for_ambiguity_check(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root)
            with closing(sqlite3.connect(Path(root)/'test.gpkg')) as c:
                c.execute("INSERT INTO portalpk_publi SELECT 'synthetic-2',tipo,'AVENIDA',nombre_via,numero,"
                    "extension,cod_postal,municipio,provincia,fuente_datos,fecha_modificacion,geom FROM portalpk_publi")
                c.commit()
            with zipfile.ZipFile(archive,'w') as z:z.write(Path(root)/'test.gpkg','test.gpkg')
            args['expected_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
            item={'case_id':'synthetic','context':{'address':'Example 4','locality':'Example Town',
                'province':'Madrid','postcode':'28001'}}
            refs,_=p.read_archive(archive,**args,matching_inputs=[item])
            self.assertEqual(len(refs),2)
            self.assertEqual(exact_matches([item],refs)[1]['ambiguous'],1)
            item['context']['address']='Calle Example 4'
            refs,_=p.read_archive(archive,**args,matching_inputs=[item])
            self.assertEqual(exact_matches([item],refs)[1]['matched'],1)

    def test_kilometre_reference_is_separate_from_numbered_portals(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root,kind='PK',changes={'tipo_vial':'CARRETERA'})
            refs,report=p.read_archive(archive,**args,include_kilometres=True)
            self.assertEqual((report['numbered_reference_points'],report['kilometre_reference_points']),(0,1))
            item={'case_id':'synthetic','context':{'address':'CTRA Example KM 4',
                'locality':'Example Town','province':'Madrid','postcode':'28001'}}
            matches,comparison=p.kilometre_matches([item],refs)
            self.assertEqual(comparison['matched'],1)
            self.assertEqual(matches['synthetic']['match_precision'],'approximate_road_kilometre_reference')
            self.assertEqual(exact_matches([item],refs)[1]['matched'],0)
            for field,value in [('address','CTRA Example KM 4,5'),('locality','Wrong town'),
                                ('province','Sevilla'),('postcode','28002')]:
                changed={**item,'context':{**item['context'],field:value}}
                self.assertEqual(p.kilometre_matches([changed],refs)[1]['matched'],0)
            self.assertEqual(p.kilometre_matches([item],refs+refs)[1]['ambiguous'],1)

    def test_kilometre_parser_does_not_guess_house_numbers_or_distances(self):
        self.assertEqual(p.kilometre_address('Carretera Example KM 4,500'),('road example','4.5'))
        self.assertEqual(p.kilometre_address('CR N-123, KM 4.500'),('road n 123','4.5'))
        for source in ['Calle Example 4','Carretera Example 4','Carretera Example KM 4-5',
                       'Carretera Example KM 4 KM 5','Industrial Estate Example KM 4']:
            self.assertIsNone(p.kilometre_address(source))

    def test_envelope_and_big_endian_points_are_decoded_without_axis_swap(self):
        blob=b'GP\x00\x03'+struct.pack('<i4d',4258,-3.7,-3.7,40.4,40.4)+struct.pack('<BI2d',1,1,-3.7,40.4)
        self.assertEqual(p.point_geometry(blob,4258),(-3.7,40.4))
        big=b'GP\x00\x00'+struct.pack('>iBI2d',4258,0,1,-3.7,40.4)
        self.assertEqual(p.point_geometry(big,4258),(-3.7,40.4))
        with self.assertRaises(ValueError):p.point_geometry(b'GP\x00\x11'+geometry()[4:],4258)

    def test_changed_archive_crs_province_and_duplicate_fail(self):
        for failure in ('hash','srid','province','duplicate','type'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
                archive,args=self.archive(root,srid=4326 if failure=='srid' else 4258,
                    duplicate=failure=='duplicate',changes={'tipo':'Unknown'} if failure=='type' else None)
                if failure=='hash': args['expected_sha256']='0'*64
                if failure=='province': args['province']='Sevilla'
                with self.assertRaises(ValueError):p.read_archive(archive,**args)

    def test_canary_file_retains_its_verified_regcan95_crs_and_extent(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root,srid=4081,changes={'provincia':'Las Palmas','geom':geometry(4081,-15.4,28.1)})
            args['province']='Las Palmas'
            rows,report=p.read_archive(archive,**args)
            self.assertEqual(rows[0]['crs'],'EPSG:4081')
            self.assertEqual(report['crs'],'EPSG:4081')
            with self.assertRaises(ValueError):p.read_archive(archive,**{**args,'province':'Madrid'})
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root,srid=4081,changes={'provincia':'Las Palmas','geom':geometry(4081,-3.7,40.4)})
            args['province']='Las Palmas'
            with self.assertRaisesRegex(ValueError,'canary_geometry_out_of_bounds'):p.read_archive(archive,**args)

    def test_geometry_rejects_swapped_missing_nonfinite_and_wrong_srs(self):
        for blob in (geometry(4326),geometry(x=float('nan')),geometry(x=40,y=-3),
                     geometry()[:-1],b'not geometry',geometry()+b'extra'):
            with self.subTest(size=len(blob)),self.assertRaises(ValueError):p.point_geometry(blob,4258)
        self.assertEqual(p.point_geometry(geometry(),4258),(-3.7,40.4))

    def test_unsupported_origin_and_size_fail_before_read(self):
        with tempfile.TemporaryDirectory() as root:
            archive,args=self.archive(root)
            for url in ('http://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=123',
                        'https://other.test/CentroDescargas/detalleArchivo?sec=123'):
                with self.assertRaises(ValueError):p.read_archive(archive,**{**args,'source_url':url})


@unittest.skipUnless(os.environ.get('UEC_SPANISH_PROVINCIAL_SQL_TESTS')=='1'
    and urlsplit(os.environ.get('UEC_DATABASE_URL','')).path.strip('/')=='uec_launch_sources_test_20261025',
    'opt-in approved local database and retained provincial comparison required')
class ProvincialPostgisTests(unittest.TestCase):
    def test_stored_result_geometry_and_components_are_checked_without_new_requests(self):
        import psycopg
        import uuid
        from pipeline.scripts.release_baseline import load_contract,verify_connection
        root=Path(__file__).resolve().parents[2]
        with psycopg.connect(os.environ['UEC_DATABASE_URL']) as connection:
            try:
                connection.execute("SET LOCAL statement_timeout='30s'")
                parent=connection.execute("""SELECT geocode_result_id,response FROM uec.geocode_results r
                    WHERE provider_id='cartociudad_local' AND status='accepted'
                    AND EXISTS(SELECT 1 FROM real_preview.geocode_display_evidence e
                               WHERE e.geocode_result_id=r.geocode_result_id)
                    ORDER BY queried_at LIMIT 1""").fetchone()
                if parent is None:self.skipTest('no stored native result; pre-import trial covers fresh results')
                contract=load_contract(root/'pipeline/contracts/development-baseline.json')
                verify_connection(connection,contract)
                for field,value,expected in [(None,None,1),('house','987654321',0),
                    ('municipality','Synthetic Wrong Town',0),('province','Synthetic Wrong Province',0),
                    ('point_kind','kilometre',0)]:
                    response=copy.deepcopy(parent[1])
                    if field:response['selected'][field]=value
                    ident=uuid.uuid4()
                    connection.execute("""INSERT INTO uec.geocode_results(geocode_result_id,source_record_id,
                        provider_id,provider_version,query,provider_address_id,result,precision,match_method,
                        status,attempt_number,retryable,response,queried_at)
                        SELECT %s,source_record_id,provider_id,provider_version,query,provider_address_id,
                        result,precision,match_method,status,attempt_number,retryable,%s::jsonb,queried_at
                        FROM uec.geocode_results WHERE geocode_result_id=%s""",(ident,json.dumps(response),parent[0]))
                    self.assertEqual(connection.execute('SELECT count(*) FROM real_preview.geocode_display_evidence WHERE geocode_result_id=%s',
                        (ident,)).fetchone()[0],expected)
                verify_connection(connection,contract)
            finally:connection.rollback()

    def test_real_matches_rollback_and_forged_components_do_not_project(self):
        import psycopg
        from pipeline.scripts.release_baseline import load_contract,verify_connection,_migration_checksums
        root=Path(__file__).resolve().parents[2]
        evidence=root/'data/staging/spain-provincial-reference-20261031/acoruna-bound-comparison-v2.json'
        if not evidence.is_file():self.skipTest('retained private reference comparison unavailable')
        saved=json.loads(evidence.read_text(encoding='utf-8'))
        migration=root/'pipeline/migrations/118_cartociudad_local_portal_display.sql'
        with psycopg.connect(os.environ['UEC_DATABASE_URL']) as connection:
            try:
                connection.execute("SET LOCAL statement_timeout='90s'")
                applied=connection.execute('SELECT version FROM uec.schema_migrations WHERE version=%s',(migration.stem,)).fetchone()
                checks=_migration_checksums()
                if not applied:checks.pop(migration.stem)
                contract=load_contract(root/'pipeline/contracts/development-baseline.json')
                verify_connection(connection,contract,checks)
                connection.execute(migration.read_text(encoding='utf-8'))
                connection.execute(migration.read_text(encoding='utf-8'))
                primary,_=p.plan_comparison(connection,saved['summary']['archive']['province'])
                primary=[item for item in primary if item['case_id'] in saved['matches']]
                if not primary:self.skipTest('native matches already applied; no unattempted acceptance targets remain')
                one=primary[:1]
                for field,value in [('house','987654321'),('municipality','Synthetic Wrong Town'),
                                    ('province','Synthetic Wrong Province'),('point_kind','kilometre'),('crs','EPSG:4326')]:
                    forged=copy.deepcopy(saved['matches']);forged[one[0]['case_id']][field]=value
                    with self.assertRaises((ValueError,KeyError)):
                        with connection.transaction():p.apply_portal_matches(connection,one,forged,saved['summary']['archive'])
                result=p.apply_portal_matches(connection,primary,saved['matches'],saved['summary']['archive'])
                self.assertEqual(result['local_results_appended'],len(primary))
                self.assertEqual(result['display_evidence_appended'],sum(len(i['targets']) for i in primary))
                self.assertEqual(result['quota_reservations_created'],0)
                bad_geometry=connection.execute("""INSERT INTO uec.geocode_results(source_record_id,provider_id,
                    provider_version,query,provider_address_id,result,precision,match_method,status,
                    attempt_number,retryable,response,queried_at)
                    SELECT source_record_id,provider_id,provider_version,query,provider_address_id,
                    ST_SetSRID(ST_MakePoint(0,0),4326)::geography,precision,match_method,status,
                    attempt_number,retryable,response,queried_at FROM uec.geocode_results
                    WHERE provider_id='cartociudad_local' ORDER BY queried_at LIMIT 1
                    RETURNING geocode_result_id""").fetchone()[0]
                self.assertEqual(connection.execute('SELECT count(*) FROM real_preview.geocode_display_evidence WHERE geocode_result_id=%s',
                    (bad_geometry,)).fetchone()[0],0)
                from pipeline.common.release_geometry import PROVIDER_CONFIDENCE_SQL
                metadata={'provider':'cartociudad_local','method':'cartociudad_local_portal_v1',
                    'precision':'provider_address_point_high_confidence','coordinate_review_status':
                    'automated_high_confidence_private_display','confidence':None}
                for changed,expected in [(metadata,True),({**metadata,'confidence':0.99},False),
                                         ({**metadata,'method':'source_coordinate'},False),
                                         ({**metadata,'coordinate_review_status':'pending'},False)]:
                    actual=connection.execute('SELECT coalesce('+PROVIDER_CONFIDENCE_SQL+
                        ',false) FROM (SELECT %s::jsonb evidence) input',
                        (json.dumps({'display_location':changed}),)).fetchone()[0]
                    self.assertEqual(actual,expected)
                again=p.apply_portal_matches(connection,primary,saved['matches'],saved['summary']['archive'])
                self.assertEqual(again['local_results_appended'],0)
                verify_connection(connection,contract,checks)
            finally:
                connection.rollback()


if __name__=='__main__':unittest.main()
