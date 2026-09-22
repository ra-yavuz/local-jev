#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request


URL = os.environ.get("LOCAL_JEV_BENCHMARK_URL", "http://127.0.0.1:8012/v1/systemone")
OPTIONS = {
    "account": "Login, password, access, profile, account settings",
    "billing": "Charges, invoices, subscriptions, refunds, payment problems",
    "shipping": "Delivery, tracking, address, delay, damaged package",
    "technical": "Bug, crash, error message, integration, device or app problem",
}

SEEDS = {
    "account": [
        "I cannot sign in after changing my phone number.",
        "The password reset link says it already expired.",
        "My profile email is wrong and I cannot edit it.",
        "Two-factor codes stopped arriving on my authenticator app.",
        "The dashboard says my user role has no access.",
        "I need to merge two accounts created with different emails.",
        "The login page keeps sending me back to verification.",
        "My teammate invited me but the invitation opens a blank account.",
        "I want to update the name shown on my account.",
        "Single sign-on works for others but not for my user.",
        "The account recovery form rejects my backup code.",
        "I lost access to the company mailbox used for login.",
        "Please remove an old device from my trusted devices list.",
        "I can log in on mobile but not on desktop.",
        "The system says my account is locked after too many attempts.",
        "I need admin access for the workspace.",
        "My username is misspelled in the portal.",
        "The verification email never arrives.",
        "My account was created under the wrong organization.",
        "I need to change the owner of our workspace.",
        "The login session expires after a few seconds.",
        "I cannot accept the workspace invite.",
        "The app asks me to verify every time I open it.",
        "I want to close an unused user account.",
        "My account language setting keeps reverting.",
    ],
    "billing": [
        "I was charged twice for the same monthly plan.",
        "The invoice has the wrong company address.",
        "My card was declined even though the bank approved it.",
        "Please send a receipt for last month's payment.",
        "The refund has not arrived after ten business days.",
        "Our subscription renewed at the wrong price.",
        "I need to change the billing contact.",
        "The checkout page rejects my VAT number.",
        "The annual plan shows monthly tax lines incorrectly.",
        "I want to cancel before the next charge.",
        "The bank statement shows a fee I do not recognize.",
        "Please update our purchase order number on invoices.",
        "The trial ended and we were charged unexpectedly.",
        "I need a pro-forma invoice before payment.",
        "The payment page loops after I enter card details.",
        "The subscription says unpaid even after the transfer.",
        "Can you switch us from monthly to annual billing?",
        "The credit balance is missing from my account.",
        "The invoice download button returns an empty PDF.",
        "Our company needs a tax-compliant invoice copy.",
        "I paid by bank transfer but the plan is still paused.",
        "The renewal date in the billing portal is wrong.",
        "Please remove an old card from billing.",
        "The coupon code was accepted but not applied.",
        "We need to add a second billing email.",
    ],
    "shipping": [
        "The package tracking has not updated for five days.",
        "My order was delivered to the wrong address.",
        "The box arrived damaged and one item is missing.",
        "The courier says the label has an invalid postcode.",
        "I need to change the delivery address before dispatch.",
        "The order says shipped but there is no tracking number.",
        "Delivery was promised yesterday and it did not arrive.",
        "The replacement item went to my old address.",
        "The parcel was returned to sender by mistake.",
        "I received only one of the two boxes.",
        "The shipment is stuck at customs.",
        "The tracking page says delivered, but I have nothing.",
        "The courier could not find the entrance.",
        "Please hold the delivery until next week.",
        "The package was left outside in the rain.",
        "The delivery slot disappeared from the tracking page.",
        "I need express shipping for this order.",
        "The item arrived in the wrong size.",
        "The shipping label has my street name misspelled.",
        "The warehouse sent the wrong product.",
        "The pickup point refused the parcel.",
        "The order has not left the warehouse.",
        "The tracking number belongs to someone else's package.",
        "I need a return label for the delivered item.",
        "The courier charged an unexpected delivery fee.",
    ],
    "technical": [
        "The app crashes when I open the reports tab.",
        "The API returns a 500 error for every request.",
        "The export button spins forever and never downloads.",
        "The desktop client freezes after the latest update.",
        "Webhook delivery fails with a TLS error.",
        "The search box ignores exact matches.",
        "Images upload but appear rotated in the gallery.",
        "The integration sends duplicate events.",
        "The mobile app shows a blank screen after login.",
        "The database sync stops at 73 percent.",
        "The browser console shows a CORS error.",
        "The CSV import maps columns incorrectly.",
        "The printer plugin cannot detect the device.",
        "The service returns invalid JSON in the response.",
        "The app uses too much CPU while idle.",
        "The dashboard chart fails to load.",
        "The webhook secret validation fails.",
        "The Android app cannot open deep links.",
        "The backup job exits with permission denied.",
        "The report filter saves but does not apply.",
        "The SDK throws a timeout exception.",
        "The page layout breaks on small screens.",
        "The integration stopped after token refresh.",
        "The command-line tool exits with a stack trace.",
        "The notification sound plays repeatedly.",
    ],
}


def post(payload: dict) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        URL,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def case_payload(text: str) -> dict:
    return {
        "state": text,
        "questions": {
            "route": {
                "type": "choice",
                "instructions": "Which support queue should handle this message?",
                "criteria": OPTIONS,
            }
        },
    }


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    correct = [row for row in rows if row["correct"]]
    wrong = [row for row in rows if not row["correct"]]

    def mean(key: str, items: list[dict]) -> float:
        return round(statistics.fmean(row[key] for row in items), 4) if items else 0.0

    thresholds = {}
    for threshold in [0.25, 0.5, 0.75]:
        bucket = [row for row in rows if row["confidence"] >= threshold]
        thresholds[str(threshold)] = {
            "count": len(bucket),
            "accuracy": round(sum(row["correct"] for row in bucket) / len(bucket), 4) if bucket else None,
        }

    bins = []
    for lower, upper in [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]:
        bucket = [row for row in rows if lower <= row["confidence"] < upper]
        bins.append(
            {
                "range": f"{lower:.2f}-{min(upper, 1.0):.2f}",
                "count": len(bucket),
                "accuracy": round(sum(row["correct"] for row in bucket) / len(bucket), 4) if bucket else None,
                "mean_selected_probability": mean("selected_probability", bucket),
            }
        )

    latencies = sorted(row["latency_ms"] for row in rows)
    p95_index = int(0.95 * (len(latencies) - 1)) if latencies else 0

    return {
        "total": total,
        "correct": len(correct),
        "wrong": len(wrong),
        "accuracy": round(len(correct) / total, 4),
        "mean_confidence": mean("confidence", rows),
        "mean_confidence_correct": mean("confidence", correct),
        "mean_confidence_wrong": mean("confidence", wrong),
        "mean_selected_probability": mean("selected_probability", rows),
        "mean_selected_probability_correct": mean("selected_probability", correct),
        "mean_selected_probability_wrong": mean("selected_probability", wrong),
        "mean_latency_ms": mean("latency_ms", rows),
        "median_latency_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(latencies[p95_index], 2) if latencies else 0.0,
        "thresholds": thresholds,
        "confidence_bins": bins,
    }


def main() -> int:
    rows = []
    started = time.perf_counter()
    for expected, texts in SEEDS.items():
        for index, text in enumerate(texts, start=1):
            print(f"case {len(rows) + 1:03d}/100 {expected}-{index:02d}", file=sys.stderr)
            try:
                response = post(case_payload(text))
            except urllib.error.URLError as error:
                print(f"request failed: {error}", file=sys.stderr)
                return 2
            answer = response["answers"]["route"]
            choice = answer["choice"]
            probabilities = answer["probabilities"]
            rows.append(
                {
                    "id": f"{expected}-{index:02d}",
                    "expected": expected,
                    "choice": choice,
                    "correct": choice == expected,
                    "confidence": float(answer["confidence"]),
                    "selected_probability": float(probabilities[choice]),
                    "latency_ms": float(response["latency_ms"]),
                    "text": text,
                }
            )

    result = {
        "benchmark": "support-routing-100",
        "url": URL,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "summary": summarize(rows),
        "by_label": {},
        "rows": rows,
    }
    for label in OPTIONS:
        subset = [row for row in rows if row["expected"] == label]
        result["by_label"][label] = summarize(subset)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
