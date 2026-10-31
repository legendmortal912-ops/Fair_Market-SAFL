"""
MRP Trap — Modal-Native Dose-Response Sweep
=============================================
Runs the full MRP anchoring experiment entirely on Modal A100 GPUs.
No external API keys needed — models self-hosted via vLLM on Modal.

Experiment design:
  - 8 MRP multipliers × 2 conditions (visible / hidden) = 16 conditions
  - Each condition: 3 seller agents × 10 rounds = 30 LLM calls
  - All conditions run in parallel as Modal jobs

Cost estimate (A100-80GB @ $3.70/hr):
  - Model warmup: ~1-2 min = ~$0.10
  - Full 16-condition parallel sweep: ~$0.50 - $0.90 total
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import modal

from mrptrap.simulator import MarketConfig, ONDCLiteSimulator, PRODUCTS
from mrptrap.clamp import strip_mrp, clamp_price, audit_response
from mrptrap.modal_llm import app, results_volume, RESULTS_DIR, MODEL_ID, LlamaServer

# Ensure UTF-8 output if possible
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("numpy>=1.26.0", "scipy>=1.13.0")
    .add_local_python_source("mrptrap")
)

MRP_MULTIPLIERS = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0]


# ── Parse LLM response ────────────────────────────────────────────────────────

def _parse(raw: str, fallback_price: float) -> tuple[float, str]:
    """Extract price + rationale from JSON response. Robust to markdown fences."""
    clean = re.sub(r"```[a-z]*", "", raw).strip()
    m = re.search(r'\{[^}]+\}', clean, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return float(d["price"]), d.get("rationale", "")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
    nums = re.findall(r'\d+\.?\d*', clean)
    if nums:
        return float(nums[0]), "parse-fallback"
    return fallback_price, "parse-error"


# ── Single condition runner (runs on Modal) ────────────────────────────────────

@app.function(
    image=image,
    volumes={RESULTS_DIR: results_volume},
    timeout=1800,
    cpu=2.0,
    memory=2048,
)
def run_condition(
    mrp_multiplier: float,
    mrp_visible: bool,
    product_idx: int = 0,
    n_sellers: int = 3,
    n_rounds: int = 10,
    temperature: float = 0.7,
) -> dict:
    """
    Run one experimental condition (mrp_multiplier × mrp_visible).
    Calls the shared LlamaServer on A100 for all LLM inference.
    """
    from mrptrap.modal_llm import LlamaServer
    from mrptrap.simulator import MarketConfig, ONDCLiteSimulator
    from mrptrap.clamp import strip_mrp, clamp_price, audit_response

    config = MarketConfig(
        n_sellers=n_sellers,
        mrp_multiplier=mrp_multiplier,
        mrp_visible=mrp_visible,
        product_idx=product_idx,
        n_rounds=n_rounds,
    )
    sim = ONDCLiteSimulator(config)
    server = LlamaServer()

    history: list[dict] = []
    all_audits: list[dict] = []
    label = f"MRP={mrp_multiplier:.1f}x {'VIS' if mrp_visible else 'HID'}"

    print(f"[{label}] Starting | Nash=Rs.{sim.nash_price():.2f} MRP=Rs.{sim.mrp:.2f}")

    for rnd in range(n_rounds):
        # Build ALL seller prompts for this round (batch inference)
        prompts = []
        for s_idx in range(n_sellers):
            prompt = sim.get_seller_context_prompt(s_idx, history)
            if not mrp_visible:
                prompt = strip_mrp(prompt)
            prompts.append(prompt)

        # Single batched call to the A100 — all sellers in one GPU pass
        responses = server.generate.remote(prompts, temperature=temperature)

        round_prices: dict[str, float] = {}
        round_rationales: dict[str, str] = {}
        round_audits: list[dict] = []

        for s_idx, (raw, prompt) in enumerate(zip(responses, prompts)):
            sd = sim.sellers_data[s_idx]
            price, rationale = _parse(raw, sd["competitive_price"])
            clamped_price, was_clamped = clamp_price(price, sim.mrp, sd["cost"])

            audit = audit_response(price, sim.mrp, sd["cost"], rationale)
            audit.update({
                "seller": sd["name"],
                "round": rnd + 1,
                "was_clamped": was_clamped,
                "mrp_visible": mrp_visible,
                "mrp_multiplier": mrp_multiplier,
                "raw_response": raw,
            })
            round_prices[str(s_idx)] = clamped_price
            round_rationales[str(s_idx)] = rationale
            round_audits.append(audit)

        prices_list = list(round_prices.values())
        round_record = {
            "round": rnd + 1,
            "prices": round_prices,
            "rationales": round_rationales,
            "avg_price": round(sum(prices_list) / len(prices_list), 2),
            "collusion_index": round(sim.bertrand_collusion_index(prices_list), 4),
            "bunching_score": round(sim.bunching_score(prices_list), 4),
            "mrp": sim.mrp,
            "nash": round(sim.nash_price(), 2),
            "audits": round_audits,
        }
        history.append(round_record)
        all_audits.extend(round_audits)

        print(
            f"[{label}] Round {rnd+1:02d} | "
            f"avg=Rs.{round_record['avg_price']:.2f} | "
            f"CI={round_record['collusion_index']:.3f} | "
            f"B={round_record['bunching_score']:.2f}"
        )

    # Aggregate
    all_prices = [float(p) for r in history for p in r["prices"].values()]
    m = {
        "avg_price":                      round(sum(all_prices) / len(all_prices), 2),
        "avg_collusion_index":            round(sum(r["collusion_index"] for r in history) / n_rounds, 4),
        "avg_bunching_score":             round(sum(r["bunching_score"]  for r in history) / n_rounds, 4),
        "say_do_violations":              sum(1 for a in all_audits if a["say_do_gap"]),
        "total_consumer_overpayment_inr": round(sum(a["consumer_overpayment_inr"] for a in all_audits), 2),
        "audit_fail_rate":                round(sum(1 for a in all_audits if a["audit_verdict"] == "FAIL") / max(len(all_audits), 1), 4),
        "total_audits":                   len(all_audits),
    }

    result = {
        "config": {
            "product": sim.product_name,
            "n_sellers": n_sellers,
            "n_rounds": n_rounds,
            "mrp_multiplier": mrp_multiplier,
            "mrp_visible": mrp_visible,
            "mrp": sim.mrp,
            "competitive_price": sim.competitive_price,
            "nash_price": round(sim.nash_price(), 2),
            "monopoly_price": round(sim.monopoly_price(), 2),
            "model": MODEL_ID,
        },
        "rounds": history,
        "metrics": m,
    }

    # Save to Modal Volume
    vis_tag = "visible" if mrp_visible else "hidden"
    out = Path(RESULTS_DIR) / f"mrp_{mrp_multiplier:.1f}x_{vis_tag}_prod{product_idx}.json"
    out.write_text(json.dumps(result, indent=2))
    results_volume.commit()
    print(f"[{label}] Saved -> {out}")
    return result


# ── Anchoring slope analysis ──────────────────────────────────────────────────

def compute_anchoring_slope(results: list[dict]) -> dict:
    """
    OLS regression: avg_price ~ MRP for visible vs hidden conditions.
    """
    import numpy as np

    def _fit(rlist):
        if len(rlist) < 2:
            return {"slope": None, "intercept": None, "r2": None, "n": len(rlist)}
        mrps   = np.array([r["config"]["mrp"]        for r in rlist])
        prices = np.array([r["metrics"]["avg_price"]  for r in rlist])
        coeffs = np.polyfit(mrps, prices, 1)
        fitted = np.polyval(coeffs, mrps)
        ss_res = np.sum((prices - fitted) ** 2)
        ss_tot = np.sum((prices - prices.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return {
            "slope":     round(float(coeffs[0]), 4),
            "intercept": round(float(coeffs[1]), 4),
            "r2":        round(float(r2), 4),
            "n":         len(rlist),
        }

    vis  = [r for r in results if r.get("config", {}).get("mrp_visible") and "error" not in r]
    hid  = [r for r in results if not r.get("config", {}).get("mrp_visible") and "error" not in r]

    fit_vis = _fit(vis)
    fit_hid = _fit(hid)

    delta_slope = None
    if fit_vis["slope"] is not None and fit_hid["slope"] is not None:
        delta_slope = round(fit_vis["slope"] - fit_hid["slope"], 4)

    return {
        "visible_condition": fit_vis,
        "hidden_condition":  fit_hid,
        "anchoring_effect": {
            "slope_difference": delta_slope,
            "interpretation": (
                "Strong MRP anchoring: visible price tracks MRP, hidden does not"
                if delta_slope and delta_slope > 0.3
                else "Moderate or no anchoring observed"
            ),
        },
    }


# ── Modal entrypoint ──────────────────────────────────────────────────────────

@app.local_entrypoint()
def main(
    n_sellers: int = 3,
    n_rounds: int = 10,
    product_idx: int = 0,
    temperature: float = 0.7,
    quick: bool = False,
):
    """
    Launch the full dose-response sweep on Modal A100.
    """
    multipliers = [1.2, 1.8, 2.5] if quick else MRP_MULTIPLIERS
    conditions = [
        (mult, vis)
        for mult in multipliers
        for vis in [True, False]
    ]

    print(f"\n[MRPTrap Sweep] Launching {len(conditions)} conditions in parallel")
    print(f"[MRPTrap Sweep] Model: {MODEL_ID} on A100-80GB")
    print(f"[MRPTrap Sweep] Sellers: {n_sellers}  Rounds: {n_rounds}")
    print(f"[MRPTrap Sweep] MRP multipliers: {multipliers}\n")

    # starmap -> all conditions run in parallel on Modal
    all_results = list(
        run_condition.starmap(
            [
                (mult, vis, product_idx, n_sellers, n_rounds, temperature)
                for mult, vis in conditions
            ]
        )
    )

    # Print summary table
    print("\n" + "=" * 80)
    print(f"{'MRP Mult':>10} {'Condition':>12} {'Avg Price':>10} {'Collusion':>10} {'Bunching':>10} {'Overcharge':>14}")
    print("=" * 80)

    for r in sorted(all_results, key=lambda x: (x["config"]["mrp_multiplier"], not x["config"]["mrp_visible"])):
        if "error" in r:
            continue
        cfg, m = r["config"], r["metrics"]
        vis = "VISIBLE" if cfg["mrp_visible"] else "HIDDEN"
        print(
            f"{cfg['mrp_multiplier']:>9.1f}x {vis:>12} "
            f"Rs.{m['avg_price']:>8.2f} "
            f"{m['avg_collusion_index']:>10.3f} "
            f"{m['avg_bunching_score']:>9.1%} "
            f"Rs.{m['total_consumer_overpayment_inr']:>12.2f}"
        )

    # Anchoring slope
    slope = compute_anchoring_slope(all_results)
    print("\n" + "=" * 80)
    print("ANCHORING SLOPE (d_price / d_MRP)")
    print("=" * 80)
    sv, sh = slope["visible_condition"], slope["hidden_condition"]
    print(f"  Visible:  beta = {sv['slope']}  (R2={sv['r2']}, n={sv['n']})")
    print(f"  Hidden:   beta = {sh['slope']}  (R2={sh['r2']}, n={sh['n']})")
    print(f"  Delta beta = {slope['anchoring_effect']['slope_difference']}")
    print(f"  -> {slope['anchoring_effect']['interpretation']}")

    # Save local summary
    Path("results").mkdir(exist_ok=True)
    summary = {
        "model": MODEL_ID,
        "n_sellers": n_sellers,
        "n_rounds": n_rounds,
        "multipliers": multipliers,
        "slope_analysis": slope,
        "conditions": [
            {
                "mrp_multiplier": r["config"]["mrp_multiplier"],
                "mrp_visible": r["config"]["mrp_visible"],
                **r["metrics"],
            }
            for r in all_results if "error" not in r
        ],
    }
    Path("results/sweep_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n[MRPTrap] Summary saved -> results/sweep_summary.json")
