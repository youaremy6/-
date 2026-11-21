"""Phrase pack, health, media signing and record deletion (spec 5.4, 6.2, 8.2)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.helpers import pcm_bytes, signed_path, upload


def test_phrase_pack_lists_all_scenarios(client):
    response = client.get("/api/v1/phrases")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 27
    assert body["draftCount"] == 27
    scenarios = {item["scenario"] for item in body["phrases"]}
    assert scenarios == {"medical", "transport", "market", "help"}
    for item in body["phrases"]:
        assert item["mandarin"] and item["lanzhou"]
        assert item["reviewStatus"] == "draft"
        assert item["mandarinAudio"]["url"]
        assert item["lanzhouAudio"]["url"]
    assert "母语者" in body["reviewPolicy"]


def test_phrase_pack_filter(client):
    response = client.get("/api/v1/phrases", params={"scenario": "market"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 6
    assert all(item["scenario"] == "market" for item in body["phrases"])


def test_phrase_pack_invalid_scenario(client):
    response = client.get("/api/v1/phrases", params={"scenario": "hospital"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_scenario"


def test_phrase_audio_is_publicly_playable(client):
    body = client.get("/api/v1/phrases").json()
    url = body["phrases"][0]["mandarinAudio"]["url"]
    response = client.get(signed_path(url))
    assert response.status_code == 200
    assert len(response.content) > 1000


def test_health_reports_mock_dependencies_without_secrets(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dialect"].startswith("lanzhou")
    for name in ("asr", "llm", "tts", "storage", "phrases"):
        assert name in body["dependencies"]
        assert body["dependencies"][name]["mode"] in {"mock", "live", "error", "misconfigured"}
    assert body["dependencies"]["asr"]["mode"] == "mock"
    assert body["dependencies"]["storage"]["ok"] is True
    assert body["dependencies"]["phrases"]["ok"] is True
    assert body["limits"]["phraseCount"] == 27
    text = response.text
    for marker in ("api_key", "api_secret", "xf_app_id", "llm_api_key"):
        assert marker not in text


def test_health_never_echoes_configured_secrets(tmp_path):
    settings = Settings(
        env="test",
        provider_mode="auto",
        media_dir=tmp_path / "media",
        phrase_asset_dir=tmp_path.parent / "missing-pack",
        public_base_url="http://testserver",
        xf_app_id="APPID",
        xf_api_key="KEY-VALUE",
        xf_api_secret="SUPER-SECRET-VALUE",
        xf_accent_gansu="accent-token",
        llm_base_url="https://example.invalid/v1",
        llm_api_key="LLM-SECRET-VALUE",
        llm_model="test-model",
    )
    own_app = create_app(settings)
    with TestClient(own_app) as own_client:
        response = own_client.get("/api/v1/health")
        assert response.status_code == 200
        text = response.text
        assert "SUPER-SECRET-VALUE" not in text
        assert "LLM-SECRET-VALUE" not in text
        assert "KEY-VALUE" not in text


def test_media_rejects_bad_signature(client):
    response = client.get("/media/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.wav?exp=9999999999&sig=deadbeef")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "media_forbidden"


def test_media_rejects_expired_link(client, app):
    from urllib.parse import parse_qs, urlencode, urlparse

    container = app.state.container
    key = container.media.put(b"RIFF0000WAVE", ".wav")
    url = container.media.sign(key, ttl_seconds=60)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params["exp"] = ["1"]
    expired = f"{parsed.path}?{urlencode({k: v[0] for k, v in params.items()})}"
    assert client.get(expired).status_code == 403


def test_delete_record_removes_audio(client, app):
    response = upload(client, pcm_bytes(1.0), requestId="req_delete_01")
    assert response.status_code == 200
    body = response.json()
    container = app.state.container
    assert len(list(container.media.media_dir.iterdir())) >= 1

    deleted = client.delete("/api/v1/records/req_delete_01")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    assert client.get(signed_path(body["outputAudioUrl"])).status_code == 404
    assert client.delete("/api/v1/records/req_delete_01").status_code == 404


def test_phrase_pack_file_matches_source():
    from pathlib import Path

    from app.services.phrases import PhraseRepository

    repo_root = Path(__file__).resolve().parents[2]
    pack_dir = repo_root / "assets" / "phrases"
    repo = PhraseRepository(
        pack_path=pack_dir / "phrases.json",
        asset_dir=pack_dir,
        public_base_url="http://testserver",
    )
    assert repo.loaded
    assert len(repo.all()) == 27
    assert repo.find_by_text("大夫，我脑壳有点晕。", "lanzhou") is not None
    assert repo.find_by_text("医生，我有点头晕。", "mandarin") is not None
    raw = json.loads((pack_dir / "phrases.json").read_text(encoding="utf-8"))
    assert raw["phrases"][0]["lanzhouAudio"]["kind"] == "placeholder"
