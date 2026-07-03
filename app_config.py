import url_config

BASE_URL = url_config.BASE_URL
CLIENT_APP_URL = url_config.CLIENT_APP_URL
TEMPLATE_FOLDER = 'templates/'
DEFAULT_FROM_EMAIL = 'noreply@map.local'

user_lookup = {
    'from': 'user',
    'localField': 'assigned_to',
    'foreignField': '_id',
    'as': 'assigned',
}
lead_status_lookup = {
    'from': 'fields',
    'localField': 'lead_status',
    'foreignField': '_id',
    'as': 'lead_status_name',
}
lead_customer_type_lookup = {
    'from': 'fields',
    'localField': 'customer_type',
    'foreignField': '_id',
    'as': 'customer_type_name',
}
lead_customer_requirement_lookup = {
    'from': 'fields',
    'localField': 'customer_requirement',
    'foreignField': '_id',
    'as': 'customer_requirement_name',
}
lead_source_type_lookup = {
    'from': 'fields',
    'localField': 'source',
    'foreignField': '_id',
    'as': 'source_name',
}
lead_payment_terms_lookup = {
    'from': 'fields',
    'localField': 'payment_terms',
    'foreignField': '_id',
    'as': 'payment_terms_name',
}
company_lookup = {
    'from': 'company',
    'localField': 'company_id',
    'foreignField': '_id',
    'as': 'company_detail',
}
contact_lookup = {
    'from': 'contact',
    'localField': 'contact_id',
    'foreignField': '_id',
    'as': 'contact_detail',
}
customfields_value_lookup = {
    'from': 'customfields_value',
    'localField': '_id',
    'foreignField': 'associate_id',
    'as': 'custom_fields_value',
}
curr_name_Lookup = {
    'from': 'currencies',
    'localField': 'currency_id',
    'foreignField': '_id',
    'as': 'currency_name',
}
assigned_by_lookup = {
    'from': 'user',
    'localField': 'assigned_by',
    'foreignField': '_id',
    'as': 'assigned_by_name',
}
watchers_lookup = {
    'from': 'user',
    'localField': 'watchers',
    'foreignField': '_id',
    'as': 'watchers_list',
}
shared_list_lookup = {
    'from': 'list',
    'localField': 'shared_lists',
    'foreignField': '_id',
    'as': 'shared_lists_data',
}
task_status_lookup = {
    'from': 'fields',
    'localField': 'task_status',
    'foreignField': '_id',
    'as': 'status_name',
}
task_priority_lookup = {
    'from': 'fields',
    'localField': 'priority',
    'foreignField': '_id',
    'as': 'priority_to',
}
team_name_lookup = {
    'from': 'team',
    'localField': 'teams',
    'foreignField': '_id',
    'as': 'team_name',
}
settingsLookup = {
    'from': 'settings',
    'localField': 'org_id',
    'foreignField': 'org_id',
    'as': 'org_settings',
}

order_dict = {'asc': 1, 'desc': -1}

UPLOAD_OPEN_EMAIL_FOLDER = 'uploads/email/'
UPLOAD_OPEN_DOCUMENT_FOLDER = 'uploads/document/'
UPLOAD_PDF_IMAGE_FOLDER = 'uploads/pdf_image/'

ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx',
    'xls', 'xlsx', 'txt', 'csv', 'zip', 'ppt', 'pptx',
}

documentfile_lookup = {
    'from': 'document',
    'localField': '_id',
    'foreignField': 'folder',
    'as': 'files',
}

ownerLookup = {
    'from': 'user',
    'localField': 'create_by',
    'foreignField': '_id',
    'as': 'createBy',
}
note_lookup = {
    'from': 'user',
    'localField': 'create_by',
    'foreignField': '_id',
    'as': 'createBy',
}
industry_lookup = {
    'from': 'fields',
    'localField': 'industry',
    'foreignField': '_id',
    'as': 'industry_name',
}
application_lookup = {
    'from': 'fields',
    'localField': 'application',
    'foreignField': '_id',
    'as': 'application_name',
}
timelineLookup_new = {
    'from': 'user',
    'localField': 'user_id',
    'foreignField': '_id',
    'as': 'createBy',
}

note_Project = {
    'createBy.name': 1,
    '_id': 1,
    'org_id': 1,
    'note': 1,
    'associate_id': 1,
    'associate_to': 1,
    'location': 1,
    'create_date': 1,
    'create_by': 1,
}
document_Project = {
    'createBy.name': 1,
    '_id': 1,
    'org_id': 1,
    'document': 1,
    'associate_id': 1,
    'associate_to': 1,
    'create_date': 1,
    'create_by': 1,
    'user_file_name': 1,
}
email_Project = {
    'createBy.name': 1,
    '_id': 1,
    'email_id': 1,
    'org_id': 1,
    'fromEmail': 1,
    'to': 1,
    'cc': 1,
    'bcc': 1,
    'subject': 1,
    'content': 1,
    'attachment': 1,
    'associate_id': 1,
    'associate_to': 1,
    'status': 1,
    'create_date': 1,
    'create_by': 1,
    'thread_id': 1,
}
activity_Project_new = {
    'createBy.name': 1,
    '_id': 1,
    'action': 1,
    'org_id': 1,
    'from_data': 1,
    'to_data': 1,
    'category_name': 1,
    'associate_to': 1,
    'associate_id': 1,
    'via': 1,
    'extra_info': 1,
    'text_info': 1,
    'title': 1,
    'create_date': 1,
}
lead_project = {
    'org_id': 1,
    'name': 1,
    'email': 1,
    'phone': 1,
    'alternate_phone': 1,
    'whatsapp_no': 1,
    'lead_type': 1,
    'lead_status': 1,
    'company_name': 1,
    'designation': 1,
    'assigned_to': 1,
    'create_date': 1,
    'source': 1,
    'customer_type': 1,
    'customer_requirement': 1,
    'current_staying': 1,
    'location': 1,
    'modify_date': 1,
    'create_by': 1,
    'description': 1,
    'assigned': 1,
    'url': 1,
    'address1': 1,
    'address2': 1,
    'city': 1,
    'country': 1,
    'state': 1,
    'stage': 1,
    'pincode': 1,
    'gstin': 1,
    'industry': 1,
    'application': 1,
    'status': 1,
    'target_date': 1,
    'converted_date': 1,
    'not_qualified_date': 1,
    'budget': 1,
    'timeline': 1,
    'payment_terms': 1,
    'dob': 1,
    'date_of_birth': 1,
    'sod': 1,
    'source_of_deal': 1,
    'referred_by': 1,
    'referred_by_contact': 1,
    'referred_mobile_no': 1,
    'purpose': 1,
    'lead_status_name': 1,
    'source_name': 1,
    'customer_type_name': 1,
    'customer_requirement_name': 1,
    'payment_terms_name': 1,
    'teams': 1,
    'suggested_projects': 1,
    'createBy': 1,
    'lead_no': 1,
    'project_name': 1,
    'industry_name': 1,
    'application_name': 1,
}
