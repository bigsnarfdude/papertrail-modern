"""
Event models and schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from enum import Enum


class EventType(str, Enum):
    """Event types for compliance tracking"""

    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    API_ACCESS = "api_access"
    DATABASE_ACCESS = "database_access"
    FILE_ACCESS = "file_access"
    SECURITY_EVENT = "security_event"
    ERROR_EVENT = "error_event"
    ADMIN_ACTION = "admin_action"
    CUSTOM = "custom"


class Event(BaseModel):
    """Base event model"""

    event_type: EventType
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    system: str = Field(..., description="System or service name")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("timestamp", pre=True)
    def parse_timestamp(cls, v):
        """Parse timestamp from string or datetime"""
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "event_type": "user_login",
                "user_id": "user123",
                "system": "production_db",
                "timestamp": "2025-10-16T10:30:00Z",
                "metadata": {
                    "ip": "192.168.1.1",
                    "status": "success",
                    "location": "San Francisco"
                },
            }
        }


class BatchEventRequest(BaseModel):
    """Batch event submission"""

    events: List[Event] = Field(..., max_length=1000)


class EventResponse(BaseModel):
    """Event submission response"""

    success: bool
    event_id: Optional[str] = None
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DistinctCountResponse(BaseModel):
    """Distinct count query response"""

    metric: str
    system: str
    window: str
    count: int
    accuracy: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ActivityCheckResponse(BaseModel):
    """Activity check response (Bloom filter)"""

    user_id: str
    system: str
    window: str
    accessed: bool
    probability: float
    note: str = "This is a probabilistic result"


class TopKResponse(BaseModel):
    """Top-K heavy hitters response"""

    metric: str
    window: str
    items: List[Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
