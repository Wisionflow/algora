"""Pydantic models for Algora Growth Agent."""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel


class Chat(BaseModel):
    id: Optional[int] = None
    telegram_id: int
    title: str
    topic: str  # marketplace | china_import | business
    member_count: int = 0
    rules_summary: Optional[str] = None
    our_status: str = "joined"  # joined | left | banned
    joined_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class Message(BaseModel):
    id: Optional[int] = None
    chat_id: int
    telegram_message_id: int
    sender_name: str
    text: str
    is_relevant: bool = False
    relevance_score: float = 0.0
    created_at: Optional[datetime] = None


class Response(BaseModel):
    id: Optional[int] = None
    message_id: int
    chat_id: int
    response_text: str
    included_channel_link: bool = False
    llm_model: str = ""
    llm_cost: float = 0.0
    sent_at: Optional[datetime] = None
    reaction: str = "unknown"  # positive | negative | neutral | unknown


class Metrics(BaseModel):
    id: Optional[int] = None
    date: date
    channel_subscribers: int = 0
    new_subscribers: int = 0
    messages_sent: int = 0
    chats_active: int = 0
    best_chat_id: Optional[int] = None
    total_llm_cost: float = 0.0


class Schedule(BaseModel):
    id: Optional[int] = None
    chat_id: int
    max_messages_per_day: int = 3
    messages_today: int = 0
    last_message_at: Optional[datetime] = None
    is_active: bool = True
    cooldown_until: Optional[datetime] = None


# Used internally by Brain to represent a decision
class BrainDecision(BaseModel):
    should_respond: bool
    reason: str
    response_text: Optional[str] = None
    include_channel_link: bool = False
    llm_model: str = ""
    llm_cost: float = 0.0
