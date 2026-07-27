"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` — Alembic's
env.py imports it so autogenerate/`create_all` see the full schema.
"""

from app.models.core import Actor, Cycle, SyncState, Team
from app.models.events import Comment, RawEvent
from app.models.insights import Anomaly, Digest
from app.models.issues import Issue, IssueHistory, IssueTag, IssueTagHistory
from app.models.points import PointsEvent, UnscoredTicket
from app.models.zoho import Epic, Project, StatusDef, Tag

__all__ = [
    "Team",
    "Actor",
    "Cycle",
    "SyncState",
    "Issue",
    "IssueHistory",
    "IssueTag",
    "IssueTagHistory",
    "Comment",
    "RawEvent",
    "Anomaly",
    "Digest",
    "Project",
    "Epic",
    "Tag",
    "StatusDef",
    "PointsEvent",
    "UnscoredTicket",
]
