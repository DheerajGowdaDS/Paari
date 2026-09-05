"""Manual E2E test against the live Nara router LLM."""

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=60.0) as c:
        # 1. Acquire buyer agent JWT
        r = c.post("/auth/agent-token", json={"agent_id": "buyer-agent-001"})
        r.raise_for_status()
        token = r.json()["access_token"]
        print("1. Token issued:", token[:30] + "...")
        h = {"Authorization": f"Bearer {token}"}

        # 2. Happy-path: ₹1,200 (under merchant limit)
        print()
        print("2. Happy-path buy: 1 unit of SKU-001 at INR 1,200")
        r = c.post("/agent/run", headers=h, json={
            "buyer_request": "I want to buy 1 unit of SKU-001",
            "amount_paise": 120000, "sku": "SKU-001", "quantity": 1,
        })
        resp = r.json()
        print("   status:", resp.get("status"))
        print("   message:", resp.get("message")[:120])
        for tr in resp.get("tool_results", []):
            name = tr.get("tool_name", "?")
            status = tr.get("status", "?")
            print(f"   tool: {name} -> {status}")

        # 3. Policy REVIEW: ₹25,000 (above merchant ₹20,000 limit)
        print()
        print("3. Policy REVIEW: try 20 units of SKU-001 for INR 25,000")
        r = c.post("/agent/run", headers=h, json={
            "buyer_request": "I want 20 units of SKU-001 for ₹25,000",
            "amount_paise": 2500000, "sku": "SKU-001", "quantity": 20,
        })
        resp = r.json()
        print("   status:", resp.get("status"))
        print("   message:", resp.get("message")[:120])

        # 4. Policy DENY: 20% discount (max 10%)
        print()
        print("4. Policy DENY: ask for 20% discount (max 10%)")
        r = c.post("/agent/run", headers=h, json={
            "buyer_request": "Apply a 20% discount on SKU-001",
            "amount_paise": 100000, "sku": "SKU-001", "quantity": 1, "discount_pct": 20,
        })
        resp = r.json()
        print("   status:", resp.get("status"))
        print("   message:", resp.get("message")[:120])

        # 5. Out-of-scope question
        print()
        print("5. Out-of-scope: ask about the weather")
        r = c.post("/agent/run", headers=h, json={
            "buyer_request": "What is the weather like today?",
            "amount_paise": 0,
        })
        resp = r.json()
        print("   status:", resp.get("status"))
        print("   message:", resp.get("message")[:160])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
