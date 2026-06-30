import logging
import os
import smtplib

from flask import current_app
from flask_mail import Message

import app_config

logger = logging.getLogger(__name__)

_PLACEHOLDER_MAIL_VALUES = {
    '',
    'your-gmail@gmail.com',
    'your-16-char-app-password',
    'PASTE_YOUR_APP_PASSWORD_HERE',
}


def mail_credentials_configured():
    username = current_app.config.get('MAIL_USERNAME', '')
    password = current_app.config.get('MAIL_PASSWORD', '')
    return (
        username not in _PLACEHOLDER_MAIL_VALUES
        and password not in _PLACEHOLDER_MAIL_VALUES
    )


def _resolve_sender(sender=None):
    configured_sender = current_app.config.get('MAIL_DEFAULT_SENDER', app_config.DEFAULT_FROM_EMAIL)
    if not sender or sender == app_config.DEFAULT_FROM_EMAIL:
        return configured_sender
    return sender


def log_otp_for_dev(to_email, verify_otp, reason):
    if not current_app.config.get('DEV_LOG_OTP', False):
        return
    print(
        f'\n[DEV OTP] {reason}\n'
        f'[DEV OTP] Email: {to_email}\n'
        f'[DEV OTP] Code:  {verify_otp}\n'
    )


def send_auth_email(to_email, subject, html, sender=None, cc=None, bcc=None, verify_otp=None):
    if not current_app.config.get('MAIL_ENABLED', False):
        logger.info('Email delivery skipped (MAIL_ENABLED=false): %s', subject)
        if verify_otp:
            log_otp_for_dev(to_email, verify_otp, 'Mail disabled; use this OTP for local testing')
        return False

    if not mail_credentials_configured():
        logger.error(
            'Gmail SMTP credentials missing. Set MAIL_PASSWORD in .env to your Google App Password: '
            'https://myaccount.google.com/apppasswords'
        )
        if verify_otp:
            log_otp_for_dev(to_email, verify_otp, 'Mail not configured; use this OTP for local testing')
        return False

    mail = current_app.extensions.get('mail')
    if mail is None:
        raise RuntimeError('Flask-Mail is not initialized')

    resolved_sender = _resolve_sender(sender)
    msg = Message(
        subject=subject,
        recipients=[to_email],
        cc=cc or [],
        bcc=bcc or [],
        sender=resolved_sender,
        html=html,
    )
    try:
        mail.send(msg)
    except smtplib.SMTPAuthenticationError:
        logger.error(
            'Gmail rejected login for %s. Use a Google App Password (not your normal password): '
            'https://myaccount.google.com/apppasswords',
            current_app.config.get('MAIL_USERNAME'),
        )
        if verify_otp:
            log_otp_for_dev(to_email, verify_otp, 'Gmail auth failed; use this OTP for local testing')
        return False
    except Exception:
        logger.exception('Failed to send email to %s (%s)', to_email, subject)
        if verify_otp:
            log_otp_for_dev(to_email, verify_otp, 'Mail send failed; use this OTP for local testing')
        return False

    logger.info('Email sent to %s (%s)', to_email, subject)
    return True


def send_signup_email(to_email, subject, html, from_email=None, verify_otp=None):
    return send_auth_email(
        to_email,
        subject,
        html,
        sender=from_email,
        verify_otp=verify_otp,
    )


def _parse_email_list(value):
    if not value or str(value).strip().lower() in ('none', 'null', 'undefined'):
        return []
    return [email.strip() for email in str(value).split(',') if email.strip()]


def _resolve_local_attachment_paths(attachment_list):
    if not attachment_list or str(attachment_list).strip().lower() in ('none', 'null', 'undefined'):
        return []

    paths = []
    base_url = app_config.BASE_URL.rstrip('/')
    for raw_url in str(attachment_list).split(','):
        url = raw_url.strip()
        if not url:
            continue

        local_path = url
        if url.startswith('http://') or url.startswith('https://'):
            marker = '/uploads/'
            if marker in url:
                local_path = 'uploads/' + url.split(marker, 1)[1]
            elif url.startswith(base_url):
                local_path = url[len(base_url):].lstrip('/')

        local_path = local_path.lstrip('/')
        if os.path.isfile(local_path):
            paths.append(local_path)
        else:
            logger.warning('Attachment not found on disk: %s', local_path)
    return paths


def send_crm_email(from_email, to, subject, html, cc=None, bcc=None, attachments=None):
    if not current_app.config.get('MAIL_ENABLED', False):
        logger.info('CRM email delivery skipped (MAIL_ENABLED=false): %s', subject)
        return False

    if not mail_credentials_configured():
        logger.error(
            'Gmail SMTP credentials missing. Set MAIL_PASSWORD in .env to your Google App Password: '
            'https://myaccount.google.com/apppasswords'
        )
        return False

    recipients = _parse_email_list(to)
    if not recipients:
        logger.error('CRM email has no recipients')
        return False

    mail = current_app.extensions.get('mail')
    if mail is None:
        raise RuntimeError('Flask-Mail is not initialized')

    resolved_sender = _resolve_sender(from_email)
    msg = Message(
        subject=subject,
        recipients=recipients,
        cc=_parse_email_list(cc),
        bcc=_parse_email_list(bcc),
        sender=resolved_sender,
        html=html,
    )

    for attachment_path in attachments or []:
        try:
            msg.attach(
                filename=os.path.basename(attachment_path),
                content_type=None,
                data=open(attachment_path, 'rb').read(),
            )
        except OSError:
            logger.exception('Failed to attach file: %s', attachment_path)

    try:
        mail.send(msg)
    except smtplib.SMTPAuthenticationError:
        logger.error(
            'Gmail rejected login for %s. Use a Google App Password (not your normal password): '
            'https://myaccount.google.com/apppasswords',
            current_app.config.get('MAIL_USERNAME'),
        )
        return False
    except Exception:
        logger.exception('Failed to send CRM email (%s)', subject)
        return False

    logger.info('CRM email sent to %s (%s)', ', '.join(recipients), subject)
    return True
