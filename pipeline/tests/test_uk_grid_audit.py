import unittest
from pipeline.geocoding.uk_grid_audit import audit


class GridAuditTests(unittest.TestCase):
    def test_wrong_database_is_rejected_before_coordinate_queries(self):
        class Connection:
            def execute(self,sql,*_):
                if sql.startswith('SET '):return self
                if sql=='SELECT current_database()':return self
                raise AssertionError('must not inspect other databases')
            def fetchone(self):return ('other_database',)
        with self.assertRaisesRegex(ValueError,'wrong_disposable_database'):
            audit(Connection())

    def test_report_is_aggregate_hypothesis_not_point_approval(self):
        class Result:
            def __init__(self,value):self.value=value
            def fetchone(self):return self.value
        class Connection:
            def execute(self,sql,*_):
                if sql.startswith('SET '):return Result(None)
                if sql=='SELECT current_database()':return Result(('uec_launch_sources_test_20261025',))
                if 'count(DISTINCT(x,y))' in sql:return Result((10,9,10,0,2))
                if 'compared AS' in sql:return Result((5,2,3,4,1))
                return Result((10,))
        result=audit(Connection())
        self.assertEqual(result['raw_coordinate_pairs'],10)
        self.assertFalse(result['publisher_crs_confirmed'])
        self.assertEqual(result['points_promoted'],0)
        self.assertEqual(result['database_writes'],0)
        self.assertNotIn('coordinates',result)


if __name__=='__main__':unittest.main()
