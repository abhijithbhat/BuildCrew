import os
from fastapi.templating import Jinja2Templates

# Path to the templates directory inside backend/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure the templates directory exists
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Shared Jinja2Templates instance for rendering server-side templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)
