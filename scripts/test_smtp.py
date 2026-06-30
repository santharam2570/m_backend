#!/usr/bin/env python
"""Quick Gmail SMTP check. Run: python scripts/test_smtp.py"""
import os
import smtplib
import sys

from dotenv import load_dotenv

load_dotenv()

server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
port = int(os.environ.get('MAIL_PORT', '587'))
username = os.environ.get('MAIL_USERNAME', '').strip()
password = os.environ.get('MAIL_PASSWORD', '').replace(' ', '')
use_tls = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
use_ssl = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
to_email = username

if not username or not password:
    print('ERROR: Set MAIL_USERNAME and MAIL_PASSWORD in .env')
    print('Create an App Password: https://myaccount.google.com/apppasswords')
    sys.exit(1)

try:
    if use_ssl:
        smtp = smtplib.SMTP_SSL(server, port, timeout=15)
    else:
        smtp = smtplib.SMTP(server, port, timeout=15)
        if use_tls:
            smtp.starttls()
    smtp.login(username, password)
    smtp.sendmail(
        username,
        [to_email],
        f'Subject: MAP SMTP test\r\n\r\nIf you see this, Gmail SMTP is working.',
    )
    smtp.quit()
    print(f'OK: Test email sent to {to_email}')
except smtplib.SMTPAuthenticationError:
    print('ERROR: Gmail rejected login (535 BadCredentials).')
    print('- Use a Google App Password, not your normal Gmail password')
    print('- Enable 2-Step Verification first')
    print('- Create App Password: https://myaccount.google.com/apppasswords')
    sys.exit(1)
except Exception as exc:
    print(f'ERROR: {exc}')
    sys.exit(1)
