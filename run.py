#!/usr/bin/env python
from app import app

if __name__ == '__main__':
    app.run(threaded=True, debug=True, port=5000, host='localhost')
