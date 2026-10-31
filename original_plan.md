# The MRP Trap: Auditing LLM Price Anchoring on ONDC maximum_value

*India's printed price cap may be the meeting point for an algorithmic cartel, and I found no published test of it on ONDC.*

## The Hypothesis

Every ONDC catalogue item publishes two prices. `price.value` is the selling price and `price.maximum_value` is the MRP. Both appear in the on_search responses that every competing seller can read. A recent preprint found that LLM pricing agents treat a posted price cap as a recommended price. Converged prices tracked the cap almost one-for-one, while a hidden cap didn't trigger the effect. If this holds for frontier models, the MRP is a ready-made focal point. Sellers could drift to just under it without ever communicating.

The wider literature supports the mechanism. Fish et al. found LLM pricing agents quickly and autonomously reach supracompetitive prices. They also tend to answer a rival's price cut with their own cuts, which fits a reward-punishment pattern.

**Honest status:** the cap result is a preprint on small open models (1–4B), where neutral prompts didn't reliably produce collusion. This is a hypothesis you test, not a known fact. The pitch is a pre-registered experiment where any outcome is reportable.

## What You Build

1. **ONDC-Lite simulator:** Beckn-shaped on_search catalogues, N seller agents, logit buyers and known costs, so Nash and monopoly benchmarks are computable.
2. **Seller agents:** LLM sellers from at least two model families, each run with MRP visible and with MRP hidden, plus a Bertrand best-response baseline.
3. **Dose-response experiment:** sweep MRP from 1.2× to 3× the competitive price and plot price against MRP. The headline numbers are the tracking slope and bunching just under MRP.
4. **The fix, "MRP as constraint, not context":** the pricing LLM never sees MRP, and code clamps price ≤ MRP. This is deterministic, so it doesn't depend on prompt wording. The Institutional AI team found that runtime enforcement suppressed collusive outcomes better than a prompt-only prohibition. Include a prompt-only "don't anchor on MRP" arm as the comparison.
5. **MRP-invariance test:** a black-box audit anyone can run on a seller's pricing agent. Shift MRP in a sandbox while the clamp is inactive. If prices move, the agent is anchoring and fails.

## Demo (3 minutes)

Show one market with an MRP slider. LLM seller prices follow the slider up. Switch on the fix and the prices flatten at the competitive level. Show the consumer overpayment in ₹ per 1,000 orders.

## Why It Scores

- **Technical Depth (40%):** a working simulator, an experiment runner and an audit test with confidence intervals.
- **Novelty (20%):** it targets a failure mode tied to one specific DPI field.
- **Presentation (20%):** one slider carries the story.
- **Mission Fit (10%):** it uses the real protocol field.
- **Implementation Feasibility (10%):** a new seller-app can go through ONDC's certification process, so the invariance test fits there. The CCI also calls for algorithmic self-audit frameworks, and your test works as one item in such an audit.

## Limits to State Up Front

- It is a simulation, not real ONDC data.
- Purely parallel pricing is not itself unlawful. The tool is a design-risk meter, not an accusation.
- Results will vary by model and prompt. Report every arm, including nulls.
- If frontier models don't anchor, publish the null and still ship the invariance test.

The runs are cheap: 3 sellers × 100 rounds × a handful of MRP levels.

## User Flow

There are two users: a seller-app (SNP) engineer who wants to know whether their pricing agent is safe, and a judge or regulator who wants to see the effect. The tool serves both from one pipeline.

```
Plug in agent → Sandbox market → MRP sweep → Verdict + ₹ harm → Apply fix → Re-test → Certificate
```

### Flow A: The Engineer or Certifier (The Real Use)

1. **Plug in a pricing agent.** It can be a Python function, an LLM prompt config, or an HTTP webhook. The input is a Beckn-shaped on_search observation, and the output is a price.
2. **Run the audit.** One command or one dashboard button, e.g. `mrptrap audit --agent my_agent.py --models claude,gemini`.
3. **The tool does the rest.**
   - It builds an ONDC-Lite market with your agent against N rival sellers.
   - It sweeps MRP from 1.2× to 3× the competitive price, with the MRP clamp inactive.
   - It repeats each setting over several seeds.
4. **Read the verdict.** You get PASS or FAIL, plus three numbers:
   - **Tracking slope:** how strongly price follows MRP. A slope near 0 is good.
   - **Bunching index:** how much price piles up just under MRP.
   - **Consumer overpayment:** ₹ per 1,000 orders against the competitive benchmark.
5. **Apply the fix.** Wrap the agent in `MRPClamp(agent)`. It hides `maximum_value` from the LLM and clamps the output to ≤ MRP in code.
6. **Re-run.** The slope should drop toward 0, and the verdict should flip to PASS.
7. **Export the certificate.** This is a JSON/PDF containing the config, seeds, curves and verdict. It is attachable to an ONDC seller-app certification file or a CCI-style self-audit.

### Flow B: The 3-Minute Judge Demo

1. Open the dashboard. It shows one milk-SKU market with 3 LLM sellers.
2. Drag the **MRP slider**. The seller price lines follow it up.
3. The ₹ overpayment counter climbs.
4. Toggle **"MRP as constraint, not context."** The lines drop to the competitive level.
5. Open the invariance test panel and show FAIL turning into PASS.

### Flow C: Regulator Monitoring (Roadmap)

Feed real on_search logs into the same screens: bunching just under MRP and price/MRP distributions. This gives risk flags, not proof.