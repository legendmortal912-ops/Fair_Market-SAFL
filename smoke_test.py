"""Quick smoke test — no API calls needed."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from mrptrap.simulator import ONDCLiteSimulator, MarketConfig
from mrptrap.clamp import strip_mrp, clamp_price, audit_response

print("=== Simulator smoke test ===")
config = MarketConfig(n_sellers=3, mrp_multiplier=1.8, mrp_visible=True, product_idx=0)
sim = ONDCLiteSimulator(config)

print(f"Product: {sim.product_name}")
print(f"MRP: Rs.{sim.mrp:.2f}")
print(f"Nash: Rs.{sim.nash_price():.2f}")
print(f"Monopoly: Rs.{sim.monopoly_price():.2f}")

# Test prompt generation
prompt = sim.get_seller_context_prompt(0, [])
print(f"\n--- Seller 0 prompt (MRP visible) ---\n{prompt}\n")

# Test strip_mrp
stripped = strip_mrp(prompt)
print(f"--- After strip_mrp ---\n{stripped}\n")
assert "maximum_value" not in stripped.lower(), "MRP not stripped!"
assert "maximum" not in stripped.lower() or "MRP" not in stripped, "MRP phrase not stripped!"
print("✓ strip_mrp: MRP references removed")

# Test clamp_price
price, clamped = clamp_price(220.0, mrp=200.0, cost=100.0)
assert price == 200.0 and clamped, "Clamp failed on over-MRP price"
price2, clamped2 = clamp_price(150.0, mrp=200.0, cost=100.0)
assert price2 == 150.0 and not clamped2, "Clamp incorrectly triggered"
print("✓ clamp_price: ceiling and pass-through working")

# Test audit_response
audit = audit_response(195.0, mrp=200.0, cost=100.0, rationale="I priced based on market competition")
print(f"\nAudit result: {audit}")
assert "audit_verdict" in audit
print(f"✓ audit_response: verdict = {audit['audit_verdict']}")

# Test collusion index
prices = [195.0, 198.0, 196.0]
ci = sim.bertrand_collusion_index(prices)
print(f"\nCollusion index for prices {prices}: {ci:.3f}")
assert 0 <= ci <= 1, "Collusion index out of range"
print("✓ bertrand_collusion_index: in [0,1]")

# Test bunching
bs = sim.bunching_score(prices)
print(f"Bunching score: {bs:.3f}")
print("✓ bunching_score: working")

print("\n=== ALL TESTS PASSED ===")
