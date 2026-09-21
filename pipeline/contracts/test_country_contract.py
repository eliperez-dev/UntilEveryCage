import unittest

from pipeline.contracts.country_contract import CountryContractError, validate_country_contract


def contract(**overrides):
    value = {
        "contract_version": "country-contract-v1",
        "country_code": "DK",
        "display_name": "Denmark",
        "source_ids": ["dk.smiley"],
        "coverage": {
            "scope_statement": "Danish food-business listings",
            "completeness": "not-claimed",
            "included": ["food-business listings"],
            "excluded": ["private records"],
            "disappearance_semantics": "not-observed; never inferred as closure",
        },
        "attribution": {
            "source_origin": "government source",
            "terms_status": "pending-human-review",
            "attribution_required": True,
            "notice": "Attribute source publisher.",
        },
        "owner_review": {"state": "awaiting-owner-review", "owner": None, "decision_id": None},
        "publication": {"state": "blocked", "approval_required": True, "reason": "review pending"},
        "readiness": {
            "schema_version": "country-source-readiness-v1",
            "state": "awaiting-owner-review",
            "owner_review": "awaiting-owner-review",
            "private_candidate": True,
            "public_release_allowed": False,
            "reasons": ["publication:blocked"],
        },
    }
    value.update(overrides)
    return value


class CountryContractTests(unittest.TestCase):
    def test_contract_requires_registered_source_ids(self):
        validate_country_contract(contract(), known_source_ids={"dk.smiley"})
        with self.assertRaises(CountryContractError):
            validate_country_contract(contract(source_ids=["not-registered"]), known_source_ids={"dk.smiley"})

    def test_contract_rejects_missing_coverage_semantics_and_publication(self):
        coverage = dict(contract()["coverage"])
        coverage.pop("disappearance_semantics")
        with self.assertRaises(CountryContractError):
            validate_country_contract(contract(coverage=coverage))
        publication = {"state": "approved-for-release", "approval_required": True}
        with self.assertRaises(CountryContractError):
            validate_country_contract(contract(publication=publication))


if __name__ == "__main__":
    unittest.main()
