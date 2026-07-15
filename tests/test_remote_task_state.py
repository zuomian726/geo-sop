import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / "server" / "geo.allgood.cn" / "api" / "remote-task-state.php"


class RemoteTaskStateTests(unittest.TestCase):
    def test_remote_status_endpoint_uses_atomic_state_guard(self):
        source = (ROOT / "server" / "geo.allgood.cn" / "api" / "remote-tasks" / "index.php").read_text(
            encoding="utf-8"
        )
        self.assertIn("geo_remote_status_transition_allowed", source)
        self.assertIn("AND status=?", source)
        self.assertIn("remote task status changed concurrently", source)

    @unittest.skipUnless(shutil.which("php"), "PHP is not installed")
    def test_terminal_states_cannot_regress(self):
        state_path = json.dumps(str(STATE_FILE))
        php = f"""
        require {state_path};
        $cases = [
            ['claimed', 'imported'],
            ['imported', 'running'],
            ['queued', 'completed'],
            ['running', 'failed'],
            ['completed', 'running'],
            ['failed', 'completed'],
            ['stopped', 'running'],
            ['skipped', 'imported'],
            ['completed', 'completed'],
        ];
        echo json_encode(array_map(
            fn($case) => geo_remote_status_transition_allowed($case[0], $case[1]),
            $cases
        ));
        """
        result = subprocess.run(
            [shutil.which("php"), "-r", php],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            [True, True, True, True, False, False, False, False, True],
            json.loads(result.stdout),
        )


if __name__ == "__main__":
    unittest.main()
