"""Unit tests for the 讯飞 business parameters (no network calls)."""

from __future__ import annotations

from app.config import Settings
from app.services.asr_xfyun import XfyunASR


def _settings(**overrides) -> Settings:
    payload = {
        "xf_app_id": "appid",
        "xf_api_key": "key",
        "xf_api_secret": "secret",
        "xf_accent_gansu": "gansu-value-from-console",
        "xf_domain": "xfime-mianqie",
    }
    payload.update(overrides)
    return Settings(**payload)


def test_dialect_business_params_use_eos_and_no_dwa():
    provider = XfyunASR(_settings())
    business = provider._business()
    assert business["language"] == "zh_cn"
    assert business["domain"] == "xfime-mianqie"
    assert business["accent"] == "gansu-value-from-console"
    assert business["eos"] == 5000
    assert "vad_eos" not in business
    assert "dwa" not in business


def test_mandarin_business_params_enable_wpgs():
    provider = XfyunASR(_settings(xf_domain="iat", xf_accent_gansu="mandarin"))
    business = provider._business()
    assert business["dwa"] == "wpgs"
    assert business["accent"] == "mandarin"


def test_asr_live_ready_requires_all_four_values():
    assert _settings().asr_live_ready() is True
    assert _settings(xf_accent_gansu="").asr_live_ready() is False
    assert _settings(xf_api_secret="").asr_live_ready() is False
