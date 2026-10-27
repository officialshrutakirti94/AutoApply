"""Import every model so ``Base.metadata`` is complete for Alembic and create_all."""

from app.db.models.application import Application
from app.db.models.platform import ExtensionPairingCode, ExtensionToken, PlatformConnection
from app.db.models.profile import Preference, Profile
from app.db.models.qa import QaBankEntry
from app.db.models.run import AgentRun
from app.db.models.safety import SafetyEvent
from app.db.models.user import User, UserSession

__all__ = [
    "AgentRun",
    "Application",
    "ExtensionPairingCode",
    "ExtensionToken",
    "PlatformConnection",
    "Preference",
    "Profile",
    "QaBankEntry",
    "SafetyEvent",
    "User",
    "UserSession",
]
