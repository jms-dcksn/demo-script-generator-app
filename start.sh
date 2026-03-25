#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
  echo "No .env file found. Copy .env.example to .env and set your OPENAI_API_KEY."
  exit 1
fi

docker compose up --build -d
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
