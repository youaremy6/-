"""The browser demo page must ship with the app and use the same API."""

from __future__ import annotations


def test_demo_page_is_served(client):
    response = client.get("/demo")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "getUserMedia" in html
    assert "/api/v1/translate/audio" in html
    assert "按住说一句兰州话" in html
    assert "组撒" not in html  # data comes from the API, not hard-coded


def test_root_links_to_demo(client):
    body = client.get("/").json()
    assert body["demo"] == "/demo"
