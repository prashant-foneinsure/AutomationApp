"""Request/response models for the API Testing module."""
from pydantic import BaseModel, Field


# ---------- groups ----------
class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


# ---------- tests ----------
class TestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    curl: str = Field(min_length=1)
    http_method: str | None = None
    sort_order: int | None = None
    notes: str | None = None
    extractors: list[dict] | None = None


class TestUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    curl: str | None = Field(default=None, min_length=1)
    http_method: str | None = None
    sort_order: int | None = None
    notes: str | None = None
    extractors: list[dict] | None = None


# ---------- running ----------
class RunOptions(BaseModel):
    """Credentials entered for this run only; never persisted."""
    token: str = ""
    username: str = ""
    password: str = ""
    instruction: str = ""
    method: str = ""
    # When false, skip asking the model to propose extractors.
    suggest_extractors: bool = True


class AdhocRequest(BaseModel):
    """A one-off run with no saved test behind it."""
    curl: str = Field(min_length=1)
    method: str = ""
    instruction: str = ""
    token: str = ""
    username: str = ""
    password: str = ""


class GroupRunRequest(BaseModel):
    token: str = ""
    username: str = ""
    password: str = ""
    instruction: str = ""
    # Stop the chain at the first test that does not produce a clean baseline.
    stop_on_failure: bool = True


# ---------- feedback ----------
class FeedbackRequest(BaseModel):
    verdict: str = Field(pattern="^(accepted|rejected|edited)$")
    note: str | None = None


class VariableUpdate(BaseModel):
    value: str = ""
