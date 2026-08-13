from pydantic import BaseModel


class SignUpRequest(BaseModel):
    email: str
    password: str


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

