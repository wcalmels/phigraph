from __future__ import annotations


def compute_cyber_metrics(feedback: list[dict]) -> dict:
    labeled = [
        row
        for row in feedback
        if row["verdict"] in {
            "confirmed",
            "false_positive",
        }
    ]
    confirmed = sum(
        row["verdict"] == "confirmed"
        for row in labeled
    )
    false_positive = sum(
        row["verdict"] == "false_positive"
        for row in labeled
    )
    reviewed = len(feedback)
    return {
        "reviewed_alerts": reviewed,
        "labeled_alerts": len(labeled),
        "confirmed_alerts": confirmed,
        "false_positive_alerts": false_positive,
        "precision": (
            confirmed / len(labeled)
            if labeled
            else None
        ),
        "false_positive_rate": (
            false_positive / len(labeled)
            if labeled
            else None
        ),
        "deferred_rate": (
            sum(row["verdict"] == "deferred" for row in feedback)
            / reviewed
            if reviewed
            else None
        ),
    }
