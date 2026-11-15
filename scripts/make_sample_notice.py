"""Make the demo's sample notice: assets/notice/sample_notice.png (+ .pdf), per docs/VOICE_AND_NOTICE.md 11.2.

    python scripts/make_sample_notice.py

A plain typed letter with the 11.2 fields; the amount is M001's gross UPI receipts for the period from
data/demo/notice_numbers.json. Watermarked "SAMPLE FOR DEMONSTRATION. NOT A REAL NOTICE." on every edge; no real
department's name, logo or emblem; the seal is a box that says SAMPLE. Rendered by headless Chrome (no image library
needed). Afterwards run `python -m backend.app.sarvam.register_demo_clips` so demo_key sample_notice_v1 is bound to it.
"""
from __future__ import annotations

import asyncio
import base64
import html
import json
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import websockets

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "assets" / "notice"
NUMBERS = REPO / "data" / "demo" / "notice_numbers.json"
CHROMES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           "/usr/bin/google-chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
WARN = "SAMPLE FOR DEMONSTRATION. NOT A REAL NOTICE."


def dmy(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


def page(amount: str, start: str, end: str) -> str:
    e = html.escape
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 0; }}
  html, body {{ margin: 0; background: #fff; }}
  body {{ width: 794px; height: 1123px; position: relative; overflow: hidden; color: #111;
         font: 17px/1.55 "Times New Roman", Times, serif; }}
  .mark {{ position: absolute; left: 50%; top: 52%; transform: translate(-50%, -50%) rotate(-30deg); white-space: nowrap;
          font: 700 130px/1 Arial, sans-serif; letter-spacing: 12px; color: rgba(0, 0, 0, 0.06); }}
  .band {{ position: absolute; left: 0; right: 0; padding: 7px 0; text-align: center; background: #b3261e; color: #fff;
          font: 700 15px/1.2 Arial, sans-serif; letter-spacing: 1.5px; }}
  .band.top {{ top: 0; }} .band.bottom {{ bottom: 0; }}
  .sheet {{ position: absolute; inset: 64px 72px 70px; }}
  .head {{ text-align: center; border-bottom: 2px solid #111; padding-bottom: 12px; }}
  .head b {{ display: block; font-size: 21px; letter-spacing: 1px; }}
  .meta {{ display: flex; justify-content: space-between; margin: 18px 0 20px; }}
  .to p, .sign p {{ margin: 0; }}
  .subject {{ margin: 22px 0 18px; font-weight: 700; }}
  p {{ margin: 0 0 14px; }}
  .nb {{ white-space: nowrap; }} /* a date or amount never breaks across lines (OCR spans) */
  ol {{ margin: 0 0 14px; padding-left: 26px; }}
  .foot {{ display: flex; justify-content: space-between; align-items: flex-end; margin-top: 34px; }}
  .seal {{ width: 132px; height: 132px; border: 3px double #b3261e; border-radius: 50%; display: grid; place-items: center;
          color: #b3261e; font: 700 22px/1 Arial, sans-serif; letter-spacing: 3px; transform: rotate(-12deg); }}
  .sign {{ text-align: right; }}
  .note {{ position: absolute; left: 0; right: 0; bottom: 0; font: 12.5px/1.45 Arial, sans-serif; color: #444;
          border-top: 1px solid #999; padding-top: 8px; }}
</style></head><body>
  <div class="mark">SAMPLE</div>
  <div class="band top">{e(WARN)}</div>
  <div class="sheet">
    <div class="head"><b>OFFICE OF THE ASSISTANT COMMISSIONER</b>(Sample) Division, Chennai</div>
    <div class="meta"><span>Reference: SAMPLE/2026/0417</span><span>Date of issue: 05-11-2026</span></div>
    <div class="to"><p>To</p><p>Murugan</p><p>Murugan Kaaikari Kadai</p><p>Chennai</p></div>
    <p class="subject">Subject: Intimation regarding receipts through UPI (SAMPLE)</p>
    <p>Sir/Madam,</p>
    <p>Receipts of <span class="nb">{e(amount)}</span> through UPI were observed in your account for <span class="nb">{e(start)}</span> to <span class="nb">{e(end)}</span>.</p>
    <p>Explain the nature of these receipts and the goods supplied, and whether registration is required.</p>
    <p>Documents requested:</p>
    <ol><li>Details of UPI receipts</li><li>Nature of goods supplied</li></ol>
    <p>Reply by: 30-11-2026</p>
    <div class="foot">
      <div class="seal">SAMPLE</div>
      <div class="sign"><p>Assistant Commissioner (Sample)</p><p>Office of the Assistant Commissioner, (Sample) Division, Chennai</p></div>
    </div>
    <div class="note">{e(WARN)} Made for the Naanayam hackathon demo with synthetic data. Not issued by any government
      office; the names, office, reference number and amount are invented for the demo.</div>
  </div>
  <div class="band bottom">{e(WARN)}</div>
</body></html>"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def render(port: int, src: Path) -> tuple[bytes, bytes]:
    t = next(t for t in httpx.get(f"http://127.0.0.1:{port}/json").json() if t["type"] == "page")
    async with websockets.connect(t["webSocketDebuggerUrl"], max_size=100_000_000) as ws:
        n = 0

        async def call(method, **params):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == n:
                    if "error" in m:
                        raise RuntimeError(m["error"])
                    return m.get("result", {})

        await call("Page.enable")
        await call("Emulation.setDeviceMetricsOverride", width=794, height=1123, deviceScaleFactor=2, mobile=False)
        await call("Page.navigate", url=src.as_uri())
        await asyncio.sleep(1.5)
        png = await call("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": 794, "height": 1123, "scale": 1})
        pdf = await call("Page.printToPDF", paperWidth=8.27, paperHeight=11.69, marginTop=0, marginBottom=0, marginLeft=0,
                         marginRight=0, printBackground=True, preferCSSPageSize=True)
        return base64.b64decode(png["data"]), base64.b64decode(pdf["data"])


def main() -> None:
    numbers = json.loads(NUMBERS.read_text(encoding="utf-8"))
    amount = numbers["amount_questioned_display"]  # e.g. ₹8,42,162 (backend money format)
    chrome = next((c for c in CHROMES if Path(c).exists()), shutil.which("chrome") or shutil.which("google-chrome"))
    if not chrome:
        raise SystemExit("Chrome not found")
    tmp = Path(tempfile.mkdtemp(prefix="naanayam_notice_"))
    src = tmp / "notice.html"
    src.write_text(page(amount, dmy(numbers["period_start"]), dmy(numbers["period_end"])), encoding="utf-8")
    port = free_port()
    proc = subprocess.Popen([chrome, "--headless=new", "--mute-audio", "--disable-gpu", "--hide-scrollbars",
                             f"--remote-debugging-port={port}", f"--user-data-dir={tmp / 'chrome'}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(80):
            try:
                httpx.get(f"http://127.0.0.1:{port}/json/version")
                break
            except httpx.HTTPError:
                time.sleep(0.25)
        png, pdf = asyncio.run(render(port, src))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample_notice.png").write_bytes(png)
    (OUT / "sample_notice.pdf").write_bytes(pdf)
    print(f"wrote {OUT / 'sample_notice.png'} ({len(png):,} bytes) and sample_notice.pdf ({len(pdf):,} bytes); amount {amount}")
    print("now run: python -m backend.app.sarvam.register_demo_clips")


if __name__ == "__main__":
    main()
