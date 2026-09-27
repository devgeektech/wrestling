"""Gunicorn config for Wrestling Guide API on EC2."""

import multiprocessing

bind = '127.0.0.1:8000'
workers = max(2, multiprocessing.cpu_count() * 2 + 1)
threads = 2
timeout = 300
graceful_timeout = 30
keepalive = 5
accesslog = '-'
errorlog = '-'
capture_output = True
raw_env = [
    'DJANGO_SETTINGS_MODULE=config.settings.production',
]
