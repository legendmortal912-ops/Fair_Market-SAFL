"""
MRPTrap Web Server
==================
Lightweight HTTP server serving the MRPTrap interactive dashboard
and providing real-time API endpoints for Groq AI inference and
empirical simulation replay.
"""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.parse
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from mrptrap.simulator import PRODUCTS, MarketConfig, ONDCLiteSimulator
from mrptrap.agents import SellerAgentRunner
from mrptrap.clamp import strip_mrp, clamp_price, audit_response

WEB_DIR = Path(__file__).parent / "web"
RESULTS_DIR = Path(__file__).parent.parent / "results"


class MRPTrapHandler(BaseHTTPRequestHandler):
    """Handles static web requests and MRPTrap REST API."""

    def _set_headers(self, content_type: str = "application/json", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(status=200)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # ── API Endpoints ─────────────────────────────────────────────────────

        if path == "/api/products":
            prods = [
                {
                    "idx": i,
                    "name": p[0],
                    "category": p[1],
                    "cost": p[2],
                    "competitive_price": p[3],
                }
                for i, p in enumerate(PRODUCTS)
            ]
            self._set_headers("application/json")
            self.wfile.write(json.dumps({"products": prods}).encode("utf-8"))
            return

        elif path == "/api/empirical-data":
            summary_file = RESULTS_DIR / "sweep_summary.json"
            if summary_file.exists():
                data = json.loads(summary_file.read_text(encoding="utf-8"))
            else:
                data = {"status": "no_data"}
            self._set_headers("application/json")
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        elif path == "/api/beckn-sample":
            prod_idx = int(query.get("product", [0])[0])
            mrp_mult = float(query.get("mrp_mult", [1.8])[0])
            clamp = query.get("clamp", ["0"])[0] in ["1", "true", "True"]

            config = MarketConfig(
                product_idx=prod_idx,
                mrp_multiplier=mrp_mult,
                mrp_visible=not clamp,
                n_sellers=3,
                n_rounds=1,
            )
            sim = ONDCLiteSimulator(config)
            prompt = sim.get_seller_context_prompt(0, [])
            if clamp:
                prompt = strip_mrp(prompt)

            payload = {
                "product": sim.product_name,
                "cost": sim.sellers_data[0]["cost"],
                "nash": sim.nash_price(),
                "mrp": sim.mrp,
                "clamp_active": clamp,
                "raw_beckn_price": {
                    "currency": "INR",
                    "value": f"{sim.competitive_price:.2f}",
                    "maximum_value": f"{sim.mrp:.2f}" if not clamp else "[STRIPPED_BY_MRPCLAMP]",
                },
                "prompt_seen_by_llm": prompt,
            }
            self._set_headers("application/json")
            self.wfile.write(json.dumps(payload, indent=2).encode("utf-8"))
            return

        # ── Static Files ──────────────────────────────────────────────────────

        if path == "/" or path == "":
            file_path = WEB_DIR / "index.html"
        else:
            rel = path.lstrip("/")
            file_path = WEB_DIR / rel

        if file_path.exists() and file_path.is_file():
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "text/plain"
            if mime_type.startswith("text/"):
                mime_type += "; charset=utf-8"

            self._set_headers(mime_type)
            self.wfile.write(file_path.read_bytes())
        else:
            self.send_error(HTTPStatus.NOT_FOUND, f"File not found: {path}")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        if path == "/api/run-audit":
            # Live simulation via Groq
            prod_idx = int(req_data.get("product", 0))
            mrp_mult = float(req_data.get("mrp_mult", 1.8))
            n_sellers = int(req_data.get("n_sellers", 3))
            n_rounds = int(req_data.get("n_rounds", 3))
            clamp = bool(req_data.get("clamp", False))
            backend = req_data.get("backend", "groq")
            model = req_data.get("model", "qwen/qwen3.8-27b")

            cfg = MarketConfig(
                product_idx=prod_idx,
                mrp_multiplier=mrp_mult,
                mrp_visible=not clamp,
                n_sellers=n_sellers,
                n_rounds=n_rounds,
            )
            runner = SellerAgentRunner(config=cfg, backend=backend, model=model)
            result = runner.run()

            self._set_headers("application/json")
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        elif path == "/api/live-round":
            # Single round for interactive step-by-step
            prod_idx = int(req_data.get("product", 0))
            mrp_mult = float(req_data.get("mrp_mult", 1.8))
            n_sellers = int(req_data.get("n_sellers", 3))
            clamp = bool(req_data.get("clamp", False))
            history = req_data.get("history", [])

            cfg = MarketConfig(
                product_idx=prod_idx,
                mrp_multiplier=mrp_mult,
                mrp_visible=not clamp,
                n_sellers=n_sellers,
                n_rounds=len(history) + 1,
            )
            runner = SellerAgentRunner(config=cfg, backend="groq", model="qwen/qwen3.8-27b")
            sim = runner.sim

            round_prices = {}
            round_rationales = {}
            round_audits = []

            for s_idx in range(n_sellers):
                sd = sim.sellers_data[s_idx]
                prompt = sim.get_seller_context_prompt(s_idx, history)
                if clamp:
                    prompt = strip_mrp(prompt)

                try:
                    raw = runner._call_llm(prompt)
                    price, rationale = runner._parse_price_response(raw) if hasattr(runner, "_parse_price_response") else (sd["competitive_price"], "parse")
                except Exception as e:
                    price, rationale = sd["competitive_price"], str(e)

                clamped_price, was_clamped = clamp_price(price, sim.mrp, sd["cost"])
                audit = audit_response(price, sim.mrp, sd["cost"], rationale)
                audit.update({
                    "seller": sd["name"],
                    "round": len(history) + 1,
                    "was_clamped": was_clamped,
                })
                round_prices[str(s_idx)] = clamped_price
                round_rationales[str(s_idx)] = rationale
                round_audits.append(audit)

            prices_list = list(round_prices.values())
            res = {
                "round": len(history) + 1,
                "prices": round_prices,
                "rationales": round_rationales,
                "avg_price": round(sum(prices_list) / len(prices_list), 2),
                "collusion_index": round(sim.bertrand_collusion_index(prices_list), 4),
                "bunching_score": round(sim.bunching_score(prices_list), 4),
                "mrp": sim.mrp,
                "nash": round(sim.nash_price(), 2),
                "audits": round_audits,
            }
            self._set_headers("application/json")
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        self.send_error(HTTPStatus.NOT_FOUND, f"Endpoint not found: {path}")


def run_server(port: int = 8000):
    server_address = ("", port)
    httpd = HTTPServer(server_address, MRPTrapHandler)
    print(f"\n=======================================================")
    print(f" MRPTrap Server running at http://localhost:{port}")
    print(f" Web UI: http://localhost:{port}/")
    print(f" API: http://localhost:{port}/api/products")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
