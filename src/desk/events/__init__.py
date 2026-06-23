"""
ODW.ai Desk — Event Bus Module

Provides event bus abstraction and implementations.
"""

from desk.events.bus import EventBus
from desk.events.nats import NATSEventBus
from desk.events.redis_streams import RedisStreamsEventBus
from desk.events.schemas import (
    AgentActionEvent,
    AIDecisionEvent,
    ConversationStateEvent,
    InboundMessageEvent,
    OutboundMessageEvent,
    SLABreachEvent,
)

__all__ = [
    "EventBus",
    "RedisStreamsEventBus",
    "NATSEventBus",
    "InboundMessageEvent",
    "OutboundMessageEvent",
    "ConversationStateEvent",
    "AIDecisionEvent",
    "SLABreachEvent",
    "AgentActionEvent",
]
