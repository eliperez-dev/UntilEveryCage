"""Static guards for the private graph SQL/API contract."""

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]


class PrivateGraphContractTests(unittest.TestCase):
    def test_both_graph_handlers_cast_numeric_confidence_and_expand_each_direction(self):
        for path in (ROOT / "src" / "graph_private.rs", ROOT / "src" / "lib.rs"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("confidence::double precision AS confidence", text)
            self.assertIn("directions(step_direction)", text)
            self.assertIn("CASE WHEN d.step_direction='out' THEN e.to_type ELSE e.from_type END", text)
            self.assertIn("CASE WHEN d.step_direction='out' THEN e.to_id ELSE e.from_id END", text)
            self.assertIn("ORDER BY o.observed_at DESC, o.relationship_observation_id DESC", text)

    def test_queue_uses_existing_source_record_timestamp(self):
        text = (ROOT / "src" / "graph_private.rs").read_text(encoding="utf-8")
        self.assertIn("parsed_at::text FROM uec.source_records", text)
        self.assertNotIn("received_at::text FROM uec.source_records", text)

    def test_graph_response_does_not_return_private_notes(self):
        text = (ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
        traverse = text[text.index("pub async fn get_private_graph_traverse_handler"):]
        self.assertNotIn('"note":r.get', traverse)

    def test_docker_context_excludes_private_staging_and_secret_patterns(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        for pattern in ("data/", "private/", "staging/", "**/*secret*", "**/*credential*", "**/*token*"):
            self.assertIn(pattern, ignore)
        self.assertTrue((ROOT / "Dockerfile.context-test").exists())

    def test_pipeline_worker_uses_dedicated_image_target(self):
        compose = (ROOT / "docker-compose.pipeline.yml").read_text(encoding="utf-8")
        self.assertIn("dockerfile: Dockerfile.worker", compose)
        self.assertIn('restart: "no"', compose)


if __name__ == "__main__":
    unittest.main()
