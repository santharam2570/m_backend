import datetime

from mongoengine import Document, fields as db
from pytz import timezone


def utc_now():
    return datetime.datetime.now(timezone('UTC'))


class Branch(db.Document):
    meta = {
        'strict': False,
        'indexes': [
            {'fields': ['org_id', 'code'], 'unique': True},
            {'fields': ['org_id', 'branch_id'], 'unique': True},
        ],
    }

    branch_id = db.IntField(required=True)
    org_id = db.IntField(required=True)
    name = db.StringField(required=True)
    code = db.StringField(required=True)
    status = db.StringField(default='active')
    manager_user_id = db.StringField()
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField()


class User(db.Document):
    meta = {'strict': False}

    email = db.StringField(required=True, unique=True)
    name = db.StringField(default='')
    phone = db.StringField(default='')
    org_id = db.IntField(required=True)
    status = db.StringField(default='active')
    password = db.StringField(default='')
    role = db.ObjectIdField()
    role_tier = db.StringField(default='branch_user')
    branch_id = db.IntField()
    create_date = db.DateTimeField(default=utc_now)
    plan_start_date = db.DateTimeField()
    plan_end_date = db.DateTimeField()
    report_days = db.ListField(default=lambda: [
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
    ])
    verify_otp = db.StringField(default='')


class Organization(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True, unique=True)
    organization_name = db.StringField(default='')
    email = db.StringField(required=True, default='')
    create_date = db.DateTimeField(default=utc_now)
    signup_via = db.StringField(default='email')
    status = db.StringField(default='active')
    two_step = db.StringField(default='')
    plan_id = db.ObjectIdField()
    trial = db.StringField()
    plan_start_date = db.DateTimeField()
    plan_end_date = db.DateTimeField()
    partner_id = db.StringField()
    coupon = db.StringField(default='')


class Role(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    role_name = db.StringField(required=True, default='Administrator')
    create_by = db.ObjectIdField()
    create_date = db.DateTimeField(default=utc_now)
    # Module access (0/1)
    lead = db.IntField(default=1)
    settings = db.IntField(default=0)
    company = db.IntField(default=0)
    quote = db.IntField(default=0)
    # Settings permissions
    manage_settings = db.IntField(default=0)
    manage_users = db.IntField(default=0)
    manage_roles = db.IntField(default=0)
    # Lead permissions
    add_lead = db.IntField(default=0)
    edit_lead = db.IntField(default=0)
    delete_lead = db.IntField(default=0)
    export_lead = db.IntField(default=0)
    import_lead = db.IntField(default=0)
    lead_view_all = db.IntField(default=1)
    lead_view_own = db.IntField(default=0)
    lead_view_team = db.IntField(default=0)
    # Booking module
    booking = db.IntField(default=0)
    add_booking = db.IntField(default=0)
    edit_booking = db.IntField(default=0)
    delete_booking = db.IntField(default=0)
    booking_view_all = db.IntField(default=1)
    booking_view_own = db.IntField(default=0)
    booking_view_team = db.IntField(default=0)
    # Notes permissions
    add_note = db.IntField(default=0)
    edit_note = db.IntField(default=0)
    delete_note = db.IntField(default=0)
    # Lead settings
    manage_lead_settings = db.IntField(default=0)
    # Organization-level RBAC permissions
    manage_branches = db.IntField(default=0)
    manage_admins = db.IntField(default=0)
    manage_branch_managers = db.IntField(default=0)
    manage_branch_users = db.IntField(default=0)
    is_system_role = db.IntField(default=0)


class Email(db.Document):
    email_id = db.StringField(required=True)
    org_id = db.IntField(required=True)
    fromEmail = db.StringField(required=True)
    email_type = db.StringField(required=True,default='single')
    thread_id = db.StringField()
    sent_email_id = db.StringField()
    to = db.ListField(required=True)
    cc = db.ListField(required=False)
    bcc = db.ListField(required=False)
    subject = db.StringField(required=True,default='')
    content = db.StringField(required=True,default='')
    attachment = db.ListField(required=False)
    associate_id =  db.ObjectIdField(required=False)
    associate_to =  db.StringField(required=True)
    process_type =  db.StringField(required=False)
    process_id =  db.ObjectIdField(required=False)
    create_date = db.DateTimeField(default=utc_now)
    create_by =  db.ObjectIdField(required=True)
    status =  db.StringField(required=True,default='0')



class RevokedToken(db.Document):
    jti = db.StringField(required=True, unique=True)
    user_id = db.StringField()
    revoked_at = db.DateTimeField(default=utc_now)


class Lead(db.Document):
    meta = {'strict': False}
    org_id = db.IntField(required=True)
    branch_id = db.IntField()
    email = db.StringField(required=False)
    phone = db.StringField(required=False)
    project_name = db.StringField(required=False)
    location = db.StringField(required=False)
    current_staying = db.StringField(required=False)
    company_name = db.StringField(required=False)
    designation = db.StringField(required=False)
    lead_no = db.StringField(required=False)
    lead_status = db.ObjectIdField(required=False)
    name = db.StringField(required=True, default='')
    assigned_to = db.ObjectIdField()
    source = db.ObjectIdField(required=False)
    customer_type = db.ObjectIdField(required=False)
    customer_requirement = db.ListField(db.ObjectIdField())
    description = db.StringField(required=False)
    url = db.StringField(required=False, default='')
    address1 = db.StringField(required=False, default='')
    address2 = db.StringField(required=False, default='')
    city = db.StringField(required=False, default='')
    country = db.StringField(required=False, default='')
    state = db.StringField(required=False, default='')
    stage = db.StringField(required=False, default='')
    pincode = db.StringField(required=False, default='')
    alternate_phone = db.StringField(required=False, default='')
    whatsapp_no = db.StringField(required=False, default='')
    gstin = db.StringField(required=False, default='')
    lead_type = db.StringField(required=False, default='')
    industry = db.ObjectIdField(required=False)
    application = db.ObjectIdField(required=False)
    teams = db.ListField(db.ObjectIdField())
    status = db.StringField(required=True, default='active')
    target_date = db.DateTimeField(required=False)
    converted_date = db.DateTimeField(required=False)
    not_qualified_date = db.DateTimeField(required=False)
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField(required=False)
    create_by = db.ObjectIdField(required=False)
    budget = db.StringField(required=False, default='')
    timeline = db.StringField(required=False, default='')
    payment_terms = db.ObjectIdField(required=False)
    dob = db.DateTimeField(required=False)
    sod = db.StringField(required=False, default='')
    source_of_deal = db.StringField(required=False, default='')
    referred_by = db.StringField(required=False, default='')
    referred_by_contact = db.StringField(required=False, default='')
    purpose = db.StringField(required=False, default='')
    referred_mobile_no = db.StringField(required=False, default='')


class Project(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    branch_id = db.IntField()
    project_no = db.StringField(required=False)
    name = db.StringField(required=True, default='')
    location = db.StringField(required=False, default='')
    area_locality = db.StringField(required=False, default='')
    price_per_sqft = db.FloatField(required=False, default=0)
    price_range_min = db.FloatField(required=False, default=0)
    price_range_max = db.FloatField(required=False, default=0)
    total_units = db.IntField(required=False, default=0)
    available_units = db.IntField(required=False, default=0)
    blocked_units = db.IntField(required=False, default=0)
    sold_units = db.IntField(required=False, default=0)
    owner_site_units = db.IntField(required=False, default=0)
    rera_status = db.StringField(required=False, default='pending')
    rera_number = db.StringField(required=False, default='')
    dtcp_status = db.StringField(required=False, default='')
    highlights = db.ListField(db.StringField(), default=list)
    property_types = db.ListField(db.StringField(), default=list)
    budget_min = db.FloatField(required=False, default=0)
    budget_max = db.FloatField(required=False, default=0)
    status = db.StringField(required=True, default='active')
    description = db.StringField(required=False, default='')
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField(required=False)
    create_by = db.ObjectIdField(required=False)
    dtcp_number = db.StringField(required=False, default='')
    price_per_cent  = db.StringField(required=False, default='')


class ProjectUnit(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    project_id = db.ObjectIdField(required=True)
    unit_no = db.StringField(required=True, default='')
    block = db.StringField(required=False, default='')
    property_type = db.StringField(required=False, default='')
    area_sqft = db.FloatField(required=False)
    area_cents = db.FloatField(required=False)
    facing = db.StringField(required=False, default='')
    floor = db.StringField(required=False, default='')
    status = db.ObjectIdField(required=False)
    price_per_sqft = db.FloatField(required=False, default=0)
    total_price = db.FloatField(required=False, default=0)
    hold_until = db.DateTimeField(required=False)
    linked_lead_id = db.ObjectIdField(required=False)
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField(required=False)
    create_by = db.ObjectIdField(required=False)


class Booking(db.Document):
    meta = {
        'strict': False,
        'indexes': [
            {'fields': ['org_id', 'receipt_number'], 'unique': True},
            {'fields': ['org_id', 'project_id', 'unit_id']},
            {'fields': ['org_id', 'booking_date']},
            {'fields': ['org_id', 'lead_id']},
            {'fields': ['org_id', 'status']},
        ],
    }

    org_id = db.IntField(required=True)
    branch_id = db.IntField()
    project_id = db.ObjectIdField(required=True)
    project_name = db.StringField(default='')
    unit_id = db.ObjectIdField(required=True)
    unit_no = db.StringField(default='')
    lead_id = db.ObjectIdField()
    customer_name = db.StringField(default='')
    associated_id = db.ObjectIdField(required=False)
    receipt_number = db.StringField(required=True)
    booking_date = db.DateTimeField(required=True)
    registration_date = db.DateTimeField()
    amount_paid = db.FloatField(required=True, default=0)
    amount_in_words = db.StringField(default='')
    payment_type = db.StringField(required=True)
    transaction_type = db.StringField(required=True)

    status = db.StringField(default='active')
    notes = db.StringField(default='')

    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField()
    create_by = db.ObjectIdField(required=True)


class ProjectSiteVisit(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    project_id = db.ObjectIdField(required=True)
    lead_id = db.ObjectIdField(required=False)
    lead_name = db.StringField(required=True, default='')
    visit_date = db.DateTimeField(required=False)
    visit_time = db.StringField(required=False, default='')
    agent_name = db.StringField(required=False, default='')
    attaching_person = db.StringField(required=False, default='')
    family_attended = db.BooleanField(required=False, default=False)
    feedback = db.StringField(required=False, default='')
    follow_up_scheduled = db.BooleanField(required=False, default=False)
    next_follow_up_date = db.DateTimeField(required=False)
    status = db.StringField(required=True, default='scheduled')
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField(required=False)
    create_by = db.ObjectIdField(required=False)


class ProjectDocument(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    project_id = db.ObjectIdField(required=True)
    name = db.StringField(required=True, default='')
    category = db.StringField(required=True, default='other')
    file_url = db.StringField(required=False, default='')
    create_date = db.DateTimeField(default=utc_now)
    create_by = db.ObjectIdField(required=False)


class Admin_email(db.Document):
    email_id = db.StringField(required=True)
    partner_id = db.ObjectIdField(required=True)
    fromEmail = db.StringField(required=True)
    email_type = db.StringField(required=True,default='single')
    thread_id = db.StringField()
    sent_email_id = db.StringField()
    to = db.ListField(required=True)
    cc = db.ListField(required=False)
    bcc = db.ListField(required=False)
    subject = db.StringField(required=True,default='')
    content = db.StringField(required=True,default='')
    attachment = db.ListField(required=False)
    associate_id =  db.ObjectIdField(required=False)
    associate_to =  db.StringField(required=True)
    process_type =  db.StringField(required=False)
    process_id =  db.ObjectIdField(required=False)
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    create_by =  db.ObjectIdField(required=True)
    status =  db.StringField(required=True,default='0')




class Crm_tasks(db.Document):
    org_id = db.IntField(required=True)
    associate_id =  db.ObjectIdField(required=True)
    associate_to = db.StringField(required=True)
    description = db.StringField(required=True,default='') 
    new_task_type =  db.StringField()
    time =  db.StringField(required=True)
    date =  db.DateTimeField(required=True)
    assigned_to =  db.ObjectIdField(required=True)
    status =  db.StringField(required=True,default='Open')
    visit_purpose =  db.ObjectIdField()
    note_id =  db.ObjectIdField()
    remainder_status =  db.StringField(required=True,default='0')
    create_by =  db.ObjectIdField(required=True)
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    modify_date = db.DateTimeField()
    company_id =  db.ObjectIdField(required=False)
    ticket_id = db.ObjectIdField(required=False)
    demo_data = db.IntField(required=False,default=0)

    completed_on = db.DateTimeField()
    priority =  db.StringField()
    in_time =  db.StringField()
    out_time =  db.StringField()
    task_type =  db.ObjectIdField()

class Document(db.Document):
    # cid = db.ObjectIdField(primary_key=True)
    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    document_id = db.StringField(required=True)
    associate_to = db.StringField(required=True)
    associate_id = db.ObjectIdField(required=True)
    document = db.StringField(required=True)
    user_file_name = db.StringField(required=False)
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    create_by =  db.ObjectIdField(required=True)

    folder = db.ObjectIdField()
    modify_date = db.DateTimeField()
    modify_by =  db.ObjectIdField()  

    demo_data = db.IntField(required=False,default=0)

class Fields(db.Document):
    name = db.StringField(required=True)
    org_id = db.IntField(required=True)
    type = db.StringField(required=True)
    info = db.StringField(default='')
    color = db.StringField(default='')
    sort_order = db.IntField(required=True)  
    default = db.IntField(required=True,default='0')
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    modify_date = db.DateTimeField()
    settings = db.ListField(required=False)
    title = db.StringField(default='')
    # create_by =  db.ObjectIdField(required=False)
    weightage = db.IntField(required=False,default=0)
    won = db.IntField(default='0')
    lost = db.IntField(default='0')
    percentage = db.IntField(required=False,default=0)
    demo_data = db.IntField(required=False,default=0)

    php_id = db.IntField(required=False)    
    reject = db.IntField(default='0')
    approve = db.IntField(default='0')
    active = db.IntField(default='0')
    inactive = db.IntField(default='0')
    not_qualified = db.IntField(default='0')
    closed = db.IntField(default='0')

class Numbering(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    module = db.StringField(required=True)
    prefix = db.StringField(default='LD')
    sequence = db.IntField(default=1)


class UserActivity(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    category_name = db.StringField()
    action = db.StringField()
    associate_to = db.StringField()
    associate_id = db.ObjectIdField()
    via = db.IntField(default=0)
    extra_info = db.DictField()
    text_info = db.StringField()
    title = db.StringField()
    from_data = db.DictField()
    to_data = db.DictField()
    create_date = db.DateTimeField(default=utc_now)




class Note(db.Document):
    note_id = db.StringField(required=True)
    org_id = db.IntField(required=True)
    note = db.StringField(required=True)
    associate_id =  db.ObjectIdField(required=True)
    associate_to =  db.StringField(required=True)
    create_date = db.DateTimeField(default=utc_now)
    create_by =  db.ObjectIdField(required=True)
    location = db.DictField(required=False, default={
        'latitude': None,
        'longitude': None,
        'accuracy': None
    })

    demo_data = db.IntField(required=False,default=0)


class Task(db.Document):
    task_name = db.StringField(required=True)
    list_id =  db.ObjectIdField(required=True)
    shared_lists = db.ListField(db.ObjectIdField(), default=[])  
    
    org_id = db.IntField(required=True)
    description =  db.StringField(required=False,default='')
    task_status =  db.ObjectIdField()
    delete_date = db.DateTimeField()
    status =  db.StringField(required=True,default='active')
    Action = db.ObjectIdField(required=False)
    priority = db.ObjectIdField(required=False)
    due_date = db.DateTimeField()
    modify_date = db.DateTimeField(required=False)
    deletede_by =  db.ObjectIdField()
    assigned_to = db.ListField(db.ObjectIdField())
    watchers = db.ListField(db.ObjectIdField())
    create_by =  db.ObjectIdField(required=True)
    create_date = db.DateTimeField(default=utc_now)

    assigned_by  =  db.ObjectIdField()
    teams = db.ListField(db.ObjectIdField())
    start_date = db.DateTimeField()
    closed_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    demo_data = db.IntField(required=False,default=0)
    task_remainder_mail=  db.StringField(required=True,default='0')




class notifications (db.Document):
    header_name = db.StringField(required=False,default='')
    associate_to = db.StringField(required=True)
    commands = db.StringField(required=False,default='')
    task_id =  db.ObjectIdField(required=False)
    company_id =  db.ObjectIdField(required=False)
    read_status = db.IntField(required=True,default=0)
    clear_status = db.IntField(required=True,default=0)
    org_id = db.IntField(required=True)
    assigned_to = db.ObjectIdField()
    create_by =  db.ObjectIdField(required=True)
    create_date = db.DateTimeField(default=utc_now)
    status =  db.StringField(required=True,default='Open')


class AdminUser(db.Document):
    meta = {'strict': False}

    email = db.StringField(required=True, unique=True)
    password = db.StringField(default='')
    name = db.StringField(default='')
    phone = db.StringField(default='')
    status = db.StringField(default='active')
    approved = db.StringField(default='0')
    admin_user_id = db.StringField()
    role = db.ObjectIdField()
    create_date = db.DateTimeField(default=utc_now)


class User_audit(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    user_name = db.StringField()
    org_name = db.StringField()
    create_date = db.DateTimeField(default=utc_now)
    start_time = db.DateTimeField()
    end_time = db.DateTimeField()
    app_type = db.StringField()




class Contact(db.Document):
    org_id = db.IntField(required=True)
    contact_name = db.StringField(required=True,default='')
    company_id =  db.ObjectIdField(required=True,default='')
    phone = db.StringField(required=False,default='')
    email = db.StringField(required=False,default='')

    alt_phone = db.StringField(required=False,default='')
    alt_email = db.StringField(required=False,default='')

    department =  db.StringField(required=False,default='')
    designation =  db.StringField(required=False,default='')
    status =  db.StringField(required=True,default='active')
    dob = db.DateTimeField(required=False)
    
    create_by =  db.ObjectIdField(required=True)
    assigned_to = db.ObjectIdField()
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField(required=False)

    demo_data = db.IntField(required=False,default=0)


class Document(db.Document):
    # cid = db.ObjectIdField(primary_key=True)
    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    document_id = db.StringField(required=True)
    associate_to = db.StringField(required=True)
    associate_id = db.ObjectIdField(required=True)
    document = db.StringField(required=True)
    user_file_name = db.StringField(required=False)
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    create_by =  db.ObjectIdField(required=True)

    folder = db.ObjectIdField()
    modify_date = db.DateTimeField()
    modify_by =  db.ObjectIdField()  

    demo_data = db.IntField(required=False,default=0)


class Team(db.Document):
    meta = {'collection': 'team', 'strict': False}

    org_id = db.IntField(required=True)


class Partner(db.Document):
    meta = {'strict': False}

    partner_record_id = db.IntField()
    partner_no = db.IntField()
    name = db.StringField(default='')
    email = db.StringField(default='')
    status = db.StringField(default='active')
    create_date = db.DateTimeField(default=utc_now)


class Partner_user(db.Document):
    meta = {'strict': False}

    email = db.StringField(required=True)
    password = db.StringField(default='')
    name = db.StringField(default='')
    phone = db.StringField(default='')
    partner_id = db.ObjectIdField()
    role = db.ObjectIdField()
    permissions = db.ListField(default=list)
    profile_image = db.StringField()
    currency = db.ObjectIdField()
    time_zone = db.ObjectIdField()
    status = db.StringField(default='active')
    modify_date = db.DateTimeField()
    create_date = db.DateTimeField(default=utc_now)


class Timezones(db.Document):
    meta = {'strict': False}

    text = db.StringField()


class Countries(db.Document):
    meta = {'strict': False}

    name = db.StringField()
    code = db.StringField()


class States(db.Document):
    meta = {'strict': False}

    name = db.StringField(required=True)
    country = db.StringField(required=True)


class Currencies(db.Document):
    meta = {'strict': False}

    name = db.StringField()
    code = db.StringField()


class Reporting_To(db.Document):
    meta = {'strict': False}

    user_id = db.ObjectIdField()
    report_to = db.ObjectIdField()
    org_id = db.IntField()


class Plan_wise_modules(db.Document):
    meta = {'strict': False}

    plan_id = db.ObjectIdField()
    module_name = db.StringField()
    status = db.StringField(default='active')


class Admin_fields(db.Document):
    meta = {'strict': False}

    partner_id = db.ObjectIdField()
    type = db.StringField()
    name = db.StringField()
    sort_order = db.IntField(default=0)
    default = db.IntField(default=0)
    info = db.StringField(default='')
    color = db.StringField(default='')
    modify_date = db.DateTimeField()
    create_date = db.DateTimeField(default=utc_now)


class Admin_contacts(db.Document):
    meta = {'strict': False}

    org_id = db.IntField()
    partner_id = db.ObjectIdField()
    create_date = db.DateTimeField(default=utc_now)


class Admin_lead(db.Document):
    meta = {'strict': False}

    partner_id = db.ObjectIdField()
    org_id = db.IntField()
    create_date = db.DateTimeField(default=utc_now)


class Admin_notes(db.Document):
    meta = {'strict': False}

    partner_id = db.ObjectIdField()
    org_id = db.IntField()
    create_date = db.DateTimeField(default=utc_now)


class Admin_document(db.Document):
    meta = {'strict': False}

    partner_id = db.ObjectIdField()
    org_id = db.IntField()
    create_date = db.DateTimeField(default=utc_now)


class Admin_activity(db.Document):
    meta = {'strict': False}

    partner_id = db.ObjectIdField()
    org_id = db.IntField()
    create_date = db.DateTimeField(default=utc_now)


class Admin_quote(db.Document):
    meta = {'strict': False}

    partner_id = db.ObjectIdField()
    org_id = db.IntField()
    create_date = db.DateTimeField(default=utc_now)


class PdfSettings(db.Document):
    meta = {'strict': False}

    org_id = db.IntField()


class Column_customize(db.Document):
    meta = {'strict': False}

    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    lead_column = db.ListField(default=[])
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField(required=False)


class history_folders(db.Document):
    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    associate_to = db.StringField(required=True)
    associate_id = db.ObjectIdField(required=True)
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))


class Folder(db.Document):
    # cid = db.ObjectIdField(primary_key=True)
    org_id = db.IntField(required=True)
    associate_to = db.StringField(required=True) 
    folder_name = db.StringField(required=True) 
    associate_id = db.ObjectIdField(required=True)
    path = db.StringField(required=True)
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))
    create_by =  db.ObjectIdField(required=True)
    modify_date = db.DateTimeField()
    modify_by =  db.ObjectIdField()  

    demo_data = db.IntField(required=False,default=0)

class Gmail_tokens(db.Document):
    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    email = db.StringField(required=True)
    access_token = db.StringField(required=True)
    refresh_token = db.StringField()
    default = db.IntField(default='0')

    picture = db.StringField()
    gmailaccount_id = db.StringField()
    gmaildata = db.StringField()
    create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))


class Email_template(db.Document):
    meta = {'strict': False, 'collection': 'email_template'}

    org_id = db.IntField(required=True)
    name = db.StringField(required=True)
    template = db.StringField(required=True)
    subject = db.StringField(required=True)
    default = db.IntField(default=0)
    sort_order = db.IntField(default=0)
    create_date = db.DateTimeField(default=utc_now)
    modify_date = db.DateTimeField()


class Email_template_history(db.Document):
    meta = {'strict': False, 'collection': 'email_template_history'}

    org_id = db.IntField(required=True)
    user_id = db.ObjectIdField(required=True)
    template_id = db.ObjectIdField()
    name = db.StringField(required=True)
    template = db.StringField(required=True)
    subject = db.StringField(required=True)
    associate_to = db.StringField(default='email_template')
    create_date = db.DateTimeField(default=utc_now)
    
# class Organization(db.Document):
#     orgid = db.ObjectIdField(default=bson.ObjectId, primary_key=True)
#     org_id = db.IntField(required=True)
#     organization_name = db.StringField(default='')
#     phone = db.StringField(required=False,default='')
#     address = db.StringField(required=False,default='')
#     address2 = db.StringField(required=False,default='')
#     city = db.StringField(required=False,default='')
#     state = db.StringField(required=False,default='')
#     pcode = db.StringField(required=False,default='')
#     country = db.StringField(required=False,default='')
#     phone = db.StringField(required=False,default='')
#     website = db.StringField(required=False,default='')
#     email = db.StringField(required=True,default='')
#     gstin = db.StringField(required=False,default='')
#     pan_no = db.StringField(required=False,default='')

#     time_zone = db.StringField(required=False,default='')
#     start_time = db.StringField(required=False,default='')
#     date_format = db.StringField(required=False,default='')
#     end_time = db.StringField(required=False,default='')
#     create_date = db.DateTimeField(default=datetime.datetime.now(timezone("UTC")).strftime('%Y-%m-%d %H:%M:%S.171Z'))

#     email_activation = db.StringField(required=False,default='pending')
#     demo_data_set = db.IntField(required=False)
#     upload_count =db.IntField(required=True,default=100)
#     password = db.StringField()
#     trial =  db.StringField()
#     signup_via = db.StringField()
#     plan_start_date = db.DateTimeField(required=False)
#     plan_end_date = db.DateTimeField(required=False)
   
   
