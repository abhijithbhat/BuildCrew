import os
from typing import Optional
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Path to the templates directory inside backend/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure the templates directory exists
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Shared Jinja2Templates instance for rendering server-side templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def should_render_html(accept_header: Optional[str], format_param: Optional[str]) -> bool:
    """
    Determine whether to render HTML or return JSON on passport routes.
    Render HTML unless ?format=json or the Accept header lists application/json before text/html.
    */* and a missing Accept header must return HTML.
    """
    if format_param == "json":
        return False
    if not accept_header:
        return True
    accept_lower = accept_header.lower()
    if accept_lower.strip() == "*/*":
        return True
    if "application/json" in accept_lower:
        if "text/html" in accept_lower:
            return accept_lower.find("text/html") < accept_lower.find("application/json")
        return False
    return True


def render_branded_error_page(status_code: int, message: Optional[str] = None) -> HTMLResponse:
    """
    Return a small branded HTML error page (emerald #064E3B / champagne #F8E7C9, no JSON)
    with the exact status code.
    """
    if status_code == 404:
        title = "Passport not found"
        desc = message or "The requested passport does not exist or has not been published yet."
    elif status_code == 503:
        title = "Temporarily unavailable, try again shortly"
        desc = message or "The passport service is temporarily unavailable. Please try again shortly."
    else:
        title = f"Error {status_code}"
        desc = message or "An error occurred while processing the passport."

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>{title} — BuildCrew</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            background-color: #064E3B;
            color: #F8E7C9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }}
        .error-card {{
            background: rgba(4, 56, 42, 0.95);
            border: 1px solid rgba(248, 231, 201, 0.35);
            border-radius: 16px;
            padding: 48px 36px;
            max-width: 480px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
        }}
        .status-badge {{
            display: inline-block;
            background: #F8E7C9;
            color: #064E3B;
            font-weight: 700;
            font-size: 13px;
            padding: 5px 14px;
            border-radius: 9999px;
            margin-bottom: 20px;
            letter-spacing: 0.05em;
        }}
        h1 {{
            color: #F8E7C9;
            font-size: 24px;
            font-weight: 700;
            line-height: 1.3;
            margin-bottom: 14px;
        }}
        p {{
            color: rgba(248, 231, 201, 0.85);
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 28px;
        }}
        .brand-link {{
            color: #F8E7C9;
            font-size: 13px;
            text-decoration: none;
            opacity: 0.75;
            transition: opacity 0.2s;
        }}
        .brand-link:hover {{
            opacity: 1;
        }}
    </style>
</head>
<body>
    <div class="error-card">
        <div class="status-badge">HTTP {status_code}</div>
        <h1>{title}</h1>
        <p>{desc}</p>
        <span class="brand-link">BuildCrew Contribution Passport Verification</span>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status_code)
