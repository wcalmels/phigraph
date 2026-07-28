from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

@dataclass(frozen=True)
class ApprovalRecord:
    approver: str
    role: str
    approved: bool
    approved_at: str
    rationale: str = ""
    def to_dict(self): return asdict(self)

class DualApprovalGate:
    def __init__(self, required_roles=("operations","safety")):
        self.required_roles = tuple(required_roles)
    def evaluate(self, approvals):
        approved_by_role = {
            item.role: item for item in approvals if item.approved
        }
        missing = tuple(
            role for role in self.required_roles if role not in approved_by_role
        )
        distinct_approvers = {
            item.approver for item in approved_by_role.values()
        }
        passed = not missing and len(distinct_approvers) >= len(self.required_roles)
        return {
            "passed": passed,
            "missing_roles": missing,
            "distinct_approvers": len(distinct_approvers),
        }

def make_approval(approver, role, approved, rationale=""):
    return ApprovalRecord(
        approver=approver,
        role=role,
        approved=approved,
        approved_at=datetime.now(timezone.utc).isoformat(),
        rationale=rationale,
    )
