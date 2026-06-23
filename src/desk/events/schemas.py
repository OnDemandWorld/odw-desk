"""
ODW.ai Desk — Event Schemas

Re-export event schemas from desk.schemas.events.
TBK places event schemas here; implementation lives in desk.schemas.events
for shared access.
"""

from desk.schemas.events import (
    AgentActionEvent,
    AIDecisionEvent,
    ConversationStateEvent,
    InboundMessageEvent,
    OutboundMessageEvent,
    SLABreachEvent,
)

__all__ = [
    "InboundMessageEvent",
    "OutboundMessageEvent",
    "ConversationStateEvent",
    "AIDecisionEvent",
    "SLABreachEvent",
    "AgentActionEvent",
]
