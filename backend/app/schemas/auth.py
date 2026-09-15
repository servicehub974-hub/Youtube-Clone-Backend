from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=60)


class LoginIn(BaseModel):
    identifier: str  # email OR username
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    display_name: str | None = None
    role: str
    email_verified: bool
    avatar_url: str | None = None


class AuthOut(BaseModel):
    access_token: str
    user: UserOut
    # dev-only helper (present when not in production) so email verification
    # can be tested before SMTP sending is wired up.
    verification_token: str | None = None
