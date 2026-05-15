from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class ArticleIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    excerpt: str = Field(min_length=10, max_length=500)
    content: str = Field(min_length=20)
    category_id: Optional[int] = None
    tags: list[str] = []
    cover_image: Optional[str] = None
    is_published: bool = False
    scheduled_at: Optional[datetime] = None
    meta_title: Optional[str] = Field(default=None, max_length=255)
    meta_description: Optional[str] = Field(default=None, max_length=320)
    meta_keywords: Optional[str] = None
    canonical_url: Optional[str] = None
    og_image: Optional[str] = None
    schema_type: str = "Article"
    faq_json: Optional[str] = None


class MessageIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    subject: str = Field(min_length=2, max_length=255)
    body: str = Field(min_length=5, max_length=5000)
