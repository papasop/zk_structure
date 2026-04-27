"""Minimal local wallet web page."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from structural_crypto.ledger.blockchain import Blockchain
from structural_crypto.node import Wallet


def wallet_page_data(chain: Blockchain, wallet: Wallet) -> dict:
    return {
        "wallet": wallet.to_dict(),
        "balance": chain.balances().get(wallet.address, 0),
        "frontier": list(chain.frontier),
        "confirmed_order": chain.confirmed_order(),
        "virtual_order": chain.virtual_order(),
        "confirmed_rewards": chain.confirmed_reward_totals(),
    }


def render_wallet_page(chain: Blockchain, wallet: Wallet) -> str:
    data = wallet_page_data(chain, wallet)
    mnemonic = html.escape(data["wallet"]["mnemonic"])
    address = html.escape(data["wallet"]["address"])
    name = html.escape(data["wallet"]["name"])
    summary_json = html.escape(json.dumps(data, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PoCT Wallet</title>
  <style>
    :root {{
      --bg: #f5f0e8;
      --ink: #1f2a1f;
      --card: #fffaf2;
      --accent: #246a5a;
      --muted: #6a716a;
      --line: #d8cfbf;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      background: radial-gradient(circle at top, #fffdf8 0, var(--bg) 55%, #ebe1d2 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 920px;
      margin: 40px auto;
      padding: 0 20px 40px;
    }}
    .hero {{
      padding: 24px 28px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: linear-gradient(135deg, rgba(255,250,242,0.95), rgba(240,247,243,0.95));
      box-shadow: 0 18px 50px rgba(54, 61, 49, 0.08);
    }}
    .eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.16em;
      font-size: 12px;
      color: var(--accent);
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0;
      font-size: 40px;
      line-height: 1.05;
    }}
    .sub {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 16px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-top: 18px;
    }}
    .card {{
      padding: 18px;
      border-radius: 16px;
      background: var(--card);
      border: 1px solid var(--line);
    }}
    .label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .value {{
      font-size: 16px;
      word-break: break-word;
    }}
    .big {{
      font-size: 34px;
      color: var(--accent);
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 13px;
      line-height: 1.45;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">PoCT Wallet</div>
      <h1>{name}</h1>
      <div class="sub">Minimal local wallet page for your current chain state.</div>
      <div class="grid">
        <div class="card">
          <div class="label">Address</div>
          <div class="value">{address}</div>
        </div>
        <div class="card">
          <div class="label">Balance</div>
          <div class="value big">{data["balance"]}</div>
        </div>
        <div class="card">
          <div class="label">Confirmed Blocks</div>
          <div class="value">{len(data["confirmed_order"])}</div>
        </div>
        <div class="card">
          <div class="label">Frontier Size</div>
          <div class="value">{len(data["frontier"])}</div>
        </div>
      </div>
    </section>
    <section class="grid" style="margin-top: 16px;">
      <div class="card">
        <div class="label">Mnemonic</div>
        <div class="value">{mnemonic}</div>
      </div>
      <div class="card">
        <div class="label">Chain Snapshot</div>
        <pre>{summary_json}</pre>
      </div>
    </section>
  </div>
</body>
</html>"""


def serve_wallet_page(
    chain_path: str | Path,
    wallet_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    chain_path = Path(chain_path)
    wallet_path = Path(wallet_path)

    def page_data() -> dict:
        chain = Blockchain.load_state(chain_path)
        wallet = Wallet.load(wallet_path)
        return wallet_page_data(chain, wallet)

    def page_html() -> str:
        chain = Blockchain.load_state(chain_path)
        wallet = Wallet.load(wallet_path)
        return render_wallet_page(chain, wallet)

    class WalletPageHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                body = page_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/state":
                body = json.dumps(page_data(), indent=2, sort_keys=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), WalletPageHandler)
    print(f"http://{host}:{port}")
    server.serve_forever()
