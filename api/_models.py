"""Pydantic request models. Limits match the CHECK constraints in scripts/schema.sql."""
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
