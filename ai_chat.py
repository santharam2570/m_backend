"""AI chat assistant for MAP CRM."""

import json
import os
import re

from bson import ObjectId

from common_config import Uid
from mongodb import MongoAPI

SYSTEM_PROMPT = """You are MAP AI Assistant, a friendly and knowledgeable CRM copilot for a real estate team.
You help with leads, projects, properties, bookings, payments, follow-ups, and day-to-day CRM questions.
Write like ChatGPT: warm, clear, conversational, and helpful — use natural sentences, not robotic bullet dumps.
Use only the CRM context provided below. Never invent names, numbers, prices, or dates.
When data is available, weave it into a helpful narrative. If something is missing, say so honestly and suggest next steps.
You can answer overview questions (counts, summaries), look up specific records, and give practical follow-up advice."""

MAX_HISTORY_TURNS = 10
MAX_NOTES = 10
MAX_TIMELINE = 10
MAX_CONTEXT_CHARS = 12000
DEFAULT_HF_MODEL = 'HuggingFaceH4/zephyr-7b-beta'
DEFAULT_OPENAI_MODEL = 'gpt-4o-mini'

STOP_WORDS = frozenset({
    'a', 'an', 'the', 'of', 'for', 'to', 'in', 'on', 'at', 'by', 'with',
    'from', 'is', 'are', 'was', 'were', 'be', 'me', 'my', 'i', 'we', 'you',
    'get', 'give', 'show', 'find', 'tell', 'about', 'details', 'detail',
    'info', 'information', 'please', 'can', 'could', 'would', 'want', 'need',
    'lead', 'leads', 'no', 'number', 'num',
})

LEAD_NO_PATTERNS = (
    re.compile(
        r'lead\s*(?:no\.?|number|#)?\s*[:\s]*([A-Za-z]{1,6})[\s\-/]+(\d{1,6})\b',
        re.I,
    ),
    re.compile(
        r'\b([A-Za-z]{1,6})[\s\-/](\d{1,6})\b',
    ),
    re.compile(
        r'lead\s*(?:no\.?|number|#)?\s*[:\s]*(\d{1,6})\b',
        re.I,
    ),
)

PROJECT_NO_PATTERNS = (
    re.compile(
        r'project\s*(?:no\.?|number|#)?\s*[:\s]*([A-Za-z]{1,6})[\s\-/]+(\d{1,6})\b',
        re.I,
    ),
    re.compile(
        r'project\s*(?:no\.?|number|#)?\s*[:\s]*(\d{1,6})\b',
        re.I,
    ),
)

BOOKING_RECEIPT_PATTERN = re.compile(
    r'receipt\s*(?:no\.?|number|#)?\s*[:\s]*([A-Za-z0-9\-/]+)',
    re.I,
)

INTENT_KEYWORDS = {
    'leads': ('lead', 'leads', 'prospect', 'follow-up', 'followup', 'follow up'),
    'projects': ('project', 'projects', 'unit', 'units', 'property', 'properties', 'rera', 'site visit'),
    'bookings': ('booking', 'bookings', 'payment', 'payments', 'receipt', 'registered', 'sold'),
    'metrics': ('how many', 'total', 'summary', 'overview', 'dashboard', 'count', 'metric', 'statistics'),
    'help': ('what can you', 'help me', 'how do i', 'what do you'),
}

PHONE_PATTERN = re.compile(
    r'(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){7,14}\d',
)
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')

LEAD_DISPLAY_FIELDS = (
    ('Lead No', 'lead_no'),
    ('Name', 'name'),
    ('Company', 'company_name'),
    ('Email', 'email'),
    ('Phone', 'phone'),
    ('Alternate Phone', 'alternate_phone'),
    ('WhatsApp', 'whatsapp_no'),
    ('Status', 'lead_status_name'),
    ('Assigned To', 'assigned'),
    ('Source', 'source_name'),
    ('Customer Type', 'customer_type_name'),
    ('Customer Requirement', 'customer_requirement_name'),
    ('Location', 'location'),
    ('Current Staying', 'current_staying'),
    ('Budget', 'budget'),
    ('Timeline', 'timeline'),
    ('Payment Terms', 'payment_terms_name'),
    ('Project', 'project_name'),
    ('Description', 'description'),
    ('Created', 'create_date'),
    ('Next Follow-up', 'next_followup_dates'),
)


class AiChatError(Exception):
    """Raised when the AI provider cannot produce a reply."""


class LeadSearchResult:
    def __init__(self, lead_id=None, matches=None, search_term=None, search_type=None):
        self.lead_id = lead_id
        self.matches = matches or []
        self.search_term = search_term
        self.search_type = search_type


class EntitySearchResult:
    def __init__(self, entity_id=None, matches=None, search_term=None, search_type=None):
        self.entity_id = entity_id
        self.matches = matches or []
        self.search_term = search_term
        self.search_type = search_type


def _ai_provider():
    return os.environ.get('AI_PROVIDER', 'huggingface').strip().lower()


def _ai_configured():
    provider = _ai_provider()
    if provider == 'openai':
        return bool(os.environ.get('OPENAI_API_KEY', '').strip())
    return bool(os.environ.get('HF_TOKEN', '').strip())


def _lead_prefixes(org_id):
    numbering = MongoAPI.getNumberingSettings('lead', org_id) or {}
    prefix = str(numbering.get('prefix') or 'LD').upper()
    return {prefix}


def _project_prefixes(org_id):
    numbering = MongoAPI.getNumberingSettings('project', org_id) or {}
    prefix = str(numbering.get('prefix') or 'PRJ').upper()
    return {prefix}


def _is_valid_lead_prefix(prefix, org_id):
    return prefix.upper() in _lead_prefixes(org_id)


def _is_valid_project_prefix(prefix, org_id):
    return prefix.upper() in _project_prefixes(org_id)


def detect_intents(message):
    text = (message or '').lower()
    intents = set()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            intents.add(intent)
    return intents or {'general'}


def extract_lead_reference(message, org_id):
    text = (message or '').strip()
    if not text:
        return None

    for pattern in LEAD_NO_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        if len(match.groups()) == 2:
            prefix, sequence = match.group(1).upper(), match.group(2)
            if prefix.lower() in STOP_WORDS or not _is_valid_lead_prefix(prefix, org_id):
                continue
            return f'{prefix}/{sequence}'

        sequence = match.group(1)
        if len(sequence) > 6:
            continue
        prefix = next(iter(_lead_prefixes(org_id)))
        return f'{prefix}/{sequence}'
    return None


def extract_phone_number(message):
    text = (message or '').strip()
    if not text:
        return None

    for match in PHONE_PATTERN.finditer(text):
        digits = re.sub(r'\D', '', match.group(0))
        if len(digits) >= 7:
            return digits
    return None


def extract_email(message):
    match = EMAIL_PATTERN.search(message or '')
    return match.group(0) if match else None


def extract_name_hint(message):
    text = (message or '').strip()
    patterns = (
        re.compile(r'(?:named|called|name(?:d)?\s+is)\s+["\']?([^"\']+?)["\']?(?:\?|$|\.)', re.I),
        re.compile(r'(?:company|organisation|organization)\s+["\']?([^"\']+?)["\']?(?:\?|$|\.)', re.I),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


LEADS_FOR_PROJECT_PATTERNS = (
    re.compile(
        r'(?:all\s+)?lead(?:s)?\s+(?:find(?:\s+out)?|show|list|get|search|fetch)',
        re.I,
    ),
    re.compile(r'(?:find|show|list|get|search|fetch)\s+(?:all\s+)?lead(?:s)?', re.I),
    re.compile(r'lead(?:s)?\s+(?:for|of|in|from|related\s+to|associated\s+with)', re.I),
)

PROJECT_NAME_FOR_LEAD_PATTERNS = (
    re.compile(r'(?:for|of|in|from|about)\s+(?:the\s+)?(.+?)\s+project\b', re.I),
    re.compile(r'(?:for|of|in|from|about)\s+(?:the\s+)?project\s+(.+?)(?:\?|$|\.)', re.I),
    re.compile(r'project\s+(?:named|called)\s+["\']?([^"\']+?)["\']?(?:\?|$|\.)', re.I),
)


def is_leads_for_project_query(message):
    text = (message or '').lower()
    if 'lead' not in text or 'project' not in text:
        return False
    return any(pattern.search(message or '') for pattern in LEADS_FOR_PROJECT_PATTERNS)


def extract_project_name_for_lead_query(message):
    text = (message or '').strip()
    for pattern in PROJECT_NAME_FOR_LEAD_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = re.sub(
            r'^(?:all|the|find|out|lead|leads)\s+',
            '',
            match.group(1).strip(),
            flags=re.I,
        ).strip()
        if name and name.lower() not in STOP_WORDS:
            return name
    return None


def resolve_leads_for_project_query(org_id, message, current_user):
    if not is_leads_for_project_query(message):
        return None

    project_name = extract_project_name_for_lead_query(message)
    if not project_name:
        return None

    projects = MongoAPI.search_projects_for_chat(
        org_id, project_name, current_user, limit=10,
    )
    if not projects:
        return LeadSearchResult(search_term=project_name, search_type='project')

    all_leads = []
    seen_ids = set()
    for project in projects:
        leads = MongoAPI.get_leads_for_project_for_chat(
            org_id, project['id'], current_user,
        )
        for lead in leads:
            if lead['id'] in seen_ids:
                continue
            seen_ids.add(lead['id'])
            lead['matched_project'] = project.get('name') or ''
            lead['matched_project_no'] = project.get('project_no') or ''
            all_leads.append(lead)

    return LeadSearchResult(
        matches=all_leads,
        search_term=project_name,
        search_type='project',
    )


def resolve_lead_search(org_id, message, current_user, explicit_lead_id=None):
    if explicit_lead_id:
        return LeadSearchResult(lead_id=explicit_lead_id, search_type='context')

    project_leads = resolve_leads_for_project_query(org_id, message, current_user)
    if project_leads is not None:
        return project_leads

    lead_ref = extract_lead_reference(message, org_id)
    if lead_ref:
        lead_id = MongoAPI.get_lead_id_by_lead_no(org_id, lead_ref, current_user)
        if lead_id:
            return LeadSearchResult(lead_id=lead_id, search_term=lead_ref, search_type='lead_no')
        return LeadSearchResult(search_term=lead_ref, search_type='lead_no')

    phone = extract_phone_number(message)
    if phone:
        matches = MongoAPI.search_leads_for_chat(org_id, phone, current_user)
        if len(matches) == 1:
            return LeadSearchResult(
                lead_id=matches[0]['id'],
                matches=matches,
                search_term=phone,
                search_type='phone',
            )
        if matches:
            return LeadSearchResult(matches=matches, search_term=phone, search_type='phone')
        return LeadSearchResult(search_term=phone, search_type='phone')

    email = extract_email(message)
    if email:
        matches = MongoAPI.search_leads_for_chat(org_id, email, current_user)
        if len(matches) == 1:
            return LeadSearchResult(
                lead_id=matches[0]['id'],
                matches=matches,
                search_term=email,
                search_type='email',
            )
        if matches:
            return LeadSearchResult(matches=matches, search_term=email, search_type='email')
        return LeadSearchResult(search_term=email, search_type='email')

    name_hint = extract_name_hint(message)
    if name_hint:
        matches = MongoAPI.search_leads_for_chat(org_id, name_hint, current_user)
        if len(matches) == 1:
            return LeadSearchResult(
                lead_id=matches[0]['id'],
                matches=matches,
                search_term=name_hint,
                search_type='name',
            )
        if matches:
            return LeadSearchResult(matches=matches, search_term=name_hint, search_type='name')

    return LeadSearchResult()


def resolve_lead_id(org_id, message, current_user, explicit_lead_id=None):
    return resolve_lead_search(org_id, message, current_user, explicit_lead_id).lead_id


def extract_project_reference(message, org_id):
    text = (message or '').strip()
    if not text:
        return None

    for pattern in PROJECT_NO_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if len(match.groups()) == 2:
            prefix, sequence = match.group(1).upper(), match.group(2)
            if not _is_valid_project_prefix(prefix, org_id):
                continue
            return f'{prefix}/{sequence}'
        sequence = match.group(1)
        prefix = next(iter(_project_prefixes(org_id)))
        return f'{prefix}/{sequence}'

    generic = re.search(r'\b([A-Za-z]{1,6})[\s\-/](\d{1,6})\b', text)
    if generic:
        prefix, sequence = generic.group(1).upper(), generic.group(2)
        if prefix.lower() not in STOP_WORDS and _is_valid_project_prefix(prefix, org_id):
            if not _is_valid_lead_prefix(prefix, org_id) or 'project' in text.lower():
                return f'{prefix}/{sequence}'
    return None


PROJECT_CRITERIA_PREFIX = re.compile(
    r'^(?:price|cost|budget|rate|sq\.?\s*ft|per\s+sq\.?\s*ft|per\s+cent|cent|dtcp|rera)\b',
    re.I,
)

PRICE_VALUE_PATTERN = re.compile(
    r'(?:price|cost|budget|rate|sq\.?\s*ft|per\s+sq\.?\s*ft|per\s+cent|cent)'
    r'[^\d₹$]*'
    r'([₹$]?\s*[\d,]+(?:\.\d+)?)',
    re.I,
)

PROJECT_PRICE_PATTERN = re.compile(
    r'project\s+(?:with\s+)?(?:a\s+)?(?:price\s+(?:of\s+|per\s+sq\.?\s*ft\s+)?)?'
    r'([₹$]?\s*[\d,]+(?:\.\d+)?)',
    re.I,
)


def _normalize_numeric_value(text):
    cleaned = re.sub(r'[^\d.]', '', str(text or ''))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def extract_project_price_hint(message):
    text = (message or '').strip()
    if not text:
        return None

    for pattern in (PRICE_VALUE_PATTERN, PROJECT_PRICE_PATTERN):
        match = pattern.search(text)
        if not match:
            continue
        value = _normalize_numeric_value(match.group(1))
        if value is not None and value > 0:
            return value
    return None


def extract_project_field_hint(message):
    text = message or ''
    for field, pattern in (
        ('dtcp', re.compile(r'dtcp\s*(?:no\.?|number|#)?\s*[:\s]*([\w/-]+)', re.I)),
        ('rera', re.compile(r'rera\s*(?:no\.?|number|#)?\s*[:\s]*([\w/-]+)', re.I)),
    ):
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            if value and value.lower() not in STOP_WORDS:
                return field, value
    return None, None


def extract_project_name_hint(message):
    text = (message or '').strip()
    patterns = (
        re.compile(r'(?:project|property)\s+["\']?([^"\']+?)["\']?(?:\?|$|\.)', re.I),
        re.compile(r'(?:about|for)\s+(?:the\s+)?project\s+["\']?([^"\']+?)["\']?(?:\?|$|\.)', re.I),
        re.compile(r'(.+?)\s+project\b', re.I),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            hint = match.group(1).strip()
            hint = re.sub(r'^(?:all|the|find|out|lead|leads)\s+', '', hint, flags=re.I).strip()
            if hint and not PROJECT_CRITERIA_PREFIX.match(hint):
                if hint.lower() not in STOP_WORDS and not is_leads_for_project_query(text):
                    return hint
    return None


def extract_booking_reference(message):
    text = message or ''
    match = BOOKING_RECEIPT_PATTERN.search(text)
    if match:
        value = match.group(1).strip()
        if value.lower() not in STOP_WORDS:
            return value

    match = re.search(r'booking\s+(?:for\s+)?(?:no\.?|number|#)?\s*[:\s]*([A-Za-z0-9\-/]+)', text, re.I)
    if match:
        value = match.group(1).strip()
        if value.lower() not in STOP_WORDS and value.lower() != 'receipt':
            return value
    return None


def extract_search_phrase(message):
    text = (message or '').strip()
    patterns = (
        re.compile(r'(?:search|find|show|list|about)\s+(?:me\s+)?(.+)$', re.I),
        re.compile(r'(?:details?|info(?:rmation)?)\s+(?:of|for|about)\s+(.+)$', re.I),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            phrase = match.group(1).strip(' ?.')
            if phrase and len(phrase) >= 2:
                return phrase
    return None


def resolve_project_search(org_id, message, current_user, explicit_project_id=None):
    if explicit_project_id:
        return EntitySearchResult(entity_id=explicit_project_id, search_type='context')

    project_ref = extract_project_reference(message, org_id)
    if project_ref:
        project_id = MongoAPI.get_project_id_by_project_no(org_id, project_ref, current_user)
        if project_id:
            return EntitySearchResult(
                entity_id=project_id,
                search_term=project_ref,
                search_type='project_no',
            )
        return EntitySearchResult(search_term=project_ref, search_type='project_no')

    price_hint = extract_project_price_hint(message)
    if price_hint is not None:
        matches = MongoAPI.search_projects_by_price_for_chat(
            org_id, price_hint, current_user,
        )
        price_label = f'₹{price_hint:,.0f}'
        if len(matches) == 1:
            return EntitySearchResult(
                entity_id=matches[0]['id'],
                matches=matches,
                search_term=price_label,
                search_type='price',
            )
        if matches:
            return EntitySearchResult(
                matches=matches, search_term=price_label, search_type='price',
            )
        return EntitySearchResult(search_term=price_label, search_type='price')

    field_type, field_value = extract_project_field_hint(message)
    if field_type and field_value:
        matches = MongoAPI.search_projects_for_chat(org_id, field_value, current_user)
        search_term = f'{field_type.upper()} {field_value}'
        if len(matches) == 1:
            return EntitySearchResult(
                entity_id=matches[0]['id'],
                matches=matches,
                search_term=search_term,
                search_type=field_type,
            )
        if matches:
            return EntitySearchResult(
                matches=matches, search_term=search_term, search_type=field_type,
            )
        return EntitySearchResult(search_term=search_term, search_type=field_type)

    name_hint = extract_project_name_hint(message)
    if name_hint:
        matches = MongoAPI.search_projects_for_chat(org_id, name_hint, current_user)
        if len(matches) == 1:
            return EntitySearchResult(
                entity_id=matches[0]['id'],
                matches=matches,
                search_term=name_hint,
                search_type='name',
            )
        if matches:
            return EntitySearchResult(matches=matches, search_term=name_hint, search_type='name')
        return EntitySearchResult(search_term=name_hint, search_type='name')

    intents = detect_intents(message)
    if 'projects' in intents:
        phrase = extract_search_phrase(message)
        if phrase:
            matches = MongoAPI.search_projects_for_chat(org_id, phrase, current_user)
            if len(matches) == 1:
                return EntitySearchResult(
                    entity_id=matches[0]['id'],
                    matches=matches,
                    search_term=phrase,
                    search_type='name',
                )
            if matches:
                return EntitySearchResult(matches=matches, search_term=phrase, search_type='name')

    return EntitySearchResult()


def resolve_booking_search(org_id, message, current_user, explicit_booking_id=None):
    if explicit_booking_id:
        return EntitySearchResult(entity_id=explicit_booking_id, search_type='context')

    receipt = extract_booking_reference(message)
    search_term = receipt
    if not search_term and detect_intents(message) & {'bookings'}:
        search_term = extract_search_phrase(message)

    if search_term:
        matches = MongoAPI.search_bookings_for_chat(org_id, search_term, current_user)
        if len(matches) == 1:
            return EntitySearchResult(
                entity_id=matches[0]['id'],
                matches=matches,
                search_term=search_term,
                search_type='receipt',
            )
        if matches:
            return EntitySearchResult(matches=matches, search_term=search_term, search_type='receipt')
        return EntitySearchResult(search_term=search_term, search_type='receipt')

    return EntitySearchResult()


def build_lead_context(org_id, lead_id, current_user):
    lead = Uid.fix_array3(MongoAPI.get_lead_Details(org_id, lead_id, current_user))
    if not lead or lead == '0':
        return None

    notes = MongoAPI.getNotes(
        org_id,
        current_user,
        ObjectId(lead_id),
        'lead',
        'create_date',
        -1,
    )
    timeline = MongoAPI.getTimeline(
        org_id,
        current_user,
        lead_id,
        'lead',
        'create_date',
        -1,
    )
    projects = MongoAPI.get_lead_suggested_projects(org_id, lead_id)

    return {
        'lead': lead,
        'notes': (Uid.fix_array(notes) or [])[:MAX_NOTES],
        'timeline': (Uid.fix_array(timeline) or [])[:MAX_TIMELINE],
        'suggested_projects': projects,
    }


def build_project_context(org_id, project_id, current_user):
    project = Uid.fix_array3(MongoAPI.get_project_details(org_id, project_id, current_user))
    if not project:
        return None
    return {'project': project}


def build_booking_context(org_id, booking_id, current_user):
    try:
        from models import Booking
        booking = Booking.objects.get(id=ObjectId(booking_id), org_id=int(org_id))
    except Exception:
        return None
    return {'booking': MongoAPI._booking_dict(booking, current_user, org_id)}


def build_crm_context(org_id, message, current_user, page_context=None,
                      lead_result=None, project_result=None, booking_result=None):
    page_context = page_context or {}
    intents = detect_intents(message)
    context = {
        'intents': sorted(intents),
        'snapshot': MongoAPI.get_crm_chat_snapshot(org_id, current_user),
    }

    if lead_result and lead_result.lead_id:
        lead_ctx = build_lead_context(org_id, lead_result.lead_id, current_user)
        if lead_ctx:
            context['lead'] = lead_ctx

    if project_result and project_result.entity_id:
        project_ctx = build_project_context(org_id, project_result.entity_id, current_user)
        if project_ctx:
            context['project'] = project_ctx

    if booking_result and booking_result.entity_id:
        booking_ctx = build_booking_context(org_id, booking_result.entity_id, current_user)
        if booking_ctx:
            context['booking'] = booking_ctx

    if page_context.get('type') == 'project' and not context.get('project'):
        project_id = (page_context.get('project') or {}).get('projectId')
        if project_id:
            project_ctx = build_project_context(org_id, project_id, current_user)
            if project_ctx:
                context['project'] = project_ctx

    if page_context.get('type') == 'booking' and not context.get('booking'):
        booking_id = (page_context.get('booking') or {}).get('bookingId')
        if booking_id:
            booking_ctx = build_booking_context(org_id, booking_id, current_user)
            if booking_ctx:
                context['booking'] = booking_ctx

    if 'leads' in intents and not context.get('lead') and lead_result and lead_result.matches:
        if lead_result.search_type == 'project':
            context['project_leads'] = {
                'project_name': lead_result.search_term,
                'leads': lead_result.matches,
            }
        else:
            context['lead_matches'] = lead_result.matches

    if 'projects' in intents and not context.get('project') and project_result and project_result.matches:
        context['project_matches'] = project_result.matches

    if 'bookings' in intents and not context.get('booking') and booking_result and booking_result.matches:
        context['booking_matches'] = booking_result.matches

    return context


def _format_field_value(value):
    if value is None or value == '':
        return None
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return ', '.join(cleaned) if cleaned else None
    return str(value).strip()


def format_lead_reply(lead_context, user_message=''):
    lead = (lead_context or {}).get('lead') or {}
    if not lead:
        return "I looked through the CRM but couldn't pull up details for that lead."

    name = _format_field_value(lead.get('name')) or 'this contact'
    lead_no = _format_field_value(lead.get('lead_no'))
    intro = f"Here’s what I found for **{name}**"
    if lead_no:
        intro += f" ({lead_no})"
    intro += ':'

    summary_parts = []
    company = _format_field_value(lead.get('company_name'))
    if company:
        summary_parts.append(f"they work with **{company}**")

    contact_bits = []
    for label, key in (('email', 'email'), ('phone', 'phone'), ('WhatsApp', 'whatsapp_no')):
        value = _format_field_value(lead.get(key))
        if value:
            contact_bits.append(f"**{value}**")
    if contact_bits:
        summary_parts.append(f"you can reach them at {' or '.join(contact_bits)}")

    status = _format_field_value(lead.get('lead_status_name'))
    assigned = _format_field_value(lead.get('assigned'))
    if status or assigned:
        status_line = []
        if status:
            status_line.append(f"status is **{status}**")
        if assigned:
            status_line.append(f"assigned to **{assigned}**")
        summary_parts.append(' and '.join(status_line))

    location = _format_field_value(lead.get('location'))
    if location:
        summary_parts.append(f"they’re based in **{location}**")

    lines = [intro, '']
    if summary_parts:
        sentences = []
        for part in summary_parts:
            sentence = part if part.endswith('.') else f'{part}.'
            sentence = sentence[0].upper() + sentence[1:]
            sentences.append(sentence)
        lines.append(' '.join(sentences))
        lines.append('')

    detail_lines = []
    shown = {'name', 'company_name', 'email', 'phone', 'whatsapp_no', 'lead_status_name', 'assigned', 'location'}
    for label, key in LEAD_DISPLAY_FIELDS:
        if key in shown:
            continue
        value = _format_field_value(lead.get(key))
        if value:
            detail_lines.append(f"- **{label}:** {value}")

    if detail_lines:
        lines.append('**Other details:**')
        lines.extend(detail_lines)

    notes = lead_context.get('notes') or []
    note_texts = [
        _format_field_value(note.get('note'))
        for note in notes[:MAX_NOTES]
        if _format_field_value(note.get('note'))
    ]
    if note_texts:
        lines.append('')
        lines.append('**Notes:**')
        for note_text in note_texts:
            lines.append(f"- {note_text}")

    timeline = lead_context.get('timeline') or []
    activity_titles = [
        _format_field_value(item.get('title') or item.get('text_info'))
        for item in timeline[:MAX_TIMELINE]
        if _format_field_value(item.get('title') or item.get('text_info'))
    ]
    if activity_titles:
        lines.append('')
        lines.append('**Recent activity:**')
        for title in activity_titles:
            lines.append(f"- {title}")

    follow_up = _format_field_value(lead.get('next_followup_dates'))
    if follow_up:
        lines.append('')
        lines.append(f"**Next follow-up:** {follow_up}")

    if len(lines) <= 2:
        return (
            f"I found **{name}** in the system, but most profile fields haven’t been filled in yet. "
            "You can open the lead record to add more details."
        )
    return '\n'.join(lines)


def format_project_leads_reply(search_result):
    project_name = search_result.search_term or 'that project'
    leads = search_result.matches or []
    if not leads:
        return (
            f"I couldn't find any leads linked to **{project_name}**. "
            "Try the exact project name or a project number like PRJ/2."
        )

    lines = [
        f"I found **{len(leads)} lead(s)** for **{project_name}**:",
        '',
    ]
    for lead in leads:
        parts = [lead.get('name') or 'Unnamed lead']
        if lead.get('lead_no'):
            parts.append(lead['lead_no'])
        if lead.get('phone'):
            parts.append(lead['phone'])
        if lead.get('matched_project_no'):
            parts.append(lead['matched_project_no'])
        link_type = lead.get('link_type')
        if link_type == 'matched' and lead.get('match_reasons'):
            parts.append(', '.join(lead['match_reasons']))
        lines.append(f"- {' · '.join(parts)}")
    lines.append('')
    lines.append('Ask for a lead number like LD/7 to see full details for one contact.')
    return '\n'.join(lines)


def format_multiple_matches_reply(matches, search_type, search_term):
    type_labels = {
        'phone': 'phone number',
        'email': 'email',
        'name': 'name',
        'lead_no': 'lead number',
    }
    label = type_labels.get(search_type, 'search')
    lines = [
        f"I found **{len(matches)} leads** matching that {label}. Which one did you mean?",
        '',
    ]
    for match in matches[:5]:
        parts = [match.get('name') or 'Unnamed lead']
        if match.get('lead_no'):
            parts.append(match['lead_no'])
        if match.get('phone'):
            parts.append(match['phone'])
        if match.get('company_name'):
            parts.append(match['company_name'])
        lines.append(f"- {' · '.join(parts)}")
    lines.append('')
    lines.append('Reply with the lead number (e.g. LD/6) or name to see full details.')
    return '\n'.join(lines)


def format_not_found_reply(search_result):
    search_type = search_result.search_type
    search_term = search_result.search_term or 'that'

    if search_type == 'phone':
        return (
            f"I couldn’t find any active lead with the phone number **{search_term}**. "
            "Double-check the number, or try searching by lead number (e.g. LD/6) or name."
        )
    if search_type == 'email':
        return (
            f"I couldn’t find any active lead with the email **{search_term}**. "
            "Try a different email or search by lead number instead."
        )
    if search_type == 'lead_no':
        return (
            f"I couldn’t find an active lead matching **{search_term}**. "
            "Please check the lead number and try again."
        )
    if search_type == 'name':
        return (
            f"I couldn’t find any active lead matching the name **{search_term}**. "
            "Try the full name, company name, phone number, or lead number."
        )
    return (
        "I’m not sure which lead you mean yet. You can ask by **lead number** (LD/7), "
        "**phone number**, **email**, or **name** — for example: “Show me details for LD/6” "
        "or “Find lead with phone 9244432777”."
    )


def format_project_reply(project_context):
    project = (project_context or {}).get('project') or {}
    if not project:
        return "I couldn’t find that project in the CRM."

    name = _format_field_value(project.get('name')) or 'this project'
    project_no = _format_field_value(project.get('project_no'))
    intro = f"Here’s an overview of **{name}**"
    if project_no:
        intro += f" ({project_no})"
    intro += ':'

    lines = [intro, '']
    summary = []
    location = _format_field_value(project.get('location') or project.get('area_locality'))
    if location:
        summary.append(f"it’s located in **{location}**")

    available = project.get('available_units')
    total = project.get('total_units')
    if total is not None:
        summary.append(f"it has **{available or 0}** available units out of **{total}** total")

    price_sqft = project.get('price_per_sqft')
    if price_sqft:
        summary.append(f"the price per sq.ft is **₹{price_sqft:,.0f}**")

    price_cent = _format_field_value(project.get('price_per_cent'))
    if price_cent:
        summary.append(f"the price per cent is **₹{price_cent}**")

    price_min = project.get('price_range_min')
    price_max = project.get('price_range_max')
    if price_min or price_max:
        min_text = f'₹{float(price_min):,.0f}' if price_min else '?'
        max_text = f'₹{float(price_max):,.0f}' if price_max else '?'
        summary.append(f"the price range is **{min_text} – {max_text}**")

    rera = _format_field_value(project.get('rera_number'))
    if rera:
        summary.append(f"RERA number is **{rera}**")

    if summary:
        sentence = summary[0][0].upper() + summary[0][1:]
        rest = [part if part.endswith('.') else f'{part}.' for part in summary[1:]]
        lines.append(' '.join([sentence] + rest))
        lines.append('')

    extra_fields = (
        ('Status', 'status'),
        ('Description', 'description'),
        ('Property types', 'property_types'),
        ('Highlights', 'highlights'),
        ('Blocked units', 'blocked_units'),
        ('Sold units', 'sold_units'),
        ('Created', 'create_date'),
    )
    details = []
    for label, key in extra_fields:
        value = _format_field_value(project.get(key))
        if value:
            details.append(f"- **{label}:** {value}")
    if details:
        lines.append('**More details:**')
        lines.extend(details)

    units = project.get('units') or []
    if units:
        lines.append('')
        lines.append('**Sample units:**')
        for unit in units[:5]:
            unit_no = unit.get('unit_no') or 'Unit'
            status = unit.get('status_name') or unit.get('status') or 'unknown'
            price = unit.get('total_price') or unit.get('price_per_sqft')
            price_text = f" — ₹{price}" if price else ''
            lines.append(f"- {unit_no} ({status}){price_text}")

    return '\n'.join(lines)


def format_booking_reply(booking_context):
    booking = (booking_context or {}).get('booking') or {}
    if not booking:
        return "I couldn’t find that booking in the CRM."

    customer = _format_field_value(booking.get('customer_name')) or 'the customer'
    receipt = _format_field_value(booking.get('receipt_number'))
    intro = f"Here are the booking details for **{customer}**"
    if receipt:
        intro += f" (Receipt **{receipt}**)"
    intro += ':'

    lines = [intro, '']
    parts = []
    project = _format_field_value(booking.get('project_name'))
    unit = _format_field_value(booking.get('unit_no'))
    if project:
        unit_text = f", unit **{unit}**" if unit else ''
        parts.append(f"they booked **{project}**{unit_text}")

    amount = booking.get('amount_paid')
    if amount:
        parts.append(f"**₹{amount:,.0f}** has been paid")

    booking_date = _format_field_value(booking.get('booking_date'))
    if booking_date:
        parts.append(f"booking date is **{booking_date}**")

    payment_type = _format_field_value(booking.get('payment_type'))
    if payment_type:
        parts.append(f"payment type is **{payment_type}**")

    if parts:
        sentence = parts[0][0].upper() + parts[0][1:]
        lines.append(' '.join([sentence] + [p if p.endswith('.') else f'{p}.' for p in parts[1:]]))

    notes = _format_field_value(booking.get('notes'))
    if notes:
        lines.append('')
        lines.append(f"**Notes:** {notes}")

    return '\n'.join(lines)


def format_overview_reply(crm_context, message=''):
    snapshot = (crm_context or {}).get('snapshot') or {}
    lead_m = snapshot.get('lead_metrics') or {}
    project_m = snapshot.get('project_metrics') or {}
    booking_m = snapshot.get('booking_metrics') or {}
    intents = set((crm_context or {}).get('intents') or [])

    lines = ["Here’s a quick snapshot of your CRM right now:", '']

    if not intents or intents & {'leads', 'metrics', 'general', 'help'}:
        lines.append(
            f"**Leads:** {lead_m.get('active_leads', 0)} active · "
            f"{lead_m.get('followup_today', 0)} follow-up(s) due today · "
            f"{lead_m.get('created_this_week', 0)} created this week"
        )

    if not intents or intents & {'projects', 'metrics', 'general', 'help'}:
        lines.append(
            f"**Projects:** {project_m.get('total_projects', 0)} total · "
            f"{project_m.get('available_units', 0)} units available · "
            f"{project_m.get('site_visits_this_week', 0)} site visit(s) this week"
        )

    if not intents or intents & {'bookings', 'metrics', 'general', 'help'}:
        paid = booking_m.get('total_amount_paid') or 0
        lines.append(
            f"**Bookings:** {booking_m.get('total_bookings', 0)} total · "
            f"₹{paid:,.0f} collected · "
            f"{booking_m.get('bookings_this_month', 0)} this month"
        )

    followups = snapshot.get('followups_today') or []
    if followups:
        lines.append('')
        lines.append('**Follow-ups due today:**')
        for item in followups[:5]:
            desc = item.get('description') or 'Follow-up'
            lines.append(f"- {desc}")

    recent_projects = snapshot.get('recent_projects') or []
    if recent_projects and intents & {'projects', 'general', 'help'}:
        lines.append('')
        lines.append('**Recent projects:**')
        for item in recent_projects[:3]:
            label = item.get('name') or 'Unnamed'
            if item.get('project_no'):
                label += f" ({item['project_no']})"
            lines.append(f"- {label}")

    lines.append('')
    lines.append(
        "Ask me about a specific **lead** (LD/7), **project** (PRJ/4), **booking**, "
        "**phone number**, or say “summary” for an overview."
    )
    return '\n'.join(lines)


def format_help_reply():
    return (
        "I’m your MAP AI Assistant — happy to help with anything in your CRM.\n\n"
        "You can ask me things like:\n"
        "- “Show me details for LD/7” or “Find lead with phone 9244432777”\n"
        "- “Tell me about project PRJ/4” or “What projects do we have?”\n"
        "- “Show booking for receipt 76” or “How many bookings this month?”\n"
        "- “Give me a summary” or “What follow-ups are due today?”\n\n"
        "Just ask naturally — I’ll pull the data from your CRM and explain it clearly."
    )


def format_entity_multiple_matches(entity_label, matches, id_key, name_key, extra_keys=()):
    lines = [
        f"I found **{len(matches)} {entity_label}** that could match. Which one did you mean?",
        '',
    ]
    for match in matches[:5]:
        parts = [match.get(name_key) or f'Unnamed {entity_label[:-1]}']
        for key in extra_keys:
            if match.get(key):
                parts.append(str(match[key]))
        lines.append(f"- {' · '.join(parts)}")
    lines.append('')
    lines.append('Reply with a more specific name or number to see full details.')
    return '\n'.join(lines)


def format_crm_fallback_reply(message, crm_context):
    if crm_context.get('lead'):
        return format_lead_reply(crm_context['lead'], message)
    if crm_context.get('project'):
        return format_project_reply(crm_context['project'])
    if crm_context.get('booking'):
        return format_booking_reply(crm_context['booking'])

    project_leads = crm_context.get('project_leads') or {}
    if project_leads.get('leads'):
        return format_project_leads_reply(LeadSearchResult(
            matches=project_leads['leads'],
            search_term=project_leads.get('project_name'),
            search_type='project',
        ))

    if crm_context.get('lead_matches'):
        return format_entity_multiple_matches(
            'leads', crm_context['lead_matches'], 'id', 'name',
            ('lead_no', 'phone', 'company_name'),
        )
    if crm_context.get('project_matches'):
        return format_entity_multiple_matches(
            'projects', crm_context['project_matches'], 'id', 'name',
            ('project_no', 'location'),
        )
    if crm_context.get('booking_matches'):
        return format_entity_multiple_matches(
            'bookings', crm_context['booking_matches'], 'id', 'customer_name',
            ('receipt_number', 'project_name'),
        )

    intents = set(crm_context.get('intents') or [])
    if intents & {'help'}:
        return format_help_reply()
    if intents & {'metrics', 'general'} or not intents:
        return format_overview_reply(crm_context, message)
    if intents & {'leads', 'projects', 'bookings'}:
        return format_overview_reply(crm_context, message)

    return format_help_reply()


def build_messages(message, history, crm_context=None, user=None):
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    if user:
        user_name = user.get('name') or user.get('email') or 'User'
        messages.append({
            'role': 'system',
            'content': f'Current CRM user: {user_name}',
        })

    if crm_context:
        context_text = json.dumps(crm_context, default=str)
        if len(context_text) > MAX_CONTEXT_CHARS:
            context_text = context_text[:MAX_CONTEXT_CHARS] + '...'
        messages.append({
            'role': 'system',
            'content': f'CRM context (JSON):\n{context_text}',
        })

    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = turn.get('role', 'user')
        content = (turn.get('content') or '').strip()
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content})

    messages.append({'role': 'user', 'content': message})
    return messages


def _generate_huggingface_reply(messages):
    from huggingface_hub import InferenceClient
    from huggingface_hub.errors import HfHubHTTPError

    token = os.environ['HF_TOKEN'].strip()
    model = os.environ.get('HF_MODEL', DEFAULT_HF_MODEL)
    client = InferenceClient(token=token)

    try:
        response = client.chat_completion(
            messages=messages,
            model=model,
            max_tokens=700,
            temperature=0.5,
        )
    except HfHubHTTPError as exc:
        raise AiChatError(f'Hugging Face API error: {exc}') from exc

    reply = (response.choices[0].message.content or '').strip()
    if not reply:
        raise AiChatError('Empty reply from Hugging Face')
    return reply


def _generate_openai_reply(messages):
    from openai import OpenAI

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    model = os.environ.get('AI_MODEL', DEFAULT_OPENAI_MODEL)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.5,
        max_tokens=700,
    )

    reply = (response.choices[0].message.content or '').strip()
    if not reply:
        raise AiChatError('Empty reply from OpenAI')
    return reply


def generate_ai_reply(message, history, crm_context=None, user=None):
    if not _ai_configured():
        if crm_context:
            return format_crm_fallback_reply(message, crm_context)
        provider = _ai_provider()
        if provider == 'openai':
            raise AiChatError('OPENAI_API_KEY is not configured')
        raise AiChatError('HF_TOKEN is not configured')

    messages = build_messages(message, history, crm_context, user)
    provider = _ai_provider()

    try:
        if provider == 'openai':
            return _generate_openai_reply(messages)
        return _generate_huggingface_reply(messages)
    except AiChatError:
        if crm_context:
            return format_crm_fallback_reply(message, crm_context)
        raise


def process_chat_request(org_id, message, history, current_user, page_context=None, user=None):
    org_id = int(org_id)
    page_context = page_context or {}

    explicit_lead_id = None
    explicit_project_id = None
    explicit_booking_id = None

    if page_context.get('type') == 'lead':
        explicit_lead_id = (page_context.get('lead') or {}).get('leadId')
    elif page_context.get('type') == 'project':
        explicit_project_id = (page_context.get('project') or {}).get('projectId')
    elif page_context.get('type') == 'booking':
        explicit_booking_id = (page_context.get('booking') or {}).get('bookingId')

    lead_result = resolve_lead_search(org_id, message, current_user, explicit_lead_id)
    project_result = resolve_project_search(org_id, message, current_user, explicit_project_id)
    booking_result = resolve_booking_search(org_id, message, current_user, explicit_booking_id)

    if lead_result.search_type == 'project' and not lead_result.lead_id:
        return format_project_leads_reply(lead_result)

    if len(lead_result.matches) > 1 and not lead_result.lead_id:
        return format_entity_multiple_matches(
            'leads', lead_result.matches, 'id', 'name', ('lead_no', 'phone', 'company_name'),
        )
    if len(project_result.matches) > 1 and not project_result.entity_id:
        return format_entity_multiple_matches(
            'projects', project_result.matches, 'id', 'name', ('project_no', 'location'),
        )
    if len(booking_result.matches) > 1 and not booking_result.entity_id:
        return format_entity_multiple_matches(
            'bookings', booking_result.matches, 'id', 'customer_name',
            ('receipt_number', 'project_name'),
        )

    if not lead_result.lead_id and lead_result.search_type:
        return format_not_found_reply(lead_result)

    if not project_result.entity_id and project_result.search_type:
        if project_result.search_type == 'price':
            return (
                f"I couldn't find a project with price per sq.ft of **{project_result.search_term}**. "
                "Try a project number like PRJ/4, the project name, or a different price."
            )
        return (
            f"I couldn't find a project matching **{project_result.search_term}**. "
            "Try a project number like PRJ/4 or the project name."
        )

    if not booking_result.entity_id and booking_result.search_type:
        return (
            f"I couldn't find a booking matching **{booking_result.search_term}**. "
            "Try a receipt number, customer name, or project name."
        )

    crm_context = build_crm_context(
        org_id, message, current_user, page_context,
        lead_result, project_result, booking_result,
    )

    try:
        return generate_ai_reply(message, history, crm_context, user)
    except AiChatError as exc:
        if crm_context:
            return format_crm_fallback_reply(message, crm_context)
        raise exc
    except Exception:
        if crm_context:
            return format_crm_fallback_reply(message, crm_context)
        raise
