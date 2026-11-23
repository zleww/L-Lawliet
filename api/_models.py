"""Pydantic request models. Limits match the CHECK constraints in scripts/schema.sql."""
import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Category = Literal[
    "Technology & Crime",
    "Finance & Taxes",
    "Governance & Business",
    "Social & Welfare",
    "Environment",
    "Education & Civil Rights",
]
Status = Literal["Active", "Amended", "Repealed"]


def Text(lo: int, hi: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=lo, max_length=hi)]


HttpsUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=500, pattern=r"^https://")
]


class LawCreate(BaseModel):
    """Every field required (status defaults to Active). Unknown fields are rejected."""
    model_config = ConfigDict(extra="forbid")

    ra_number: Text(3, 20)
    official_title: Text(3, 300)
    plain_title: Text(3, 200)
    category: Category
    year: int = Field(ge=1900, le=2100)
    status: Status = "Active"
    reading_time_minutes: int = Field(ge=1, le=120)
    importance_rating: int = Field(ge=1, le=5)
    tldr_summary: Text(10, 500)
    full_breakdown: Text(10, 2000)
    why_it_matters: Text(5, 1000)
    example_scenario: Text(10, 1000)
    penalties: Text(5, 1000)
    min_fine_php: int = Field(ge=0)
    total_sections: int = Field(ge=1, le=1000)
    enacting_president: Text(3, 100)
    target_audience: Text(3, 300)
    source_url: HttpsUrl


class LawUpdate(BaseModel):
    """Same rules as LawCreate, but every field optional. At least one must be sent, none may be null."""
    model_config = ConfigDict(extra="forbid")

    ra_number: Optional[Text(3, 20)] = None
    official_title: Optional[Text(3, 300)] = None
    plain_title: Optional[Text(3, 200)] = None
    category: Optional[Category] = None
    year: Optional[int] = Field(default=None, ge=1900, le=2100)
    status: Optional[Status] = None
    reading_time_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    importance_rating: Optional[int] = Field(default=None, ge=1, le=5)
    tldr_summary: Optional[Text(10, 500)] = None
    full_breakdown: Optional[Text(10, 2000)] = None
    why_it_matters: Optional[Text(5, 1000)] = None
    example_scenario: Optional[Text(10, 1000)] = None
    penalties: Optional[Text(5, 1000)] = None
    min_fine_php: Optional[int] = Field(default=None, ge=0)
    total_sections: Optional[int] = Field(default=None, ge=1, le=1000)
    enacting_president: Optional[Text(3, 100)] = None
    target_audience: Optional[Text(3, 300)] = None
    source_url: Optional[HttpsUrl] = None

    @model_validator(mode="after")
    def at_least_one_non_null_field(self):
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("Send at least one field to update.")
        nulls = [name for name, value in sent.items() if value is None]
        if nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(nulls)}")
        return self


class CommentSubmission(BaseModel):
    user_name: Text(1, 100)
    comment: Text(1, 1000)


class LoginRequest(BaseModel):
    username: Text(1, 50)
    password: str = Field(min_length=1, max_length=200)


# ----------------------------------------------------------------------
# Accounts
# ----------------------------------------------------------------------
Username = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_.]+$")
]
Theme = Literal["dark", "light"]
Accent = Literal["gold", "blue", "green", "rose"]


def check_password_rules(password: str) -> str:
    """Password rules: 8+ characters, at least one letter and one number, and at most
    72 bytes (bcrypt ignores anything after 72 bytes, so longer passwords are refused)."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(password.encode()) > 72:
        raise ValueError("Password must be at most 72 bytes (about 72 characters).")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise ValueError("Password must contain at least one letter and one number.")
    return password


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    password: str = Field(max_length=200)
    display_name: Optional[Text(1, 100)] = None

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return check_password_rules(value)

    @model_validator(mode="after")
    def password_not_username(self):
        if self.password.lower() == self.username.lower():
            raise ValueError("Password cannot be the same as the username.")
        return self


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)  # the ID token from Google's button


class ProfileUpdate(BaseModel):
    """Every field optional, at least one required. An empty bio clears it."""
    model_config = ConfigDict(extra="forbid")

    display_name: Optional[Text(1, 100)] = None
    bio: Optional[Text(0, 300)] = None
    theme: Optional[Theme] = None
    accent: Optional[Accent] = None

    @model_validator(mode="after")
    def at_least_one_non_null_field(self):
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("Send at least one field to update.")
        nulls = [name for name, value in sent.items() if value is None]
        if nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(nulls)}")
        return self


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(max_length=200)

    @field_validator("new_password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return check_password_rules(value)


class DeleteAccountRequest(BaseModel):
    """confirm must be the account's username. password is required if the account has one."""
    model_config = ConfigDict(extra="forbid")

    confirm: str = Field(min_length=1, max_length=50)
    password: Optional[str] = Field(default=None, max_length=200)


class CommentEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: Text(1, 1000)


# ----------------------------------------------------------------------
# Saved laws, ratings, votes, reports, suggestions
# ----------------------------------------------------------------------
_RA_PATTERN = re.compile(r"^(?:R\.?\s*A\.?\s*(?:No\.?\s*)?)?(\d{1,5})$", re.IGNORECASE)


def normalize_ra_number(value: str) -> str:
    """'11036', 'ra 11036', 'R.A. No. 11036' -> 'RA 11036' (the format stored in laws)."""
    match = _RA_PATTERN.match(value.strip())
    if not match:
        raise ValueError("Use an RA number like RA 11036.")
    return f"RA {int(match.group(1))}"


class RatingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)


ReportReason = Literal["spam", "offensive", "wrong_info", "other"]


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: ReportReason
    details: Optional[Text(0, 500)] = None


class ReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["dismissed"]


class SuggestionCreate(BaseModel):
    """The short form: the admin completes the full law when approving."""
    model_config = ConfigDict(extra="forbid")

    ra_number: str = Field(max_length=30)
    title: Text(3, 200)
    reason: Text(10, 1000)
    source_url: Optional[HttpsUrl] = None

    @field_validator("ra_number")
    @classmethod
    def ra_format(cls, value: str) -> str:
        return normalize_ra_number(value)


class SuggestionReview(BaseModel):
    """Approve (pointing at the law that was created for it) or reject, with an optional note."""
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"]
    admin_note: Optional[Text(0, 500)] = None
    law_id: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def approval_needs_law(self):
        if self.status == "approved" and self.law_id is None:
            raise ValueError("Approving needs law_id: the law created for this suggestion.")
        return self


# ----------------------------------------------------------------------
# Study data (used by JurisCard)
# ----------------------------------------------------------------------
CardStatus = Literal["new", "review", "mastered"]


class FlashcardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    question: Text(5, 300)
    answer: Text(2, 1500)
    source: Optional[Text(0, 100)] = None


class FlashcardUpdate(BaseModel):
    """Every field optional, at least one required."""
    model_config = ConfigDict(extra="forbid")

    category: Optional[Category] = None
    question: Optional[Text(5, 300)] = None
    answer: Optional[Text(2, 1500)] = None
    source: Optional[Text(0, 100)] = None
    status: Optional[CardStatus] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("Send at least one field to update.")
        nulls = [name for name, value in sent.items() if value is None and name != "source"]
        if nulls:
            raise ValueError(f"These fields cannot be null: {', '.join(nulls)}")
        return self


class ProgressUpdate(BaseModel):
    """'new' clears the mark."""
    model_config = ConfigDict(extra="forbid")

    status: CardStatus


class QuizResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=50)
    total: int = Field(ge=1, le=50)
    category: Optional[Category] = None

    @model_validator(mode="after")
    def score_within_total(self):
        if self.score > self.total:
            raise ValueError("Score cannot be higher than the number of questions.")
        return self


class StudyPrefsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_length: Optional[Literal[5, 10, 15, 20]] = None
    daily_goal: Optional[int] = Field(default=None, ge=1, le=100)
    hide_mastered: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("Send at least one field to update.")
        if any(value is None for value in sent.values()):
            raise ValueError("Fields cannot be null.")
        return self


# ----------------------------------------------------------------------
# Game data (used by JustGiveupATP / JurisCards Arena)
# ----------------------------------------------------------------------
CaseId = Annotated[str, StringConstraints(min_length=1, max_length=60, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


class ArenaResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: CaseId
    tier: int = Field(ge=1, le=3)
    won: bool
    turns: int = Field(ge=0, le=500)
    jp_left: int = Field(ge=0, le=1000)


class ArenaPrefsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_abandon: Optional[bool] = None
    reduce_motion: Optional[bool] = None
    hide_won: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("Send at least one field to update.")
        if any(value is None for value in sent.values()):
            raise ValueError("Fields cannot be null.")
        return self
