"""Network errors stay useful without echoing signed URLs or proxy credentials."""
from __future__ import annotations

import logging

import pytest

from pet import voice_chime_service as service
from pet.voice_chime import DEFAULT_VOICE


class HandshakeRejected(Exception):
    status = 403


@pytest.mark.parametrize("error,expected", [
    (HandshakeRejected("wss://host/?token=PRIVATE_TOKEN http://user:PRIVATE_PASSWORD@proxy"), "403"),
    (TimeoutError("request included PRIVATE_TOKEN"), "超时"),
    (type("NoAudioReceived", (Exception,), {})("PRIVATE_TOKEN"), "未返回音频"),
    (type("ClientProxyConnectionError", (Exception,), {})("PRIVATE_PASSWORD"), "代理"),
])
def test_worker_sanitizes_failures_and_discards_partial_audio(tmp_path, monkeypatch, caplog, error, expected):
    monkeypatch.setattr(service, "refresh_voice_list", lambda: None)
    results = []
    async def fail(worker, voice):
        worker._temp_path.write_bytes(b"partial")
        raise error
    monkeypatch.setattr(service._TTSWorker, "_synthesize", fail)
    caplog.set_level(logging.DEBUG)
    worker = service._TTSWorker("private speech", DEFAULT_VOICE, "+0%", "+0Hz",
                                tmp_path / "test.mp3", lambda *args: results.append(args))
    worker.run()
    assert len(results) == 1
    message = results[0][2]
    assert expected in message[:40]
    assert "PRIVATE_TOKEN" not in message + caplog.text
    assert "PRIVATE_PASSWORD" not in message + caplog.text
    assert "version=" in caplog.text and "route=" in caplog.text
    assert not (tmp_path / "test.mp3").exists()
    assert not list(tmp_path.glob("*.part"))
