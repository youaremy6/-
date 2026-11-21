"""End-to-end smoke test against a running server.

    python scripts/smoke_test.py [base_url]

Exercises health, phrases, both translation directions, signed media and the
delete-record flow.  Exits non-zero on the first hard failure.
"""

from __future__ import annotations

import sys
import uuid

import httpx


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
    client = httpx.Client(base_url=base, timeout=30.0)

    health = client.get("/api/v1/health")
    health.raise_for_status()
    body = health.json()
    print(f"health: {body['status']} asr={body['dependencies']['asr']['mode']} "
          f"llm={body['dependencies']['llm']['mode']} tts={body['dependencies']['tts']['mode']} "
          f"phrases={body['limits']['phraseCount']}")

    phrases = client.get("/api/v1/phrases", params={"scenario": "medical"})
    phrases.raise_for_status()
    pack = phrases.json()
    assert pack["count"] >= 4, pack["count"]
    first = pack["phrases"][0]
    audio = client.get(first["mandarinAudio"]["url"].replace(base, ""))
    assert audio.status_code == 200 and len(audio.content) > 1000
    print(f"phrases: {pack['count']} medical, audio_bytes={len(audio.content)}")

    pcm = (1200).to_bytes(2, "little", signed=True) * 16_000
    request_id = f"req_smoke_{uuid.uuid4().hex[:10]}"
    audio_resp = client.post(
        "/api/v1/translate/audio",
        files={"audio": ("speech.pcm", pcm, "application/octet-stream")},
        data={"requestId": request_id, "dialectId": "lanzhou", "scenario": "medical"},
    )
    audio_resp.raise_for_status()
    result = audio_resp.json()
    assert result["asrText"] and result["outputText"]
    print(f"audio->text: asr={result['asrText']!r} out={result['outputText']!r} "
          f"audio={'yes' if result['outputAudioUrl'] else 'no'} warnings={result['warnings']}")
    if result["outputAudioUrl"]:
        media = client.get(result["outputAudioUrl"].replace(base, ""))
        assert media.status_code == 200, media.text
        print(f"media: {len(media.content)} bytes {media.headers.get('content-type')}")

    text_request_id = f"req_smoke_{uuid.uuid4().hex[:10]}"
    text_resp = client.post(
        "/api/v1/translate/text",
        json={
            "requestId": text_request_id,
            "direction": "mandarin_to_dialect",
            "dialectId": "lanzhou",
            "scenario": "medical",
            "text": "医生，我有点头晕。",
        },
    )
    text_resp.raise_for_status()
    text_result = text_resp.json()
    assert text_result["dialectText"]
    print(f"text->dialect: {text_result['dialectText']!r} "
          f"tts={text_result['ttsProvider']} warnings={text_result['warnings']}")

    edit_resp = client.post(
        "/api/v1/translate/dialect-text",
        json={
            "requestId": f"req_smoke_{uuid.uuid4().hex[:10]}",
            "dialectId": "lanzhou",
            "scenario": "medical",
            "text": "大夫，我脑壳有点晕。",
        },
    )
    edit_resp.raise_for_status()
    assert edit_resp.json()["normalizedText"]
    print(f"edit: {edit_resp.json()['normalizedText']!r}")

    deleted = client.delete(f"/api/v1/records/{request_id}")
    assert deleted.status_code == 200, deleted.text
    print("delete record: ok")

    client.close()
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
