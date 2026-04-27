"""Minimal local wallet web page."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.ledger.blockchain import Blockchain
from structural_crypto.node import Wallet


def wallet_page_data(chain: Blockchain, wallet: Wallet) -> dict:
    address = wallet.address
    balances = chain.balances()
    history = []
    for block in chain.blocks:
        for tx in block.transactions:
            outputs = tx.outputs or []
            sent = tx.sender == address
            received_amount = sum(output.amount for output in outputs if output.recipient == address)
            if not sent and received_amount == 0:
                continue
            sent_amount = sum(output.amount for output in outputs if output.recipient != address) if sent else 0
            history.append(
                {
                    "txid": tx.txid,
                    "block_index": block.index,
                    "direction": "sent" if sent else "received",
                    "amount": sent_amount if sent else received_amount,
                    "sequence": tx.sequence,
                    "counterparty": (
                        ", ".join(output.recipient for output in outputs if output.recipient != address)
                        if sent
                        else tx.sender
                    ),
                }
            )
    history.reverse()
    return {
        "wallet": wallet.to_dict(),
        "balance": balances.get(address, 0),
        "frontier": list(chain.frontier),
        "confirmed_order": chain.confirmed_order(),
        "virtual_order": chain.virtual_order(),
        "confirmed_rewards": chain.confirmed_reward_totals(),
        "history": history,
        "blocks": len(chain.blocks),
        "utxos": len(chain.utxos),
    }


def faucet_wallet(chain_path: str | Path, wallet_path: str | Path, amount: int) -> dict:
    chain = Blockchain.load_state(chain_path)
    wallet = Wallet.load(wallet_path)
    tx = chain.faucet(wallet.address, amount)
    chain.save_state(chain_path)
    return {"ok": True, "txid": tx.txid, "amount": amount, "address": wallet.address}


def send_from_wallet(chain_path: str | Path, wallet_path: str | Path, recipient: str, amount: int) -> dict:
    chain = Blockchain.load_state(chain_path)
    wallet = Wallet.load(wallet_path)
    policy = PolicyCommitment.from_values(
        epsilon=10.0,
        max_amount=amount,
        allowed_recipients=[recipient],
    )
    tx = chain.build_transaction(
        key=wallet.key,
        recipients=[(recipient, amount)],
        policy=policy,
    )
    chain.add_transaction(tx, signer_seed=wallet.seed)
    chain.save_state(chain_path)
    return {"ok": True, "txid": tx.txid, "sender": wallet.address, "recipient": recipient, "amount": amount}


def produce_for_wallet(chain_path: str | Path, wallet_path: str | Path) -> dict:
    chain = Blockchain.load_state(chain_path)
    wallet = Wallet.load(wallet_path)
    block = chain.produce_block(wallet.address)
    chain.save_state(chain_path)
    return {"ok": True, "block_hash": block.block_hash, "producer": wallet.address}


def render_wallet_page(chain: Blockchain, wallet: Wallet) -> str:
    data = wallet_page_data(chain, wallet)
    summary_json = html.escape(json.dumps(data, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BBS-DAG Wallet</title>
  <style>
    :root {{
      --bg: #f5f0e8; --ink: #1f2a1f; --card: #fffaf2; --accent: #246a5a; --muted: #6a716a; --line: #d8cfbf;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Georgia, "Iowan Old Style", serif; background: radial-gradient(circle at top, #fffdf8 0, var(--bg) 55%, #ebe1d2 100%); color: var(--ink); }}
    .wrap {{ max-width: 1120px; margin: 32px auto 64px; padding: 0 18px; }}
    .hero, .card {{ border: 1px solid var(--line); border-radius: 18px; background: var(--card); box-shadow: 0 18px 45px rgba(36,48,39,.08); }}
    .hero {{ padding: 24px 28px; background: linear-gradient(135deg, rgba(255,250,242,.96), rgba(240,247,243,.96)); }}
    .eyebrow {{ text-transform: uppercase; letter-spacing: .16em; font-size: 12px; color: var(--accent); margin-bottom: 10px; }}
    h1 {{ margin: 0; font-size: 42px; line-height: 1.05; }}
    .sub {{ margin-top: 10px; color: var(--muted); font-size: 16px; line-height: 1.45; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 18px; }}
    .grid-two {{ display: grid; grid-template-columns: minmax(320px, 1.05fr) minmax(280px, .95fr); gap: 16px; margin-top: 18px; }}
    .card {{ padding: 18px; }}
    .label {{ text-transform: uppercase; letter-spacing: .12em; font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
    .section-title {{ margin: 0 0 10px; font-size: 22px; }}
    .value {{ font-size: 15px; line-height: 1.5; word-break: break-word; }}
    .big {{ font-size: 34px; color: var(--accent); line-height: 1; }}
    .hint {{ color: var(--muted); font-size: 13px; line-height: 1.45; }}
    input {{ width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--line); background: #fffdf9; color: var(--ink); font: inherit; }}
    .row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }}
    .stack {{ display: flex; flex-direction: column; gap: 12px; }}
    button {{ border: 1px solid var(--line); border-radius: 999px; padding: 10px 14px; font: inherit; cursor: pointer; background: white; color: var(--ink); }}
    button.primary {{ background: var(--accent); color: white; border-color: var(--accent); }}
    button.secondary {{ background: #f8f3ea; }}
    pre, .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.45; background: #fbf8f1; padding: 12px; border-radius: 12px; border: 1px solid var(--line); }}
    .pill {{ display: inline-block; padding: 6px 10px; border-radius: 999px; background: #ecf6f2; color: var(--accent); font-size: 13px; margin-right: 8px; margin-bottom: 8px; }}
    .status {{ min-height: 20px; color: var(--accent); font-size: 13px; }}
    .tx-list {{ display: flex; flex-direction: column; gap: 10px; }}
    .tx-item {{ border: 1px solid var(--line); border-radius: 12px; background: #fbf8f1; padding: 12px; }}
    .tx-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; color: var(--muted); font-size: 13px; }}
    .empty {{ color: var(--muted); font-size: 14px; }}
    @media (max-width: 860px) {{ .grid-two {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">BBS-DAG</div>
      <h1>BBS-DAG AI Agent Wallet Blockchain</h1>
      <div class="sub">Interactive local wallet page for BBS-DAG, a wallet blockchain built for AI agents, backed by your current chain state file.</div>
    </section>

    <section class="grid">
      <div class="card"><div class="label">Address</div><div class="value mono" id="address">{html.escape(data["wallet"]["address"])}</div></div>
      <div class="card"><div class="label">Balance</div><div class="big" id="balance">{data["balance"]}</div></div>
      <div class="card"><div class="label">State Summary</div><div class="value"><span class="pill">frontier <span id="frontierCount">{len(data["frontier"])}</span></span><span class="pill">blocks <span id="blockCount">{data["blocks"]}</span></span><span class="pill">utxos <span id="utxoCount">{data["utxos"]}</span></span></div></div>
    </section>

    <section class="grid-two">
      <div class="card">
        <div class="label">Actions</div>
        <h2 class="section-title">Faucet, Send, Produce</h2>
        <div class="stack">
          <div>
            <div class="hint">Faucet amount</div>
            <input id="faucetAmount" type="text" value="10">
            <div class="row"><button class="primary" id="runFaucet">Request Test Coins</button></div>
          </div>
          <div>
            <div class="hint">Send transaction</div>
            <input id="sendTo" type="text" placeholder="Recipient address">
            <input id="sendAmount" type="text" placeholder="Amount">
            <div class="row">
              <button class="primary" id="runSend">Send</button>
              <button class="secondary" id="copyAddress">Copy Address</button>
            </div>
          </div>
          <div>
            <div class="hint">Produce next block</div>
            <div class="row"><button class="primary" id="runProduce">Produce Block</button></div>
          </div>
          <div class="status" id="actionStatus"></div>
        </div>
      </div>

      <div class="card">
        <div class="label">Wallet Secret</div>
        <h2 class="section-title">Mnemonic</h2>
        <pre>{html.escape(data["wallet"]["mnemonic"])}</pre>
        <div class="hint" style="margin-top: 10px;">This local page can act because it is backed by your local wallet file and chain state file.</div>
      </div>
    </section>

    <section class="grid-two">
      <div class="card">
        <div class="label">History</div>
        <h2 class="section-title">Transaction History</h2>
        <div id="historyList" class="tx-list">
          {''.join(_history_html(item) for item in data["history"]) or '<div class="empty">No transactions yet.</div>'}
        </div>
      </div>
      <div class="card">
        <div class="label">Chain Snapshot</div>
        <h2 class="section-title">Current State</h2>
        <pre id="chainSnapshot">{summary_json}</pre>
      </div>
    </section>
  </div>

  <script>
    function setState(data) {{
      document.getElementById("address").textContent = data.wallet.address;
      document.getElementById("balance").textContent = String(data.balance);
      document.getElementById("frontierCount").textContent = String(data.frontier.length);
      document.getElementById("blockCount").textContent = String(data.blocks);
      document.getElementById("utxos").textContent = String(data.utxos);
    }}

    function renderHistory(history) {{
      const target = document.getElementById("historyList");
      if (!history.length) {{
        target.innerHTML = '<div class="empty">No transactions yet.</div>';
        return;
      }}
      target.innerHTML = history.map((entry) => `
        <div class="tx-item">
          <div><strong>${{entry.direction === "sent" ? "Sent" : "Received"}}</strong> ${{entry.amount}}</div>
          <div class="tx-meta">
            <span>block ${{entry.block_index}}</span>
            <span>sequence ${{entry.sequence}}</span>
            <span>counterparty ${{entry.counterparty || "n/a"}}</span>
          </div>
          <div class="tx-meta"><span class="mono">${{entry.txid}}</span></div>
        </div>
      `).join('');
    }}

    async function refreshState(message = "") {{
      const response = await fetch('/api/state');
      const data = await response.json();
      document.getElementById('address').textContent = data.wallet.address;
      document.getElementById('balance').textContent = String(data.balance);
      document.getElementById('frontierCount').textContent = String(data.frontier.length);
      document.getElementById('blockCount').textContent = String(data.blocks);
      document.getElementById('utxoCount').textContent = String(data.utxos);
      document.getElementById('chainSnapshot').textContent = JSON.stringify(data, null, 2);
      renderHistory(data.history || []);
      document.getElementById('actionStatus').textContent = message;
    }}

    async function postJson(path, payload) {{
      const response = await fetch(path, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      return response.json();
    }}

    document.getElementById('copyAddress').addEventListener('click', async () => {{
      await navigator.clipboard.writeText(document.getElementById('address').textContent);
      document.getElementById('actionStatus').textContent = 'Address copied.';
    }});

    document.getElementById('runFaucet').addEventListener('click', async () => {{
      const amount = Number(document.getElementById('faucetAmount').value.trim());
      const result = await postJson('/api/faucet', {{ amount }});
      await refreshState(result.ok ? `Faucet tx ${{result.txid}}` : (result.error || 'Faucet failed'));
    }});

    document.getElementById('runSend').addEventListener('click', async () => {{
      const to = document.getElementById('sendTo').value.trim();
      const amount = Number(document.getElementById('sendAmount').value.trim());
      const result = await postJson('/api/send', {{ to, amount }});
      await refreshState(result.ok ? `Send tx ${{result.txid}}` : (result.error || 'Send failed'));
    }});

    document.getElementById('runProduce').addEventListener('click', async () => {{
      const result = await postJson('/api/produce', {{}});
      await refreshState(result.ok ? `Produced block ${{result.block_hash}}` : (result.error || 'Produce failed'));
    }});
  </script>
</body>
</html>"""


def _history_html(item: dict) -> str:
    return (
        '<div class="tx-item">'
        f'<div><strong>{"Sent" if item["direction"] == "sent" else "Received"}</strong> {item["amount"]}</div>'
        '<div class="tx-meta">'
        f'<span>block {item["block_index"]}</span>'
        f'<span>sequence {item["sequence"]}</span>'
        f'<span>counterparty {html.escape(item["counterparty"] or "n/a")}</span>'
        "</div>"
        f'<div class="tx-meta"><span class="mono">{html.escape(item["txid"])}</span></div>'
        "</div>"
    )


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
        def _write_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
                self._write_json(page_data())
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            try:
                if self.path == "/api/faucet":
                    result = faucet_wallet(chain_path, wallet_path, int(payload["amount"]))
                    self._write_json(result)
                    return
                if self.path == "/api/send":
                    result = send_from_wallet(
                        chain_path,
                        wallet_path,
                        str(payload["to"]),
                        int(payload["amount"]),
                    )
                    self._write_json(result)
                    return
                if self.path == "/api/produce":
                    result = produce_for_wallet(chain_path, wallet_path)
                    self._write_json(result)
                    return
            except Exception as exc:  # pragma: no cover - exercised via manual page interactions
                self._write_json({"ok": False, "error": str(exc)}, status=400)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer((host, port), WalletPageHandler)
    print(f"http://{host}:{port}")
    server.serve_forever()
