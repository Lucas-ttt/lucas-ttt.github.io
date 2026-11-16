"""通过两个本地 HTTP 端点验证接口和模型适配行为。"""

import http.client
import json
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from answer_service import LocalQueryServer, ModelConfig
from project_walkthrough import build_index


class FixtureModelHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.received.append((self.path, payload, self.headers.get("Authorization")))
        if self.server.delay:
            time.sleep(self.server.delay)
        body = json.dumps({
            "choices": [{"message": {"content": self.server.output}}],
            "usage": {"prompt_tokens": 25, "completion_tokens": 8, "total_tokens": 33},
        }).encode("utf-8")
        self.send_response(self.server.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        try:
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return


@contextmanager
def running(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    with server:
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join()


def request(server, method="POST", path="/query", body=None, content_type="application/json"):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        connection.request(method, path, data, {"Content-Type": content_type})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class AnswerServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = build_index()

    @contextmanager
    def configured(self, output, delay=0, timeout=2, response_status=200):
        model = ThreadingHTTPServer(("127.0.0.1", 0), FixtureModelHandler)
        model.output = output
        model.delay = delay
        model.response_status = response_status
        model.received = []
        with running(model):
            config = ModelConfig(
                f"http://127.0.0.1:{model.server_port}/v1/chat/completions",
                "test-fixture",
                timeout=timeout,
            )
            with running(LocalQueryServer(0, self.index, config)) as app:
                yield app, model

    def test_extracts_version_specific_evidence_and_health(self):
        with running(LocalQueryServer(0, self.index)) as server:
            status, health = request(server, method="GET", path="/health")
            self.assertEqual((status, health["mode"]), (200, "extractive"))
            for version, field in [("v1", "user_id"), ("v2", "customer_id")]:
                status, result = request(server, body={"query": "E102", "version": version})
                self.assertEqual((status, result["status"]), (200, "extractive"))
                self.assertIn(field, result["answer"])
                self.assertEqual(result["citations"], [f"csv-{version}"])
                self.assertEqual(result["sources"][0]["version"], version)
                self.assertIsNone(result["timing_ms"]["model_request"])
                self.assertNotEqual(result["request_id"], health["request_id"])

    def test_rejects_invalid_requests_before_model_call(self):
        with self.configured("") as (app, model):
            for payload in [
                {"query": "E102"},
                {"query": " ", "version": "v2"},
                {"query": "E102", "version": "v2", "endpoint": "untrusted"},
            ]:
                with self.subTest(payload=payload):
                    status, result = request(app, body=payload)
                    self.assertEqual((status, result["status"]), (400, "invalid_request"))
                    self.assertTrue(result["request_id"])
            self.assertEqual(model.received, [])

    def test_no_evidence_never_calls_model(self):
        with self.configured("") as (app, model):
            status, result = request(app, body={"query": "E102", "version": "v9"})
            self.assertEqual((status, result["status"]), (200, "insufficient_evidence"))
            self.assertEqual(result["sources"], [])
            self.assertIsNone(result["timing_ms"]["model_request"])
            self.assertIsNone(result["usage"])
            self.assertEqual(model.received, [])

    def test_accepts_completion_with_citations_from_current_evidence(self):
        output = json.dumps({"answer": "检查 customer_id 列", "citations": ["csv-v2"]})
        with self.configured(output) as (app, model):
            status, result = request(app, body={"query": "E102", "version": "v2"})
            self.assertEqual((status, result["status"]), (200, "generated"))
            self.assertEqual(result["answer"], "检查 customer_id 列")
            self.assertEqual(result["citations"], ["csv-v2"])
            self.assertEqual(result["usage"]["total_tokens"], 33)
            self.assertGreaterEqual(result["timing_ms"]["citation_check"], 0)
            path, payload, authorization = model.received[0]
            self.assertEqual(path, "/v1/chat/completions")
            self.assertIsNone(authorization)
            evidence = json.loads(payload["messages"][1]["content"])["evidence"]
            self.assertEqual([row["id"] for row in evidence], ["csv-v2"])

    def test_rejects_wrong_version_reference_and_returns_source(self):
        output = json.dumps({"answer": "检查 user_id 列", "citations": ["csv-v1"]})
        with self.configured(output) as (app, _model):
            status, result = request(app, body={"query": "E102", "version": "v2"})
            self.assertEqual((status, result["status"]), (200, "fallback"))
            self.assertEqual(result["reason"], "model_citation_invalid")
            self.assertEqual(result["citations"], ["csv-v2"])
            self.assertIn("customer_id", result["answer"])
            # 已发生的模型用量仍在结果中，便于解释降级请求的费用。
            self.assertEqual(result["usage"]["total_tokens"], 33)

    def test_model_timeout_returns_source(self):
        with self.configured("", delay=0.6, timeout=0.12) as (app, model):
            status, result = request(app, body={"query": "E102", "version": "v2"})
            self.assertEqual((status, result["status"]), (200, "fallback"))
            self.assertEqual(result["reason"], "model_timeout")
            self.assertEqual(result["citations"], ["csv-v2"])
            self.assertIsNone(result["usage"])
            self.assertEqual(len(model.received), 1)

    def test_malformed_completion_and_upstream_rejection_return_source(self):
        for output, response_status, reason in [
            ("无法解析", 200, "model_output_invalid"),
            ("", 503, "model_http_error"),
        ]:
            with self.subTest(reason=reason), self.configured(output, response_status=response_status) as (app, _model):
                status, result = request(app, body={"query": "E102", "version": "v2"})
                self.assertEqual((status, result["status"]), (200, "fallback"))
                self.assertEqual(result["reason"], reason)
                self.assertEqual(result["citations"], ["csv-v2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
