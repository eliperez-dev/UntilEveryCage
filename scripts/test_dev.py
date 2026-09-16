import json, os, subprocess, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class DevEntrypointTests(unittest.TestCase):
  def test_help(self):
    result = subprocess.run([sys.executable, "scripts/dev.py", "--help"], cwd=ROOT, capture_output=True, text=True)
    self.assertEqual(result.returncode, 0)
    self.assertIn("doctor", result.stdout)
    self.assertIn("review-packet", result.stdout)

  def test_doctor_json_does_not_echo_secret(self):
    result = subprocess.run([sys.executable, "scripts/dev.py", "--json", "doctor"], cwd=ROOT, env={**os.environ, "UEC_DATABASE_URL": "postgresql://secret.invalid/db"}, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    self.assertEqual(payload["command"], "doctor")
    self.assertNotIn("secret.invalid", result.stdout)

if __name__ == "__main__": unittest.main()
