"""Validation and normalization for user identity detail fields."""

import re

AADHAAR_RE = re.compile(r'^\d{12}$')
PAN_RE = re.compile(r'^[A-Z]{5}\d{4}[A-Z]$')
PASSPORT_RE = re.compile(r'^[A-Z0-9]{6,12}$')
REFERENCE_CONTACT_RE = re.compile(r'^\d{10,15}$')

USER_DETAIL_FIELD_ALIASES = {
    'aadhaar': 'aadhaar_number',
    'aadhaar_doc': 'aadhaar_document',
    'pan': 'pan_number',
    'pan_doc': 'pan_document',
    'referredBy': 'referred_by',
    'reference_contact': 'reference_contact_number',
    'reference_phone': 'reference_contact_number',
}

USER_DETAIL_SCALAR_FIELDS = (
    'aadhaar_number',
    'aadhaar_document',
    'pan_number',
    'pan_document',
    'address',
    'source',
    'referred_by',
    'reference_contact_number',
    'passport_number',
)

USER_DETAIL_REQUEST_KEYS = set(USER_DETAIL_SCALAR_FIELDS) | set(USER_DETAIL_FIELD_ALIASES)

USER_DOCUMENT_MAGIC = {
    'image/jpeg': (b'\xff\xd8\xff',),
    'image/png': (b'\x89PNG\r\n\x1a\n',),
    'image/webp': (b'RIFF',),
    'application/pdf': (b'%PDF',),
}


def normalize_user_detail_payload(payload):
    """Map frontend aliases to canonical keys and normalize string values."""
    if not payload:
        return {}

    normalized = {}
    for key, value in payload.items():
        canonical = USER_DETAIL_FIELD_ALIASES.get(key, key)
        if canonical not in USER_DETAIL_SCALAR_FIELDS:
            continue
        if value is None:
            normalized[canonical] = None
            continue
        if canonical in ('aadhaar_number', 'reference_contact_number'):
            normalized[canonical] = re.sub(r'\D', '', str(value).strip())
            continue
        if canonical in ('pan_number', 'passport_number'):
            text = str(value).strip().upper()
            normalized[canonical] = text or None
            continue
        text = str(value).strip()
        normalized[canonical] = text or None

    return normalized


def _validate_scalar_fields(data, require_documents=False, existing_user=None):
    errors = []

    aadhaar = data.get('aadhaar_number')
    if aadhaar is None and existing_user:
        aadhaar = existing_user.get('aadhaar_number')
    if not aadhaar:
        errors.append('Aadhaar number is required.')
    elif not AADHAAR_RE.match(str(aadhaar)):
        errors.append('Aadhaar number must be exactly 12 digits.')

    pan = data.get('pan_number')
    if pan is None and existing_user:
        pan = existing_user.get('pan_number')
    if not pan:
        errors.append('PAN number is required.')
    elif not PAN_RE.match(str(pan)):
        errors.append('PAN number must match format ABCDE1234F.')

    address = data.get('address')
    if address is None and existing_user:
        address = existing_user.get('address')
    if not address:
        errors.append('Address is required.')
    elif len(str(address)) > 500:
        errors.append('Address must be at most 500 characters.')

    source = data.get('source')
    if source is None and existing_user:
        source = existing_user.get('source')
    if not source:
        errors.append('Source is required.')
    elif len(str(source)) > 100:
        errors.append('Source must be at most 100 characters.')

    referred_by = data.get('referred_by')
    if referred_by is None and existing_user:
        referred_by = existing_user.get('referred_by')
    if not referred_by:
        errors.append('Referred by is required.')
    elif len(str(referred_by)) > 100:
        errors.append('Referred by must be at most 100 characters.')

    reference_contact = data.get('reference_contact_number')
    if reference_contact is None and existing_user:
        reference_contact = existing_user.get('reference_contact_number')
    if not reference_contact:
        errors.append('Reference contact number is required.')
    elif not REFERENCE_CONTACT_RE.match(str(reference_contact)):
        errors.append('Reference contact number must be 10 to 15 digits.')

    passport = data.get('passport_number')
    if passport is None and existing_user:
        passport = existing_user.get('passport_number')
    if passport and not PASSPORT_RE.match(str(passport)):
        errors.append('Passport number must be 6 to 12 alphanumeric characters.')

    if require_documents:
        aadhaar_doc = data.get('aadhaar_document')
        if aadhaar_doc is None and existing_user:
            aadhaar_doc = existing_user.get('aadhaar_document')
        if not aadhaar_doc:
            errors.append('Aadhaar document is required.')

        pan_doc = data.get('pan_document')
        if pan_doc is None and existing_user:
            pan_doc = existing_user.get('pan_document')
        if not pan_doc:
            errors.append('PAN document is required.')

    return errors


def has_user_detail_fields(payload):
    if not payload:
        return False
    return any(key in payload for key in USER_DETAIL_REQUEST_KEYS)


def validate_user_details(payload, require_documents=False, existing_user=None):
    """Validate user detail fields. Returns a list of error messages."""
    data = normalize_user_detail_payload(payload)
    return _validate_scalar_fields(
        data,
        require_documents=require_documents,
        existing_user=existing_user,
    )


def validate_user_document_file(file, allowed_extensions, allowed_mime_types, max_size_bytes):
    """Validate uploaded identity document. Returns (error_message or None)."""
    if not file or not getattr(file, 'filename', None):
        return 'Document file is required.'

    filename = file.filename
    if '.' not in filename:
        return 'Invalid file type. Allowed: JPG, JPEG, PNG, WEBP, PDF'

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return 'Invalid file type. Allowed: JPG, JPEG, PNG, WEBP, PDF'

    content_type = (getattr(file, 'content_type', None) or '').lower()
    if content_type and content_type not in allowed_mime_types:
        return 'Invalid file type. Allowed: JPG, JPEG, PNG, WEBP, PDF'

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_size_bytes:
        return 'Document must be under 5 MB'

    header = file.read(16)
    file.seek(0)
    if not header:
        return 'Invalid or empty document file.'

    if content_type in USER_DOCUMENT_MAGIC:
        signatures = USER_DOCUMENT_MAGIC[content_type]
        if content_type == 'image/webp':
            if not (header.startswith(b'RIFF') and header[8:12] == b'WEBP'):
                return 'Invalid file content for declared type.'
        elif not any(header.startswith(sig) for sig in signatures):
            return 'Invalid file content for declared type.'
    else:
        known = False
        for mime, signatures in USER_DOCUMENT_MAGIC.items():
            if mime == 'image/webp':
                if header.startswith(b'RIFF') and header[8:12] == b'WEBP':
                    known = True
                    break
            elif any(header.startswith(sig) for sig in signatures):
                known = True
                break
        if not known:
            return 'Invalid file type. Allowed: JPG, JPEG, PNG, WEBP, PDF'

    return None
