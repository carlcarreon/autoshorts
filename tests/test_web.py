import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import web


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = web.app.test_client()

    def test_invalid_inputs_do_not_start_generation(self):
        with patch.object(web.subprocess, "run") as run:
            for data in (None, {}, {"topic": 123}, {"topic": "   "}, {"topic": "x" * 201}):
                self.assertEqual(self.client.post("/generate", json=data).status_code, 400)
            self.assertEqual(self.client.post("/generate", data="x" * 5000,
                                              content_type="application/json").status_code, 413)
            run.assert_not_called()

    def test_concurrent_request_is_rejected(self):
        web.generation_lock.acquire()
        try:
            self.assertEqual(self.client.post("/generate", json={"topic": "gravity"}).status_code, 409)
        finally:
            web.generation_lock.release()

    def test_failed_or_timed_out_process_releases_lock_and_hides_logs(self):
        for failure in (SimpleNamespace(returncode=1, stderr="private diagnostic details"),
                        subprocess.TimeoutExpired("python", 600)):
            with tempfile.TemporaryDirectory() as work, patch.object(web, "OUTPUT", Path(work)), \
                    patch.object(web.subprocess, "run") as run:
                if isinstance(failure, Exception):
                    run.side_effect = failure
                else:
                    run.return_value = failure
                response = self.client.post("/generate", json={"topic": "gravity"})
                self.assertIn(response.status_code, (500, 504))
                self.assertNotIn("private diagnostic details", response.get_data(as_text=True))
                self.assertFalse(web.generation_lock.locked())

    def test_unique_files_and_mp4_preview_download_range_requests(self):
        def fake_run(command, **kwargs):
            path = Path(command[command.index("--output") + 1])
            path.write_bytes(b"example mp4 bytes")
            self.assertEqual(command[-2:], ["--", "--an arbitrary topic"])
            return SimpleNamespace(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as work, patch.object(web, "OUTPUT", Path(work)), \
                patch.object(web.subprocess, "run", side_effect=fake_run):
            responses = [self.client.post("/generate", json={"topic": "--an arbitrary topic"}) for _ in range(2)]
            for response in responses:
                self.assertEqual(response.status_code, 200)
            urls = [response.json["video_url"] for response in responses]
            self.assertNotEqual(*urls)
            preview = self.client.get(urls[0], headers={"Range": "bytes=0-3"})
            self.assertEqual(preview.status_code, 206)
            self.assertEqual(preview.content_type, "video/mp4")
            self.assertEqual(preview.data, b"exam")
            download = self.client.get(responses[0].json["download_url"])
            self.assertIn("attachment", download.headers["Content-Disposition"])
            self.assertEqual(download.data, b"example mp4 bytes")
            preview.close()
            download.close()

    def test_secret_and_arbitrary_files_are_not_served(self):
        for path in ("/.env", "/videos/.env", "/download/main.py", "/videos/autoshorts.mp4"):
            self.assertEqual(self.client.get(path).status_code, 404)


if __name__ == "__main__":
    unittest.main()
