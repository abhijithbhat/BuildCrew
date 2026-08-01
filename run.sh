#!/bin/bash
source "$(dirname "$0")/venv/bin/activate"
uvicorn main:app --reload --host 0.0.0.0 --port 8000

