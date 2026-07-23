from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from collections import defaultdict
from functools import wraps

from flask import jsonify, request

from exceptions import ENSPMCPError

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_calls=120, window=60):
        self.max_calls, self.window = max_calls, window
        self.calls = defaultdict(list)
        self.lock = threading.Lock()

    def check(self, key):
        now = time.time()
        with self.lock:
            self.calls[key] = [item for item in self.calls[key] if now - item < self.window]
            if len(self.calls[key]) >= self.max_calls:
                return False
            self.calls[key].append(now)
            return True


def install_error_handlers(app):
    @app.errorhandler(ENSPMCPError)
    def handle_business_error(error):
        logger.info('业务异常: %s', error)
        return jsonify({'success': False, 'error': error.message, 'code': error.code,
                        'details': error.details}), 400


def make_guards():
    api_key = os.environ.get('ENSP_API_KEY', '')
    limiter = RateLimiter()

    def require_auth(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            provided = request.headers.get('X-API-Key', '')
            if api_key and (not provided or not secrets.compare_digest(str(provided), api_key)):
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            return function(*args, **kwargs)
        return wrapped

    def rate_limit(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not limiter.check(request.remote_addr or 'unknown'):
                return jsonify({'success': False, 'error': 'Rate limit exceeded'}), 429
            return function(*args, **kwargs)
        return wrapped

    return require_auth, rate_limit, limiter
