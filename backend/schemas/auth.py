from pydantic import BaseModel, field_validator


class SignUpRequest(BaseModel):
    email: str
    password: str
    name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_min_length(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long.")
        return v



class LoginRequest(BaseModel):
    email: str
    password: str


class VerifyOTPRequest(BaseModel):
    email: str
    token: str
    type: str = "signup"  # 'signup' or 'recovery'


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_min_length(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long.")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RefreshTokenResponse(BaseModel):
    message: str = "Token refreshed successfully"
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    expires_at: int | None = None
    user: dict | None = None

