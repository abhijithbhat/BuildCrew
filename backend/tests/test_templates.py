import os
from fastapi import Request
from fastapi.testclient import TestClient
from core.templates import templates, TEMPLATES_DIR
from main import app


def test_jinja2_templates_configuration():
    """Verify Jinja2Templates instance is properly initialized with templates directory."""
    assert templates is not None
    assert os.path.isdir(TEMPLATES_DIR)
    assert os.path.basename(TEMPLATES_DIR) == "templates"


def test_jinja2_template_rendering():
    """Verify Jinja2 template rendering works with FastAPI Request and context variables."""
    test_template_path = os.path.join(TEMPLATES_DIR, "_test_sample.html")
    with open(test_template_path, "w", encoding="utf-8") as f:
        f.write("<h1>Hello, {{ name }}!</h1><p>{{ role }}</p>")

    try:
        # Create a dummy endpoint using the template
        @app.get("/_test/template-render")
        async def sample_render(request: Request):
            return templates.TemplateResponse(
                request=request,
                name="_test_sample.html",
                context={"name": "Alex Rivera", "role": "Backend Lead"},
            )

        client = TestClient(app)
        response = client.get("/_test/template-render")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "<h1>Hello, Alex Rivera!</h1>" in response.text
        assert "<p>Backend Lead</p>" in response.text
    finally:
        if os.path.exists(test_template_path):
            os.remove(test_template_path)
