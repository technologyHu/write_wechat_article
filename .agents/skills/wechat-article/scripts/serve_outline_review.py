"""Serve the current review on one loopback URL and queue explicit feedback."""
import argparse
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from time import monotonic
from uuid import UUID
import webbrowser

from render_outline_review import register_review_outputs, render, replace_current
from validate_outline_feedback import validate_feedback


MAX_FEEDBACK_BYTES = 12_000


class ReviewServer(HTTPServer):
    timeout = 1

    def __init__(self, review, codex, thread_id, *, source=None, port=0, review_path=None, receipt=None, version=None):
        self.review = review
        self.page = render(review, standalone=True, local_delivery=True).encode("utf-8")
        self.codex = codex
        self.thread_id = thread_id
        self.source = source
        self.review_path = review_path or "/" + secrets.token_urlsafe(24) + "/"
        self.receipt = receipt
        self.version = version
        self.queued_digest = None
        self.delivery_uncertain = False
        self.restore_receipt()
        self.last_activity = monotonic()
        super().__init__(("127.0.0.1", port), ReviewRequest)
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.host}"
        self.url = self.origin + self.review_path

    def refresh(self):
        if self.source is None:
            return
        review = json.loads(self.source.read_text(encoding="utf-8-sig"))
        if review == self.review:
            return
        if review["review_id"] == self.review["review_id"]:
            raise ValueError("a published review ID cannot change its content")
        page = render(review, standalone=True, local_delivery=True).encode("utf-8")
        self.review, self.page = review, page
        self.restore_receipt()
        self.last_activity = monotonic()

    def restore_receipt(self):
        self.queued_digest = None
        self.delivery_uncertain = False
        if self.receipt is None or not self.receipt.exists():
            return
        saved = json.loads(self.receipt.read_text(encoding="utf-8"))
        if (saved["review_id"], saved["thread_id"]) != (self.review["review_id"], self.thread_id):
            return
        if saved["status"] == "queued":
            self.queued_digest = saved["message_sha256"]
        else:
            self.delivery_uncertain = True

    def record_receipt(self, status, fingerprint):
        if self.receipt is None:
            return
        if status is None:
            self.receipt.unlink(missing_ok=True)
        else:
            replace_current(self.receipt, json.dumps({
                "status": status, "message_sha256": fingerprint,
                "review_id": self.review["review_id"], "thread_id": self.thread_id,
            }))
            register_review_outputs([self.receipt], f"serve_outline_review ({self.review['review_id']})", version=self.version)

    def queue(self, feedback):
        validate_feedback(self.review, feedback)
        message = json.dumps(feedback, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        encoded = message.encode("utf-8")
        if len(encoded) > MAX_FEEDBACK_BYTES:
            return HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "反馈过长，请复制到对话。"}
        fingerprint = sha256(encoded).hexdigest()
        if fingerprint == self.queued_digest:
            return HTTPStatus.OK, {"status": "queued"}
        if self.queued_digest is not None:
            return HTTPStatus.CONFLICT, {"error": "本轮已有反馈，请在对话里继续修改。"}
        if self.delivery_uncertain:
            return HTTPStatus.CONFLICT, {"error": "送达状态待确认，请先查看原对话。"}

        try:
            self.record_receipt("uncertain", fingerprint)
        except OSError:
            return HTTPStatus.BAD_GATEWAY, {"error": "无法记录提交状态，请复制反馈。"}
        try:
            result = subprocess.run(
                [self.codex, "queue", "--thread", self.thread_id, "--message", message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired:
            self.delivery_uncertain = True
            return HTTPStatus.GATEWAY_TIMEOUT, {"error": "送达状态待确认，请先查看原对话。"}
        except OSError:
            self.record_receipt(None, fingerprint)
            return HTTPStatus.BAD_GATEWAY, {"error": "暂时无法连接当前对话，可复制反馈。"}
        if result.returncode != 0:
            self.record_receipt(None, fingerprint)
            return HTTPStatus.BAD_GATEWAY, {"error": "当前对话未接受反馈，可复制后发送。"}
        self.queued_digest = fingerprint
        try:
            self.record_receipt("queued", fingerprint)
        except OSError:
            # The in-memory queue result is still valid. A restart retains the uncertainty marker.
            pass
        self.last_activity = monotonic()
        return HTTPStatus.OK, {"status": "queued"}


class ReviewRequest(BaseHTTPRequestHandler):
    timeout = 5

    def log_message(self, *_args):
        pass

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        review_path = self.server.review_path
        if self.headers.get("Host") != self.server.host or self.path not in (review_path, review_path + "current"):
            self.reply(HTTPStatus.NOT_FOUND, {"error": "页面不存在。"})
            return
        try:
            self.server.refresh()
        except (OSError, ValueError, KeyError, TypeError):
            self.reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "页面正在更新，请稍后重试。"})
            return
        if self.path.endswith("/current"):
            self.reply(HTTPStatus.OK, {"review_id": self.server.review["review_id"]})
            return
        self.reply(HTTPStatus.OK, self.server.page, "text/html; charset=utf-8")

    def do_POST(self):
        if self.headers.get("Host") != self.server.host or self.path != self.server.review_path + "feedback":
            self.reply(HTTPStatus.NOT_FOUND, {"error": "页面不存在。"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_FEEDBACK_BYTES:
                self.reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "反馈为空或过长。"})
                return
            raw = self.rfile.read(size)
            if self.headers.get("Origin") != self.server.origin:
                self.reply(HTTPStatus.FORBIDDEN, {"error": "请从本轮浏览器页面发送反馈。"})
                return
            if self.headers.get_content_type() != "application/json":
                self.reply(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "请提交 JSON 反馈。"})
                return
            feedback = json.loads(raw.decode("utf-8"))
            self.server.refresh()
            status, body = self.server.queue(feedback)
        except (OSError, TypeError, ValueError, KeyError, RecursionError):
            status, body = HTTPStatus.BAD_REQUEST, {"error": "反馈格式或轮次不匹配，请使用当前页面。"}
        self.reply(status, body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path, help="JSON used to render the current review round")
    parser.add_argument("--open-browser", action="store_true", help="open the initial page when explicitly requested")
    parser.add_argument("--reuse-url", help="restore a previously printed loopback URL")
    parser.add_argument("--version", help="Article or outline version of the review receipt")
    args = parser.parse_args()
    try:
        thread_id = str(UUID(os.environ.get("CODEX_THREAD_ID", "")))
        codex = shutil.which("codex.exe" if os.name == "nt" else "codex")
        if not codex:
            raise ValueError("Codex CLI is not available")
        options = {"timeout": 5, "capture_output": True}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        probe = subprocess.run([codex, "queue", "--help"], **options)
        if probe.returncode != 0 or b"--thread" not in probe.stdout:
            raise ValueError("This Codex CLI does not support codex queue")
        port, review_path = 0, None
        if args.reuse_url:
            match = re.fullmatch(r"http://127\.0\.0\.1:(\d{1,5})(/[A-Za-z0-9_-]{32}/)", args.reuse_url)
            if not match or not 1 <= int(match[1]) <= 65535:
                raise ValueError("expected a previously printed loopback URL")
            port, review_path = int(match[1]), match[2]
        source = args.review.resolve()
        review = json.loads(source.read_text(encoding="utf-8-sig"))
        with ReviewServer(review, codex, thread_id, source=source, port=port, review_path=review_path,
                          receipt=source.with_suffix(".delivery.json"), version=args.version) as server:
            print(json.dumps({"url": server.url, "review_id": review["review_id"]}), flush=True)
            if args.open_browser:
                webbrowser.open(server.url, new=2)
            while monotonic() - server.last_activity < 2 * 60 * 60:
                server.handle_request()
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Local feedback service unavailable: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
