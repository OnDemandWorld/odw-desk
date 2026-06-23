"""
ODW.ai Desk — SQLAlchemy Models

All models are imported here so Alembic can detect them for migrations.
"""

from desk.models.base import Base
from desk.models.customer import Customer
from desk.models.conversation import Conversation
from desk.models.message import Message
from desk.models.agent import Agent
from desk.models.ai_configuration import AIConfiguration
from desk.models.audit_log import AuditLog
from desk.models.license_state import LicenseState
from desk.models.brand_persona import BrandPersona
from desk.models.response_policy import ResponsePolicy

__all__ = [
    "Base",
    "Customer",
    "Conversation",
    "Message",
    "Agent",
    "AIConfiguration",
    "AuditLog",
    "LicenseState",
    "BrandPersona",
    "ResponsePolicy",
]
