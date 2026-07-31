"""
ODW.ai Desk — SLA Package

SLA timing evaluation, escalation, and due-conversation scanning (V1.1 M3 / F6).
"""

from desk.sla.checker import scan_due_conversations
from desk.sla.policy import SLAPolicy
from desk.sla.service import ACTIVE_STATUSES, SLAService, SLAStatus

__all__ = [
    "SLAPolicy",
    "SLAService",
    "SLAStatus",
    "ACTIVE_STATUSES",
    "scan_due_conversations",
]
