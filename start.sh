#!/bin/bash

# FastAPI 서버 실행
uv run uvicorn main:app --host 0.0.0.0 --port 39100 --reload --log-level info