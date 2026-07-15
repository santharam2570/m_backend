import os

from dotenv import load_dotenv

load_dotenv()


def _normalize(url, default):
    value = (os.environ.get(url) or default).strip()
    if value and not value.endswith('/'):
        value += '/'
    return value


# Public base URL for this backend (file uploads, attachment links in emails).
BASE_URL = _normalize('BASE_URL', 'http://localhost:5000/')

# Optional client-app URL for deep links in emails (password reset, lead detail).
# Leave unset when running the API without a web client.
CLIENT_APP_URL = _normalize('CLIENT_APP_URL', '').rstrip('/')
