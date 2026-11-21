"""Verify the browser demo end-to-end with a fake microphone (no human needed).

Requires a headless Chrome started with CDP and fake media flags, e.g.:

  chrome --headless=new --remote-debugging-port=9231 --remote-allow-origins=* \
    --use-fake-ui-for-media-stream --use-fake-device-for-media-stream \
    --autoplay-policy=no-user-gesture-required about:blank

Then:
  python -m uvicorn app.main:app --app-dir server --port 8000
  python scripts/verify_h5.py
  python scripts/verify_h5.py --mode upload   # click the no-mic upload self-test

The fake device produces a tone, so ASR content is whatever the backend
provider returns (mock mode returns a preset sentence).  This script checks
that recording -> WAV encode -> upload -> result card works in a real browser.
"""

from __future__ import annotations

import argparse
import asyncio
import json

import httpx
import websockets

RECORD_SCRIPT = """
(async () => {
  const button = document.getElementById('talk');
  button.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
  await new Promise((resolve) => setTimeout(resolve, 2600));
  button.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true }));
  await new Promise((resolve) => setTimeout(resolve, 5000));
  const card = document.getElementById('resultCard');
  return {
    visible: card && !card.classList.contains('hidden'),
    status: document.getElementById('status').innerText,
    result: document.getElementById('resultBody').innerText,
    banner: document.getElementById('banner').innerText
  };
})()
"""

UPLOAD_SCRIPT = """
(async () => {
  document.getElementById('testUpload').click();
  await new Promise((resolve) => setTimeout(resolve, 10000));
  const card = document.getElementById('resultCard');
  return {
    visible: card && !card.classList.contains('hidden'),
    status: document.getElementById('status').innerText,
    result: document.getElementById('resultBody').innerText,
    banner: document.getElementById('banner').innerText
  };
})()
"""


async def run(port: int, url: str, mode: str = "record") -> int:
    targets = httpx.get(f"http://127.0.0.1:{port}/json/list", timeout=5).json()
    pages = [item for item in targets if item.get("type") == "page"]
    if not pages:
        print("no page target; start Chrome with --remote-debugging-port")
        return 1

    async with websockets.connect(pages[0]["webSocketDebuggerUrl"], max_size=8 * 1024 * 1024) as ws:
        counter = 0

        async def command(method: str, params: dict | None = None) -> dict:
            nonlocal counter
            counter += 1
            await ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
            while True:
                message = json.loads(await ws.recv())
                if message.get("id") == counter:
                    return message

        await command("Page.enable")
        await command("Runtime.enable")
        await command("Page.navigate", {"url": url})
        await asyncio.sleep(2.0)

        evaluation = await command(
            "Runtime.evaluate",
            {
                "expression": RECORD_SCRIPT if mode == "record" else UPLOAD_SCRIPT,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        try:
            value = evaluation["result"]["result"]["value"]
        except (KeyError, TypeError):
            print("evaluate failed:", json.dumps(evaluation, ensure_ascii=False)[:800])
            return 1

        print("status:", value.get("status"))
        print("result:", value.get("result"))
        if not value.get("visible"):
            print("FAILED: result card did not appear")
            return 1
        text = value.get("result") or ""
        if "普通话" not in text and "兰州话" not in text:
            print("FAILED: result card has no translation text")
            return 1
    print("H5 RECORDING OK" if mode == "record" else "H5 UPLOAD TEST OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the H5 demo recording flow")
    parser.add_argument("--port", type=int, default=9231)
    parser.add_argument("--url", default="http://127.0.0.1:8000/demo")
    parser.add_argument("--mode", choices=["record", "upload"], default="record")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.port, args.url, args.mode))
    except Exception as exc:  # noqa: BLE001
        print(f"VERIFY FAILED: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
