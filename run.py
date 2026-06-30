#!/usr/bin/env python
import os

from app import app

if __name__ == '__main__':
    # Defaults are safe for production. For local dev, set FLASK_DEBUG=true.
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(threaded=True, debug=debug, host=host, port=port)
