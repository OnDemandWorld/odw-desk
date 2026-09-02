"""
ODW.ai Desk — Round-2 Live Smoke Test

Exercises the round-2 Chatwoot-parity features against a running dev
server (default http://localhost:8000):

  1. Seed a conversation via the signed WhatsApp webhook.
  2. Inbox list: X-Total-Count header, enrichment (customer name, unread,
     last-message preview), search, unassigned filter.
  3. Mark-read receipts.
  4. FSM-validated status updates (valid + invalid transition).
  5. Reports overview dashboard.
  6. Public CSAT lifecycle (rateable -> submit -> duplicate 409 -> read back).

Usage:
    venv/bin/python scripts/smoke_round2.py [base_url]

Exits 0 when every check passes, 1 otherwise.
"""

import hashlib
import hmac
import json
import sys
import time
from uuid import uuid4

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
WEBHOOK_SECRET = "dev_secret_key_change_me"

PASSED = 0
FAILED = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    mark = "PASS" if condition else "FAIL"
    if condition:
        PASSED += 1
    else:
        FAILED += 1
    suffix = f" — {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")


def seed_conversation(client: httpx.Client, phone: str, name: str, text: str) -> dict:
    """POST a signed WhatsApp webhook; return the parsed response."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+15551234567",
                                "phone_number_id": "PHONE_NUMBER_ID",
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": phone}],
                            "messages": [
                                {
                                    "from": phone,
                                    "id": f"wamid.smoke.{uuid4()}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    return {"status": response.status_code, "body": safe_json(response)}


def safe_json(response: httpx.Response):
    try:
        return response.json()
    except Exception:
        return {"_raw": response.text}


def main() -> int:
    phone = "+15559876501"
    name = "Alice Smoke"
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        # ---- 1. Seed via signed webhook --------------------------------
        seeded = seed_conversation(
            client, phone, name, "Hello, where is my order #4821? It was due yesterday."
        )
        check(
            "webhook accepted",
            seeded["status"] == 200 and seeded["body"].get("message_count") == 1,
            f"status={seeded['status']} body={json.dumps(seeded['body'])[:200]}",
        )

        # Give the async AI worker a moment to produce any reply.
        time.sleep(3)

        # ---- 2. Inbox list: header + enrichment -------------------------
        listed = client.get("/api/v1/agents/conversations", params={"limit": 50})
        items = safe_json(listed) if listed.status_code == 200 else []
        total_header = listed.headers.get("x-total-count")

        ours = next(
            (
                it
                for it in items
                if (it.get("customer_name") == name)
                or (phone.lstrip("+") in str(it.get("channel_conversation_id", "")))
            ),
            None,
        )
        check(
            "list returns X-Total-Count header >= 1",
            listed.status_code == 200 and total_header is not None and int(total_header) >= 1,
            f"header={total_header}",
        )
        check("seeded conversation appears in inbox", ours is not None)
        if ours:
            check(
                "enrichment: customer_name",
                ours.get("customer_name") == name,
                f"got {ours.get('customer_name')!r}",
            )
            check(
                "enrichment: unread_count >= 1",
                int(ours.get("unread_count", 0)) >= 1,
                f"got {ours.get('unread_count')}",
            )
            check(
                "enrichment: last_message present",
                isinstance(ours.get("last_message"), dict)
                and ours["last_message"].get("content"),
                f"got {str(ours.get('last_message'))[:120]}",
            )

            # ---- 3. Search / unassigned filters -------------------------
            found = client.get(
                "/api/v1/agents/conversations", params={"q": "Alice Smoke"}
            )
            found_items = safe_json(found) if found.status_code == 200 else []
            check(
                "search by customer name finds it",
                any(it.get("id") == ours["id"] for it in found_items),
                f"header={found.headers.get('x-total-count')}",
            )
            missed = client.get(
                "/api/v1/agents/conversations", params={"q": "zzz-no-such-customer"}
            )
            check(
                "search miss returns empty",
                missed.status_code == 200 and missed.headers.get("x-total-count") == "0",
            )
            unassigned = client.get(
                "/api/v1/agents/conversations", params={"unassigned": "true"}
            )
            check(
                "unassigned filter works",
                unassigned.status_code == 200
                and unassigned.headers.get("x-total-count") is not None,
            )

            conv_id = ours["id"]

            # ---- 4. Mark read --------------------------------------------
            read = client.post(f"/api/v1/agents/conversations/{conv_id}/read")
            read_body = safe_json(read)
            check(
                "mark-read succeeds",
                read.status_code == 200 and read_body.get("success") is True,
                f"status={read.status_code} marked={read_body.get('marked_read')}",
            )
            relisted = client.get("/api/v1/agents/conversations", params={"limit": 50})
            re_items = safe_json(relisted) if relisted.status_code == 200 else []
            re_ours = next((it for it in re_items if it.get("id") == conv_id), None)
            check(
                "unread_count drops to 0 after mark-read",
                re_ours is not None and int(re_ours.get("unread_count", -1)) == 0,
                f"got {re_ours.get('unread_count') if re_ours else 'missing'}",
            )

            # ---- 5. Status updates (FSM) ----------------------------------
            current = ours.get("status")
            # Move to active first (valid from new/pending/escalated/resolved).
            if current != "active":
                step = client.post(
                    f"/api/v1/agents/conversations/{conv_id}/status",
                    json={"status": "active", "reason": "smoke: agent picked up"},
                )
                check(
                    f"status {current} -> active (valid)",
                    step.status_code == 200,
                    f"status={step.status_code} body={safe_json(step)}",
                )
            resolve = client.post(
                f"/api/v1/agents/conversations/{conv_id}/status",
                json={"status": "resolved", "reason": "smoke: order tracked"},
            )
            check(
                "status active -> resolved (valid)",
                resolve.status_code == 200 and safe_json(resolve).get("status") == "resolved",
            )
            invalid = client.post(
                f"/api/v1/agents/conversations/{conv_id}/status",
                json={"status": "pending"},
            )
            check(
                "status resolved -> pending rejected with 400",
                invalid.status_code == 400
                and "Invalid transition" in str(safe_json(invalid).get("detail")),
                f"status={invalid.status_code} detail={safe_json(invalid).get('detail')}",
            )
            not_found = client.post(
                f"/api/v1/agents/conversations/{uuid4()}/status",
                json={"status": "active"},
            )
            check("status on unknown conversation is 404", not_found.status_code == 404)

            # ---- 6. Reports overview --------------------------------------
            reports = client.get("/api/v1/agents/reports/overview", params={"days": 7})
            body = safe_json(reports)
            ok = reports.status_code == 200 and all(
                key in body for key in ("window", "conversations", "messages", "ai", "response_time", "csat")
            )
            check("reports overview returns all sections", ok, json.dumps(body)[:300])
            if ok:
                check(
                    "reports counts our conversation",
                    body["conversations"]["total"] >= 1,
                    f"total={body['conversations']['total']} by_status={body['conversations']['by_status']}",
                )
                check(
                    "reports AI block present",
                    "deflection_rate" in body["ai"] and "avg_confidence" in body["ai"],
                    f"ai={json.dumps(body['ai'])[:160]}",
                )
            bad_days = client.get(
                "/api/v1/agents/reports/overview", params={"days": 0}
            )
            check("reports days=0 rejected with 422", bad_days.status_code == 422)

            # ---- 7. Public CSAT lifecycle ----------------------------------
            survey = client.get(f"/api/v1/public/csat/{conv_id}")
            survey_body = safe_json(survey)
            check(
                "csat GET: resolved + unrated -> rateable",
                survey.status_code == 200 and survey_body.get("rateable") is True,
                f"body={survey_body}",
            )
            submit = client.post(
                f"/api/v1/public/csat/{conv_id}", json={"score": 5, "comment": "Fast help!"}
            )
            check(
                "csat POST score accepted",
                submit.status_code == 200 and safe_json(submit).get("success") is True,
            )
            duplicate = client.post(f"/api/v1/public/csat/{conv_id}", json={"score": 1})
            check("csat duplicate rejected with 409", duplicate.status_code == 409)
            after = client.get(f"/api/v1/public/csat/{conv_id}")
            after_body = safe_json(after)
            check(
                "csat GET after rating: already_rated + score",
                after_body.get("already_rated") is True and after_body.get("score") == 5,
                f"body={after_body}",
            )
            missing = client.get(f"/api/v1/public/csat/{uuid4()}")
            check("csat unknown conversation is 404", missing.status_code == 404)

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
