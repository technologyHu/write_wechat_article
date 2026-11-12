"""Exercise the loopback handoff with a mocked Codex process."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from serve_outline_review import ReviewServer
from render_outline_review import replace_current
from validate_outline_feedback import FORMAT


class OutlineReviewBridgeTest(unittest.TestCase):
    def setUp(self):
        review = {"stage": "final", "review_id": "example-final-r1", "markdown": "# 完整稿"}
        self.thread_id = "11111111-1111-4111-8111-111111111111"
        self.server = ReviewServer(review, "codex-test", self.thread_id)
        self.addCleanup(self.server.server_close)
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 1)
        self.addCleanup(self.server.shutdown)
        self.feedback = {
            "format": FORMAT,
            "review_id": review["review_id"],
            "stage": review["stage"],
            "decisions": [{"id": "outline", "decision": "confirm"}],
        }

    def post(self, feedback, *, origin=None):
        request = Request(
            self.server.url + "feedback",
            data=json.dumps(feedback).encode("utf-8"),
            headers={"Content-Type": "application/json", "Origin": origin or self.server.origin},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status
        except HTTPError as error:
            return error.code

    @patch("serve_outline_review.subprocess.run", return_value=SimpleNamespace(returncode=0))
    def test_valid_feedback_queues_to_bound_thread_once(self, run):
        with urlopen(self.server.url, timeout=5) as page:
            self.assertIn(b'data-outline-delivery="local"', page.read())
        self.assertEqual(self.post(self.feedback), 200)
        self.assertEqual(self.post(self.feedback), 200)
        changed = dict(self.feedback, decisions=[{"id": "outline", "decision": "revise", "value": "改标题"}])
        self.assertEqual(self.post(changed), 409)
        run.assert_called_once()
        args = run.call_args.args[0]
        self.assertEqual(args[:5], ["codex-test", "queue", "--thread", self.thread_id, "--message"])
        self.assertEqual(json.loads(args[5]), self.feedback)

    @patch("serve_outline_review.subprocess.run")
    def test_rejects_wrong_origin_wrong_round_and_unknown_route(self, run):
        self.assertEqual(self.post(self.feedback, origin="http://unrelated.test"), 403)
        self.assertEqual(self.post(dict(self.feedback, review_id="old-final-r1")), 400)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.server.origin + "/feedback", timeout=5)
        self.assertEqual(error.exception.code, 404)
        run.assert_not_called()

    @patch("serve_outline_review.subprocess.run")
    def test_cli_failure_allows_retry(self, run):
        run.side_effect = [SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)]
        self.assertEqual(self.post(self.feedback), 502)
        self.assertEqual(self.post(self.feedback), 200)
        self.assertEqual(run.call_count, 2)

    @patch("serve_outline_review.subprocess.run", return_value=SimpleNamespace(returncode=0))
    def test_same_url_advances_to_new_round_and_rejects_stale_feedback(self, run):
        self.assertEqual(self.post(self.feedback), 200)
        with TemporaryDirectory() as directory:
            self.server.source = Path(directory) / "current.json"
            new_review = dict(self.server.review, review_id="example-final-r2", markdown="# 修订稿")
            replace_current(self.server.source, json.dumps(new_review))
            with urlopen(self.server.url + "current", timeout=5) as current:
                self.assertEqual(json.load(current)["review_id"], "example-final-r2")
            with urlopen(self.server.url, timeout=5) as page:
                self.assertIn("修订稿".encode("utf-8"), page.read())
            self.assertEqual(self.post(self.feedback), 400)
            self.assertEqual(self.post(dict(self.feedback, review_id="example-final-r2")), 200)
            self.assertEqual(run.call_count, 2)

    @patch("serve_outline_review.subprocess.run", return_value=SimpleNamespace(returncode=0))
    def test_restarting_at_the_same_address_does_not_enqueue_again(self, run):
        with TemporaryDirectory() as directory:
            receipt = Path(directory) / "current.delivery.json"
            with ReviewServer(self.server.review, "test", self.thread_id, receipt=receipt) as original:
                url, port, route = original.url, original.server_port, original.review_path
                self.assertEqual(original.queue(self.feedback)[1], {"status": "queued"})
            with ReviewServer(self.server.review, "test", self.thread_id, port=port,
                              review_path=route, receipt=receipt) as restored:
                self.assertEqual(restored.url, url)
                self.assertEqual(restored.queue(self.feedback)[1], {"status": "queued"})
                run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
