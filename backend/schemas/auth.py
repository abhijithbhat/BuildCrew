from pydantic import BaseModel


class SignUpRequest(BaseModel):
    email: str
    password: str
    name: str | None = None



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

