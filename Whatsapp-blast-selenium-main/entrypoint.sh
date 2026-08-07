#!/bin/sh
# entrypoint.sh — dijalankan saat container Railway start
# Shell script ini memastikan $PORT ter-expand dengan benar oleh shell
exec gunicorn \
  --bind "0.0.0.0:${PORT:-5000}" \
  --timeout 120 \
  --workers 1 \
  --threads 4 \
  app:app
