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

  def test_contracts_command_uses_package_root_for_relative_imports(self):
    result = subprocess.run([sys.executable, "scripts/dev.py", "contracts"], cwd=ROOT, capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

  def test_json_delegated_command_is_machine_readable(self):
    result = subprocess.run([sys.executable, "scripts/dev.py", "--json", "status"], cwd=ROOT, capture_output=True, text=True)
    self.assertEqual(result.returncode, 0)
    payload = json.loads(result.stdout)
    self.assertEqual(payload["command"], "status")

  def test_probe_reports_unreachable_backend_without_stack_trace(self):
    probe = ROOT / "frontend" / "scripts" / "probe-local-v2.mjs"
    result = subprocess.run(["node", str(probe), "http://127.0.0.1:9"], cwd=ROOT, capture_output=True, text=True)
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("backend is not reachable", result.stderr)
    self.assertNotIn("at async", result.stderr)

if __name__ == "__main__": unittest.main()
