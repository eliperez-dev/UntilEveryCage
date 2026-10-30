import copy
import json
import unittest
from pipeline.sources.uk.fhrs_reference import project,exact_matches,fetch_manufacturers


class FhrsReferenceTests(unittest.TestCase):
    def fetch(self,pages):
        class Response:
            def __init__(self,payload,url):self.payload=json.dumps(payload).encode();self.url=url
            def __enter__(self):return self
            def __exit__(self,*_):return False
            def geturl(self):return self.url
            def read(self,size):return self.payload[:size]
        responses=iter([{'businessTypes':[{'BusinessTypeName':'Manufacturers/packers','BusinessTypeId':7}]},*pages])
        def opener(request,timeout):
            self.assertNotIn('Example Foods',request.full_url)
            return Response(next(responses),request.full_url)
        return fetch_manufacturers(opener=opener,sleep=lambda _:None)

    def row(self):
        return {"FHRSID":1,"BusinessName":"Example Foods","PostCode":"AB1 2CD",
            "AddressLine1":"4 Example Road","AddressLine2":"Example Town","AddressLine3":"","AddressLine4":"",
            "Phone":"do not retain","RightToReply":"do not retain","LocalAuthorityEmailAddress":"do not retain",
            "geocode":{"latitude":"52.1","longitude":"-.2"}}

    def test_projection_drops_contacts_and_requires_real_coordinate_fields(self):
        source=self.row();original=copy.deepcopy(source);result=project(source)
        self.assertEqual(result["reference_id"],1)
        for key in ("Phone","RightToReply","LocalAuthorityEmailAddress"):self.assertNotIn(key,result)
        self.assertEqual(source,original)
        for coordinates in ({"latitude":"NaN","longitude":"-.2"},{"latitude":"0","longitude":"0"},{},None):
            self.assertIsNone(project({**source,"geocode":coordinates}))

    def test_exact_match_requires_name_postcode_and_complete_address(self):
        reference=project(self.row())
        primary={"candidate_id":"synthetic","name":"Example Foods","postcode":"AB12CD",
                 "address_lines":["4 Example Road"],"city":"Example Town"}
        matches,counts=exact_matches([primary],[reference])
        self.assertEqual(list(matches),["synthetic"])
        self.assertEqual(counts["ambiguous_matches"],0)
        for change in ({"name":"Different Foods"},{"postcode":"AB1 2CE"},
                       {"address_lines":["5 Example Road"]},{"name":None},{"postcode":""}):
            self.assertFalse(exact_matches([{**primary,**change}],[reference])[0])
        duplicate={**reference,"reference_id":2}
        self.assertEqual(exact_matches([primary],[reference,duplicate])[1]["ambiguous_matches"],1)

    def test_benign_page_duplicates_do_not_claim_an_atomic_snapshot(self):
        first=self.row();second={**first,'FHRSID':2};third={**first,'FHRSID':3}
        pages=[{'establishments':[first,second],'meta':{'totalCount':3,'totalPages':2}},
               {'establishments':[second,third],'meta':{'totalCount':3,'totalPages':2}}]
        rows,manifest=self.fetch(pages)
        self.assertEqual(len(rows),3)
        self.assertEqual(manifest['duplicate_rows'],1)
        self.assertFalse(manifest['snapshot_atomic'])

    def test_conflicting_or_withdrawn_page_coordinate_is_not_used(self):
        first=self.row();removed={**first,'geocode':{}}
        pages=[{'establishments':[first],'meta':{'totalCount':2,'totalPages':2}},
               {'establishments':[removed],'meta':{'totalCount':2,'totalPages':2}}]
        rows,manifest=self.fetch(pages)
        self.assertEqual(rows,[])
        self.assertEqual(manifest['conflicting_ids_excluded'],1)
        self.assertFalse(manifest['unique_count_matches_published_total'])


if __name__=='__main__':unittest.main()
