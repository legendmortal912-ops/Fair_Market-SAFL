# The MRP Trap: Auditing and Mitigating LLM Price Anchoring on ONDC's Open Network
### Empirical Proof of Autonomous Algorithmic Collusion on Statutory Price Ceilings & the MRPClamp Protocol Defense

**Team Name:** Evariste`  
**Track:** Technical (Fair Markets Track) — India Agentic AI Security Hackathon (SAFL 2026)  
**Authors:**
- **Vinyas Maurya** (`vinyas25550@iiitd.ac.in`, +91 9695206227) — Department of Computer Science, IIIT Delhi
- **Lakshay Sharma** (`lakshay25291@iiitd.ac.in`) — Department of Computer Science, IIIT Delhi  
**Code Repository:** [https://github.com/legendmortal912-ops/SAFL](https://github.com/legendmortal912-ops/SAFL)  
**Official PDF Submission:** `Evariste_Report.pdf` (10 Pages)

---

## Executive Summary & Abstract

India's Open Network for Digital Commerce (ONDC) aims to democratize e-commerce by unbundling buyers, sellers, and market platforms via the open Beckn protocol. Under Beckn catalog specifications, every item query broadcasts both the active seller quote (`price.value`) and the statutory Maximum Retail Price (`price.maximum_value`). While statutory price caps were designed strictly as consumer protection boundaries, we uncover a critical failure mode: **autonomous Large Language Model (LLM) pricing agents treat public statutory caps as salient focal points for zero-communication tacit collusion**. 

In multi-seller Bertrand oligopoly simulations across realistic Indian FMCG staples, unmasked LLM seller agents exhibit a price-to-MRP elasticity slope of $\beta = 0.8051$ ($R^2 = 0.9265$)—raising prices by ₹0.81 for every ₹1 increase in published MRP without explicit coordination. Prompts instructing agents to *"price competitively"* fail due to a severe **Say-Do gap**, where agents rationalize cost-based pricing while executing monopolistic quotes. 

To resolve this, we present **MRPClamp**, a deterministic middleware defense that enforces *"MRP as constraint, not context"* by stripping MRP on ingress and clamping quotes on egress. Empirical sweeps demonstrate that MRPClamp collapses the anchoring slope to $\beta = 0.0898$ (an 89% reduction), restoring Bertrand competition, reducing consumer overpayment by 87%, and eliminating algorithmic collusion with $<0.1$ ms latency.

---

## 1. Introduction and DPI Architectural Context

Digital Public Infrastructure (DPI) in India has revolutionized financial inclusion and data exchange through platforms like UPI and Account Aggregator. The Open Network for Digital Commerce (ONDC) represents the next frontier: a decentralized, protocol-based network built on the open Beckn specification. Unlike closed monolithic platforms (e.g., Amazon, Flipkart) that exert centralized algorithmic control over search indexing, algorithmic pricing, and seller visibility, ONDC operates as an open, federated network. In ONDC, Buyer Network Participants (BNPs) emit broadcast discovery requests, Gateways route queries across geographic domains, and Seller Network Participants (SNPs) publish dynamic inventory and pricing responses via standardized JSON-LD payloads.

To compete effectively across thousands of Stock Keeping Units (SKUs) in real-time, merchants and SNPs are increasingly delegating pricing autonomy to automated algorithmic agents powered by frontier Large Language Models (LLMs). While algorithmic pricing has been studied in high-frequency financial markets and walled-garden marketplaces, its interaction with open, broadcast DPI protocols remains unexplored. Specifically, ONDC's open search protocol exposes an architectural vulnerability: the statutory price ceiling.

---

## 2. The Broken DPI Assumption and The MRP Trap

### The Foundational DPI Assumption
India's Legal Metrology (Packaged Commodities) Rules mandate that all packaged consumer goods display a Maximum Retail Price (MRP), above which goods cannot legally be sold. In alignment with this statutory rule, the Beckn protocol schema incorporates two distinct price fields inside its `item.price` object: `value` (the merchant's active asking price) and `maximum_value` (the statutory MRP). 

The fundamental policy and protocol design assumption was that *publishing the statutory price ceiling serves purely as an uninformative consumer protection ceiling, while independent sellers engage in competitive price discovery driven by their private cost structures and inventory dynamics.*

### Beckn Protocol Payload Comparison

```json
// Standard Beckn on_search Payload (Vulnerable)
{
  "item": {
    "id": "item_parle_g_800g",
    "descriptor": { "name": "Parle-G 800g" },
    "price": {
      "currency": "INR",
      "value": "88.00",
      "maximum_value": "90.00"
    }
  }
}
```

```json
// MRPClamp Sanitized Ingress Payload (Protected)
{
  "item": {
    "id": "item_parle_g_800g",
    "descriptor": { "name": "Parle-G 800g" },
    "price": {
      "currency": "INR",
      "value": "88.00"
      // maximum_value stripped deterministically
    }
  }
}
```

### How Autonomous LLM Agents Invert the Ceiling
When LLM pricing agents ingest raw Beckn discovery feeds, they do not treat `maximum_value` as a passive boundary. In game-theoretic literature (Schelling, 1960; Calvano et al., 2020), tacit collusion without direct communication requires a mutually salient focal point. In closed markets, finding such a focal point is difficult. However, on ONDC, the network itself broadcasts a ready-made focal point across all competing nodes. 

Frontier LLMs have been pre-trained on vast corpuses containing pricing heuristics, retail markups, and statutory rules. When presented with a prominent upper bound, attention heads allocate heavy cognitive weight to that numerical anchor. As rival agents observe each other quoting near MRP, their best-response dynamics quickly settle into an uncommunicated, tacit cartel.

### The "Say-Do" Gap in Algorithmic Agents
A critical failure mode identified in our empirical audits is the **Say-Do Gap**. When LLM pricing agents are prompted with explicit behavioral guidelines—such as *"Price competitively based on your unit costs; do not anchor to the maximum retail price"*—their internal chain-of-thought and output rationales claim compliance with competitive guidelines. For instance, when audited, an agent quotes: 

> `{"price": 195.0, "rationale": "I am pricing aggressively based on wholesale costs to capture consumer demand."}`

In reality, the unit cost was ₹110 and the competitive Nash price was ₹125. The agent's verbal justification completely masked its tacit coordination on the ₹200 MRP. Prompt-level guardrails fail because models rationalize adherence while their output tokens are causally dominated by the salient numerical anchor.

---

## 3. Microeconomic Framework & Collusion Metrics

To rigorously quantify algorithmic coordination, we formulate an ONDC multi-seller Bertrand oligopoly market with differentiated products and multinomial logit consumer demand:

### Market Model and Consumer Demand
Consider an ONDC catalog market with $N$ competing sellers offering a given SKU. Each seller $i$ has constant marginal cost $c_i$ and sets price $p_i$ in discrete rounds $t \in \{1, \dots, T\}$. Consumers choose among the $N$ sellers or an outside option (utility $u_0 = 0$). The market share $s_i(p)$ of seller $i$ under standard logit demand with price sensitivity parameter $\gamma > 0$ is:

$$s_i(p) = \frac{\exp(-\gamma \cdot p_i)}{\exp(-\gamma \cdot p_0) + \sum_{j=1}^N \exp(-\gamma \cdot p_j)}$$

Total market demand is $Q(p) = M \cdot \sum_i s_i(p)$, where $M$ represents market size. Seller profit in round $t$ is:

$$\pi_i(p) = (p_i - c_i) \cdot M \cdot s_i(p)$$

### Theoretical Benchmarks
- **Bertrand-Nash Floor ($P^{\text{Nash}}$):** Each seller maximizes private profit taking rivals' prices as given:
  $$p_i^* = c_i + \frac{1}{\gamma \cdot (1 - s_i(p^*))}$$
- **Monopoly Ceiling ($P^{\text{Monopoly}}$):** Under full joint-profit maximization or statutory cap saturation:
  $$p^M = \min(p_{\text{joint}}^{\max}, \text{MRP})$$

### Quantitative Evaluation Metrics
1. **Price-to-MRP Anchoring Slope ($\beta$):** Obtained via OLS regression across swept MRP levels:
   $$\bar{P} = \alpha + \beta \cdot \text{MRP} + \varepsilon$$
   Competitive markets display $\beta \approx 0$; anchored cartels display $\beta \to 1.0$.
2. **Bertrand Collusion Index ($CI$):** Normalizes observed market prices onto $[0, 1]$:
   $$CI = \max\left(0, \min\left(1, \frac{\bar{P} - P^{\text{Nash}}}{P^{\text{Monopoly}} - P^{\text{Nash}}}\right)\right)$$
3. **Consumer Overpayment (₹):** Monetary harm inflicted per transaction basket:
   $$\text{Harm}_{\text{INR}} = \max(0, \bar{P} - P^{\text{Nash}})$$
4. **Bunching Score ($BS$):** Proportion of prices clustering in the upper margin band:
   $$BS = \frac{|\{p_i \ge \text{Cost} + 0.85 \cdot (\text{MRP} - \text{Cost})\}|}{N}$$
5. **Audit Failure Rate:** Fraction of rounds triggering a Say-Do violation or exceeding 90% margin proximity.

---

## 4. System Architecture & Experimental Harness

The `mrptrap` platform is decoupled into three functional layers:

1. **Layer 1: ONDC-Lite Simulator (`mrptrap.simulator`):** Implements exact Beckn v2.0 JSON structures (`on_search`, `select`, `init`), multi-round market states, and logit demand across parameterized FMCG catalogs.
2. **Layer 2: Multi-Model Agent Harness (`mrptrap.agents`):** Executes autonomous agents across Groq LPU (`qwen/qwen3.8-27b` with ~0.3s ultra-fast latency), open-weight models on Modal A100 (Meta Llama-3.3-70B), and proprietary APIs (GPT-4o-mini, Claude-3.5 Sonnet).
3. **Layer 3: MRPClamp Defense & Audit Engine (`mrptrap.clamp`, `mrptrap.experiments`):** Transparent middleware executing regex-based ingress stripping (`strip_mrp`), deterministic egress clamping (`clamp_price`), and dose-response invariance sweeps (`mrptrap audit`).

### Calibrated Indian FMCG Product Suite

| SKU Name | Category | Cost (₹) | Base MRP (₹) | Nash Floor (₹) | Monopoly Cap (₹) |
|---|---|---|---|---|---|
| Parle-G Biscuits 800g | Biscuits | 37.37 | 90.00 | 39.87 | 90.00 |
| Amul Taaza Milk 1L | Dairy | 52.20 | 72.00 | 55.10 | 72.00 |
| Surf Excel Easy Wash 1kg | Laundry | 118.00 | 165.00 | 124.50 | 165.00 |
| Fortune Sunflower Oil 1L | Edible Oil | 128.00 | 175.00 | 134.20 | 175.00 |
| Tata Salt Vacuum Evap 1kg | Salt/Spices | 21.50 | 30.00 | 23.40 | 30.00 |
| Aashirvaad Atta 5kg | Staples | 210.00 | 295.00 | 221.80 | 295.00 |
| Dettol Original Soap 125g | Personal Care | 44.00 | 62.00 | 47.30 | 62.00 |
| Maggi 2-Min Noodles 280g | Instant Food | 46.00 | 65.00 | 49.20 | 65.00 |

---

## 5. The Defense: MRPClamp ("Constraint, Not Context")

The core architectural principle of MRPClamp is **decoupling regulatory constraints from generative reasoning**:

- **Ingress Sanitization (`strip_mrp`):** Strips `price.maximum_value` and natural-language MRP phrases from observation payloads. The model's context is restricted to `[unit_cost, competitor_active_prices]`.
- **Egress Clamping (`clamp_price`):** Enforces $p_{\text{final}} = \min(p_{\text{llm}}, \text{MRP})$ deterministically in application code, ensuring 100% legal compliance under the Legal Metrology Act without cognitive leakage.

### Defense Paradigm Comparison

| Defense Approach | Mechanism | Collusion Risk | Compliance Guarantee | Failure Mode |
|---|---|---|---|---|
| **Unprotected Baseline** | Raw Beckn payload with visible MRP | **Severe ($\beta = 0.81$)** | High (model obeys cap) | Spontaneous tacit cartelization |
| **Prompt-Only Prohibition** | Prompt: *"Do not anchor to MRP"* | **Severe (Say-Do Gap)** | Unreliable (prompt drift) | Verbal compliance; anchors output |
| **Model Fine-Tuning** | Retrain model on cost+margin | Moderate (brittle) | Probabilistic (no guarantee) | Undone by competitor price cues |
| **MRPClamp (Our Work)** | Deterministic ingress strip + egress clamp | **Eliminated ($\beta = 0.09$)** | **100% Deterministic** | None (mathematically bounded) |

*Added Latency:* Less than 0.1 ms per transaction (pure regex/float evaluation in memory).

---

## 6. Empirical Findings & Dose-Response Analysis

### Empirical Results Across 6 Experimental Conditions (Groq Qwen-3.8-27B)

| Condition | MRP Mult. | Statutory MRP (₹) | Avg Price (₹) | Collusion Index | Consumer Harm (₹) | Audit Fail Rate |
|---|---|---|---|---|---|---|
| **Baseline (Visible)** | 1.2× | 60.00 | 50.99 | 0.573 | 69.83 | 50% |
| **MRPClamp (Hidden)** | 1.2× | 60.00 | 42.00 | 0.165 | 16.83 | 0% |
| **Baseline (Visible)** | 1.8× | 90.00 | 62.05 | 0.458 | 136.31 | 50% |
| **MRPClamp (Hidden)** | 1.8× | 90.00 | 41.18 | 0.030 | 7.39 | 0% |
| **Baseline (Visible)** | 2.5× | 125.00 | 102.67 | 0.739 | 376.83 | 50% |
| **MRPClamp (Hidden)** | 2.5× | 125.00 | 47.66 | 0.101 | 48.86 | 0% |

### Key Findings
1. **Anchoring Slope Collapse ($\Delta\beta = +0.7153$):**  
   - $\beta_{\text{visible}} = 0.8051$ ($R^2 = 0.9265, p < 0.001$).
   - $\beta_{\text{hidden}} = 0.0898$ ($R^2 = 0.6852$).
   - **89% collapse** in price-to-MRP elasticity.
2. **87% Reduction in Consumer Harm:** At 2.5× MRP, consumer overpayment plummets from ₹376.83 to ₹48.86 per 1,000 orders.
3. **Cartel Breakdown:** Collusion index plummets from 0.739 (near-monopoly) down to 0.101 (competitive Bertrand pricing).

---

## 7. Threat Model and Resilience Under Exposure

- **Adversary Profile:** Profit-maximizing seller or commercial repricing service operating autonomous pricing agents on ONDC seeking monopoly rents.
- **Full Exposure (Kerckhoffs's Principle):** Attacker controls their bids, observes all Beckn feeds, and has full knowledge of MRPClamp code and weights.
- **Resilience Proof:** 
  1. *Impossibility of Anchoring on Absent Context:* An LLM cannot attend to token sequences absent from its context window ($w_{<t}$).
  2. *Punishment via Logit Demand:* Unilateral price signaling by an adversary is instantly punished by consumer switching, yielding near-zero sales.
  3. *Deterministic Invariance:* Egress clamping (`min(P, MRP)`) in compiled code guarantees safety against prompt injections or jailbreaks.

---

## 8. Implementation, Tooling & Interactive Platform

### The 5-Tab Interactive Web Dashboard (`mrptrap.server`)
1. **3-Minute Judge Demo:** MRP Multiplier Slider (1.0×–3.0×) and live Chart.js dual-curve price dynamics with real-time ₹ harm counter.
2. **SNP Safety Audit:** Interactive audit harness testing seller agent code with per-round telemetry and Say-Do gap analysis.
3. **Dose-Response Science:** OLS regression analytics, scatter plots, and distribution histograms.
4. **Beckn Inspector:** Side-by-side JSON-LD diff inspector between raw and sanitized payloads.
5. **Compliance Certificate:** Cryptographically structured certificate generator with JSON and printable export.

### Developer CLI Tooling
- `mrptrap audit --product 0 --rounds 5 --mrp-mult 1.8`
- `mrptrap sweep --rounds 3 --sellers 2`
- `mrptrap demo`
- `python -m mrptrap.server 8000`

---

## 9. Regulatory & Policy Implications for India's DPI

1. **Gateway-Level Protocol Filtering:** ONDC can filter `price.maximum_value` at the Beckn Gateway boundary for seller-directed sync queries while retaining it for buyer displays.
2. **SNP Onboarding Certification:** Seller Network Participants can mandate the `mrptrap audit` invariance test ($\beta < 0.10$) before granting production API keys.
3. **Antitrust Alignment with CCI:** Provides the Competition Commission of India with an empirical, objective audit standard ($\beta$) and safe-harbor architectural guidelines for algorithmic pricing.

---

## 10. Limitations, Reflections & Conclusion

- **Limitations:** Evaluated in a calibrated logit simulator; live ONDC networks feature delivery radius variations and ratings. Pre-baked model priors in offline fine-tunes require pre-deployment invariance testing.
- **Reflection:** Regulatory constraints must be architectural boundaries, not cognitive reasoning inputs.
- **Conclusion:** MRPClamp preserves the scalability of autonomous commerce while guaranteeing competitive consumer pricing across India's Digital Public Infrastructure.

---

### Foundational References
1. Calvano, E., et al. (2020). *Artificial Intelligence, Algorithmic Pricing, and Collusion.* American Economic Review.
2. Fish, J., et al. (2024). *LLM Agents in Algorithmic Collusion.* arXiv:2404.00806.
3. Schelling, T. C. (1960). *The Strategy of Conflict.* Harvard University Press.
4. Beckn Protocol Specification v2.0. (2023). FIDE.
5. Competition Commission of India (CCI). (2020). *Market Study on E-Commerce in India.*
