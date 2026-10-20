"""Model assistant transport, privacy and editor integration checks."""

from unittest.mock import MagicMock, patch

import pytest
from PyQt6 import Qsci

from rascal2.widgets.model_assistant import (
    CompletionWorker,
    ModelAssistant,
    assistant_messages,
    replacement_code,
)


@pytest.fixture
def assistant(qt_application):
    editor = Qsci.QsciScintilla()
    editor.setText("def model():\n    return 1\n")
    panel = ModelAssistant(editor)
    yield panel
    panel.close()


def test_context_and_reference_are_opt_in():
    messages = assistant_messages("Explain this", "", "python", False)
    assert "User-shared code" not in messages[1]["content"]
    assert "Repository reference" not in messages[0]["content"]
    messages = assistant_messages("Help", "shared_selection", "python", True)
    assert "shared_selection" in messages[1]["content"]
    assert "def custom_bilayer_DSPC" in messages[0]["content"]


@pytest.mark.parametrize("response", ["No code", "```python\nx = 1\n```\n```python\nx = 2\n```"])
def test_ambiguous_replacement(response):
    assert replacement_code(response) is None


def test_review_apply_and_undo_without_save(assistant, tmp_path):
    file = tmp_path / "model.py"
    file.write_text(assistant.editor.text())
    original = assistant.editor.text()
    assistant.snapshot = original
    assistant.response = "Updated:\n```python\ndef model():\n    return 2\n```\n"
    assistant.complete()
    assert "-    return 1" in assistant.diff.toPlainText()
    assert "+    return 2" in assistant.diff.toPlainText()
    assert assistant.editor.text() == original
    assistant.apply_proposal()
    assert "return 2" in assistant.editor.text()
    assert file.read_text() == original
    assistant.editor.undo()
    assert assistant.editor.text() == original


def test_stale_proposal_is_rejected(assistant):
    assistant.snapshot = assistant.editor.text()
    assistant.response = "```python\nx = 2\n```"
    assistant.complete()
    assistant.editor.setText("user edits")
    assistant.apply_proposal()
    assert assistant.editor.text() == "user edits"
    assert not assistant.apply.isEnabled()


def test_invalid_python_and_partial_response_cannot_apply(assistant):
    assistant.response = "```python\ndef broken(:\n```"
    assistant.complete()
    assert assistant.proposal is None
    assert not assistant.apply.isEnabled()
    assistant.response = "```python\nx = 1\n```"
    assistant.failure("Connection failed")
    assistant.complete()
    assert not assistant.apply.isEnabled()


@patch("rascal2.widgets.model_assistant.requests.post")
def test_streaming_transport(post):
    response = post.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_lines.return_value = [
        ": keepalive",
        'data: {"choices":[{"delta":{"content":"hello "}}]}',
        'data: {"choices":[{"delta":{"content":"world"}}]}',
        "data: [DONE]",
    ]
    worker = CompletionWorker("https://example.com/v1/", "model", "secret", [])
    chunks, errors = [], []
    worker.chunk.connect(chunks.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert chunks == ["hello ", "world"]
    assert not errors
    args, kwargs = post.call_args
    assert args == ("https://example.com/v1/chat/completions",)
    assert kwargs["headers"]["Authorization"] == "Bearer secret"
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == (10, 30)
    assert worker.key == ""


@patch("rascal2.widgets.model_assistant.requests.post")
def test_truncated_stream_is_failure(post):
    response = post.return_value.__enter__.return_value
    response.status_code = 200
    response.iter_lines.return_value = ['data: {"choices":[{"delta":{"content":"partial"}}]}']
    worker = CompletionWorker("https://example.com/v1", "model", "", [])
    errors = []
    worker.failed.connect(errors.append)
    worker.run()
    assert errors


@patch("rascal2.widgets.model_assistant.CompletionWorker")
def test_only_explicit_context_sent(worker_class, assistant):
    worker_class.return_value = MagicMock()
    assistant.model.setText("model")
    assistant.prompt.setPlainText("Explain")
    assistant.submit()
    messages = worker_class.call_args.args[3]
    assert assistant.editor.text() not in messages[1]["content"]
    assert "User-shared code" not in messages[1]["content"]


@patch("rascal2.widgets.model_assistant.CompletionWorker")
def test_insecure_remote_provider_rejected(worker_class, assistant):
    assistant.endpoint.setText("http://remote.example/v1")
    assistant.submit()
    worker_class.assert_not_called()
    assert "HTTPS" in assistant.status.text()


def test_real_streaming_request_and_apply(assistant):
    """Exercise the real worker, HTTP transport, queued signals and review flow."""
    import json
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from PyQt6 import QtTest

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for content in ["A replacement:\n```python\n", "def model():\n    return 3\n```\n"]:
                event = {"choices": [{"delta": {"content": content}}]}
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assistant.endpoint.setText(f"http://127.0.0.1:{server.server_port}/v1")
        assistant.model.setText("test-model")
        assistant.key.clear()
        assistant.prompt.setPlainText("Change the return value")
        assistant.context.setCurrentIndex(2)
        assistant.submit()
        deadline = time.monotonic() + 5
        while assistant.worker is not None and time.monotonic() < deadline:
            QtTest.QTest.qWait(10)
        assert assistant.worker is None
        assert received[0][0] == "/v1/chat/completions"
        assert "return 1" in received[0][1]["messages"][1]["content"]
        assert assistant.apply.isEnabled(), assistant.status.text()
        assistant.apply.click()
        assert "return 3" in assistant.editor.text()
    finally:
        if assistant.worker is not None:
            assistant.stop()
            assistant.worker.wait(35000)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_cancel_discards_late_chunks_and_proposal(assistant):
    worker = MagicMock()
    worker.isRunning.return_value = True
    assistant.worker = worker
    assistant.stop()
    worker.requestInterruption.assert_called_once()
    assistant.receive("```python\nx = 3\n```")
    assistant.complete()
    assert assistant.response == ""
    assert not assistant.apply.isEnabled()
    assert "Cancelled" in assistant.status.text()
