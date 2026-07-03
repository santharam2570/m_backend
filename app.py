import base64
import datetime
import json
import os
import random
import time
from collections import defaultdict
from urllib.parse import unquote
from adminapi import AdminAPI

from bson import ObjectId, json_util
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
from flask_mail import Mail
from pytz import timezone
from werkzeug.utils import secure_filename

import app_config
from ai_chat import AiChatError, process_chat_request
from common_config import Uid
from db import initialize_db
from jwt_auth import (
    create_user_tokens,
    get_jwt_identity,
    init_jwt,
    jwt_required,
    revoke_current_token,
    revoke_token_string,
)
from rbac import (
    branch_allowed_for_user,
    can_manage_users,
    effective_tier,
    resolve_record_branch_id,
)
from mail_service import (
    _resolve_local_attachment_paths,
    send_auth_email,
    send_crm_email,
    send_signup_email,
)
from mongodb import MongoAPI

load_dotenv()

app = Flask(__name__, template_folder=app_config.TEMPLATE_FOLDER)
app.config.from_pyfile('config.cfg')

app.config['JWT_SECRET_KEY'] = os.environ.get(
    'JWT_SECRET_KEY',
    'map-auth-secret-change-in-production',
)
app.config['CORS_HEADERS'] = 'Content-Type'

_mail_server = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
_gmail_defaults = _mail_server == 'smtp.gmail.com'
app.config['MAIL_SERVER'] = _mail_server
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587' if _gmail_defaults else '465'))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '').strip()
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '').replace(' ', '')
app.config['MAIL_USE_TLS'] = os.environ.get(
    'MAIL_USE_TLS',
    'true' if _gmail_defaults else 'false',
).lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get(
    'MAIL_USE_SSL',
    'false' if _gmail_defaults else 'true',
).lower() == 'true'
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get(
    'MAIL_DEFAULT_SENDER',
    os.environ.get('MAIL_USERNAME') or app_config.DEFAULT_FROM_EMAIL,
)
app.config['MAIL_ENABLED'] = os.environ.get('MAIL_ENABLED', 'false').lower() == 'true'
app.config['DEV_LOG_OTP'] = os.environ.get('DEV_LOG_OTP', 'true').lower() == 'true'

_PLACEHOLDER_MAIL_VALUES = {
    '',
    'your-gmail@gmail.com',
    'your-16-char-app-password',
    'PASTE_YOUR_APP_PASSWORD_HERE',
}


def _warn_mail_config():
    if not app.config.get('MAIL_ENABLED'):
        return
    username = app.config.get('MAIL_USERNAME', '')
    password = app.config.get('MAIL_PASSWORD', '')
    if username in _PLACEHOLDER_MAIL_VALUES or password in _PLACEHOLDER_MAIL_VALUES:
        print(
            '\n[MAIL] Gmail SMTP is enabled but credentials are missing.\n'
            '[MAIL] Set MAIL_PASSWORD in .env to your Google App Password\n'
            '[MAIL] Create one at: https://myaccount.google.com/apppasswords\n'
            '[MAIL] OTP emails will fail until this is configured.\n'
        )


_warn_mail_config()

CORS(app)
initialize_db(app)
Mail(app)
init_jwt(app)

UPLOAD_EMAIL_DIR = app_config.UPLOAD_OPEN_EMAIL_FOLDER.rstrip('/')
app.config['UPLOAD_EMAIL_FOLDER'] = UPLOAD_EMAIL_DIR
os.makedirs(UPLOAD_EMAIL_DIR, exist_ok=True)

UPLOAD_DOCUMENT_DIR = app_config.UPLOAD_OPEN_DOCUMENT_FOLDER.rstrip('/')
app.config['UPLOAD_DOCUMENT_FOLDER'] = UPLOAD_DOCUMENT_DIR
os.makedirs(UPLOAD_DOCUMENT_DIR, exist_ok=True)


def allowed_file(filename, allowed_extensions):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in allowed_extensions
    )


def splitpart(value, index, separator):
    parts = value.split(separator)
    if index == -1:
        return parts[-1]
    if 0 <= index < len(parts):
        return parts[index]
    return value


@app.route('/')
@app.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'service': 'map-backend'}), 200


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory('uploads', filename)


@app.route('/ai_chat', methods=['POST'])
@jwt_required()
def ai_chat():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request", "code": 400})

    body = request.json or {}
    message = (body.get('message') or '').strip()
    if not message:
        return jsonify({"msg": "Missing message parameter", "code": 400})

    history = body.get('history') or []
    context = body.get('context') or {'type': 'general'}

    try:
        reply = process_chat_request(
            int(org_id), message, history, current_user, context, user,
        )
    except AiChatError as exc:
        return jsonify({"msg": str(exc), "code": 503}), 503
    except Exception:
        return jsonify({"msg": "AI service unavailable", "code": 503}), 503

    return jsonify({"code": 200, "data": {"reply": reply}})


def extract_list_params(
    request,
    current_user,
    default_page=1,
    default_length=10,
    default_sort='create_date',
    default_order='desc',
):
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id', '')
    if not org_id:
        return None, None, None, None, None, None, None

    if request.method == 'POST' and request.is_json:
        filter_data = request.json.get('filter', []) if request.json else []
    else:
        filter_data = request.args.get('filter', [])
        if isinstance(filter_data, str):
            try:
                filter_data = json.loads(filter_data) if filter_data else []
            except (json.JSONDecodeError, ValueError):
                filter_data = []

    try:
        page = int(request.args.get('page', default_page))
        if page < 1:
            page = default_page
    except (ValueError, TypeError):
        page = default_page

    try:
        length = int(request.args.get('length', default_length))
        if length <= 0:
            length = default_length
        if length > 1000:
            length = 1000
    except (ValueError, TypeError):
        length = default_length

    sort = request.args.get('sort', default_sort) or default_sort
    order_str = request.args.get('order', default_order) or default_order
    order = -1 if order_str.lower() == 'desc' else 1
    search = request.args.get('search', '') or ''

    return int(org_id), filter_data, page, length, sort, order, search


def encode_password(password):
    return base64.b64encode(password.encode()).decode('utf-8')


def generate_otp():
    return ''.join(random.choice('0123456789') for _ in range(6))


def dumps_response(payload):
    return Response(json.dumps(payload, default=json_util.default), mimetype='application/json')


def build_role_data(org_id, user_id):
    role_data = MongoAPI.get_user_role_data(org_id, user_id)
    if not role_data:
        role_id = MongoAPI.userAdministratorRole(org_id)
        if not role_id:
            role_id = MongoAPI.create_administrator_role(org_id, user_id)
        role_data = MongoAPI.getRolesListDetails(org_id, role_id)
    return Uid.fix_array_role(role_data)


def require_authenticated_user():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    if not user:
        return None, None, (jsonify({'msg': 'Invalid user', 'code': 401}), 401)
    return current_user, user, None


def require_manage_settings():
    current_user, user, error = require_authenticated_user()
    if error:
        return None, None, None, error
    org_id = user.get('org_id')
    if not MongoAPI.user_has_permission(org_id, current_user, 'manage_settings'):
        return None, None, None, (jsonify({
            'msg': "You don't have access to manage settings",
            'code': 403,
        }), 403)
    return current_user, user, org_id, None


def require_user_management():
    current_user, user, error = require_authenticated_user()
    if error:
        return None, None, None, error
    org_id = user.get('org_id')
    role_data = MongoAPI.get_user_role_data(org_id, current_user)
    if not can_manage_users(user, role_data):
        return None, None, None, (jsonify({
            'msg': "You don't have access to manage users",
            'code': 403,
        }), 403)
    return current_user, user, org_id, None


def require_branch_management():
    current_user, user, error = require_authenticated_user()
    if error:
        return None, None, None, error
    org_id = user.get('org_id')
    tier = effective_tier(user)
    if tier not in ('super_admin', 'admin'):
        return None, None, None, (jsonify({
            'msg': "You don't have access to manage branches",
            'code': 403,
        }), 403)
    return current_user, user, org_id, None


def build_login_payload(user_id, org_id):
    user_details = MongoAPI.getUserDetails(org_id, user_id)
    organization = MongoAPI.organizationInfo(org_id)
    role_data = build_role_data(org_id, user_id)
    plan_data = MongoAPI.get_plan_data(org_id)
    access_token, refresh_token = create_user_tokens(user_id)
    return {
        'result': user_details,
        'access_token': access_token,
        'refresh_token': refresh_token,
        'roleData': role_data,
        'organization': organization,
        'planData': plan_data,
    }


def newCompany(org_id, user_id):
    role_id = MongoAPI.userAdministratorRole(org_id)
    if not role_id:
        MongoAPI.create_administrator_role(org_id, user_id)
    MongoAPI.set_user_tier(org_id, user_id, 'super_admin', None)
    MongoAPI.seed_default_branches(org_id)
    MongoAPI.seedLeadDefaultSettings(org_id)
    MongoAPI.seedProjectDefaultSettings(org_id)
    return True


def _backend_logo_url():
    return f"{app_config.BASE_URL.rstrip('/')}/uploads/logo.png"


def _client_app_url(path=''):
    base = app_config.CLIENT_APP_URL
    if not base:
        return ''
    path = (path or '').lstrip('/')
    return f"{base}/{path}" if path else base


def render_auth_email(template_name, user_id, **template_context):
    return render_template(
        template_name,
        logo=_backend_logo_url(),
        reset_password_url=_client_app_url(f'reset-password?user_id={user_id}'),
        **template_context,
    )


@app.route('/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    email = request.json.get('email')
    password = request.json.get('password')
    device_id = request.json.get('device_id')

    if not email:
        return jsonify({'msg': 'Missing email parameter', 'code': 400})
    if not password:
        return jsonify({'msg': 'Missing password parameter', 'code': 400})

    if not device_id:
        device_id = ''
        app_type = 'web'
    else:
        app_type = 'mobile'

    response = MongoAPI.selectLogin(email, encode_password(password))

    if response == 'no such name':
        if MongoAPI.emailCheck(email) == 'Yes':
            return jsonify({'msg': 'Invalid Password.', 'code': 400})
        return jsonify({'msg': 'Invalid Email', 'code': 400})

    if response['status'] == 'inactive':
        return jsonify({'msg': 'Your account is inactive, Please contact Admin', 'code': 400})

    organization = MongoAPI.organizationInfo(response['org_id'])
    role_data = build_role_data(response['org_id'], response['id'])
    plan_data = MongoAPI.get_plan_data(response['org_id'])
    access_token, refresh_token = create_user_tokens(response['id'])

    MongoAPI.updateDeviceID(response['org_id'], response['id'], device_id)
    current_time = datetime.datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S.%f')
    MongoAPI.userAudit(response['id'], response['org_id'], current_time, app_type)

    verify_otp = generate_otp()
    MongoAPI.change_otp(response['id'], verify_otp)

    if organization.get('two_step') == 'email':
        send_auth_email(
            email,
            '2-Step Verification',
            render_auth_email('login_otp_html.html', response['id'], verify_otp=verify_otp),
            verify_otp=verify_otp,
        )

    return jsonify({
        'msg': 'You have been successfully Logged in.',
        'code': 200,
        'data': {
            'result': response,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'roleData': role_data,
            'organization': organization,
            'planData': plan_data,
        },
    })


@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    if not user:
        return jsonify({'msg': 'Invalid user', 'code': 401}), 401

    device_id = request.json.get('device_id') if request.is_json else None
    if device_id:
        app_type = 'mobile'
    else:
        app_type = 'web'

    org_id = user.get('org_id')
    current_time = datetime.datetime.now(timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S.%f')

    if app_type == 'mobile':
        MongoAPI.userLogoutMobile(current_user, org_id, current_time)
        MongoAPI.clearDeviceID(org_id, current_user)
    else:
        MongoAPI.userLogoutWeb(current_user, org_id, current_time)

    revoke_current_token()

    if request.is_json:
        refresh_token = request.json.get('refresh_token')
        if refresh_token:
            revoke_token_string(refresh_token)

    return jsonify({'msg': 'You have been successfully logged out.', 'code': 200})


@app.route('/signup', methods=['POST'])
def userSignUp():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request'})

    email = request.json.get('email', None)
    plan_id = request.json.get('plan_id', None)
    trial = request.json.get('trial', None)
    plan_start_date = request.json.get('plan_start_date', None)
    plan_end_date = request.json.get('plan_end_date', None)
    create_date = request.json.get('create_date', None)
    device_id = request.json.get('device_id', None)
    coupon = request.json.get('coupon', '')
    partner_id = request.json.get('partner_id', None)

    if not email:
        return jsonify({'msg': 'Missing email parameter', 'code': 400})

    if not device_id:
        device_id = ''
        app_type = 'web'
    else:
        app_type = 'mobile'

    user = MongoAPI.userCheck(email)
    if user == 'Yes':
        return jsonify({'msg': 'Email id is already registered', 'code': 400})

    signup_via = 'email'
    org_id = MongoAPI.create_organization_planData(
        email, '', plan_id, trial, plan_start_date, plan_end_date, signup_via, partner_id,
    )
    if org_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
    org_id = int(org_id)

    password = base64.b64encode(''.encode())
    verify_otp = ''.join(random.choice('0123456789') for _ in range(6))
    response1 = MongoAPI.createUser_plan(
        email, password, '', org_id, create_date, plan_start_date, plan_end_date, verify_otp,
    )

    if response1:
        user_id_value = response1['user_id']

        newCompany(org_id, user_id_value)
        MongoAPI.insertDemoData(org_id, response1['user_id'])

        role_id = MongoAPI.userAdministratorRole(org_id)
        role_id = response1.get('role', role_id)
        role = MongoAPI.getRolesListDetails(org_id, role_id)
        roleData = Uid.fix_array_role(role)

        organization = MongoAPI.organizationInfo(org_id)

        logo = _backend_logo_url()
        otp_verification_mail = render_template(
            'signup_verification_code.html',
            verify_otp=verify_otp,
            logo=logo,
            REDIRECT_URI=_client_app_url('configuration'),
        )

        str_id = str(org_id)
        encode_id = str_id
        activation_link = app.config.get('ACTIVATION_LINK', '')
        encoded_link = activation_link + encode_id

        organization = MongoAPI.organizationInfo(org_id)

        data1 = defaultdict(list)
        data1['subject'] = 'Welcome To MAP'
        data1['content'] = otp_verification_mail
        data1['to'] = email
        data1['cc'] = ''
        data1['bcc'] = ''

        emailId = app_config.DEFAULT_FROM_EMAIL
        attachment = ''
        data1['associate_id'] = user_id_value
        data1['associate_to'] = 'signup'

        sendMail = MongoAPI.emailSubmit_signup(org_id, user_id_value, data1, emailId, attachment)
        email_sent = send_signup_email(
            email,
            data1['subject'],
            otp_verification_mail,
            emailId,
            verify_otp=verify_otp,
        )

        data = {
            'user': user_id_value,
            'access_token': '',
            'refresh_token': '',
            'organization': organization,
            'roleData': roleData,
        }
        reresult = {
            'data': data,
            'code': 200,
            'msg': 'Account registered successfully.',
            'email_sent': email_sent,
        }
        return dumps_response(reresult)

    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/otp_verify_match', methods=['POST'])
def otp_verify_match():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    user_id = request.json.get('user')
    verify_otp = request.json.get('verify_otp')

    if not user_id:
        return jsonify({'message': 'Missing user parameter', 'code': 400})
    if not verify_otp:
        return jsonify({'message': 'Missing verify_otp parameter', 'code': 400})

    user_details = MongoAPI.authorizationCheck_otp(user_id)
    if not user_details or user_details.get('verify_otp') != verify_otp:
        return jsonify({'message': 'OTP verification failed', 'code': 400})

    org_id = user_details.get('org_id')
    organization = MongoAPI.organizationInfo(org_id)
    role_data = build_role_data(org_id, user_details['id'])
    plan_data = MongoAPI.get_plan_data(org_id)
    access_token, refresh_token = create_user_tokens(user_details['id'])

    return dumps_response({
        'data': {
            'user': user_details,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'organization': organization,
            'roleData': role_data,
            'planData': plan_data,
        },
        'code': 200,
        'msg': 'Account registered successfully.',
        'user_verify_otp': user_details.get('verify_otp'),
    })


@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    user_id = request.json.get('user_id')
    if not user_id:
        return jsonify({'message': 'Missing user_id parameter', 'code': 400})

    user = MongoAPI.authorizationCheck_otp(user_id)
    if not user:
        return jsonify({'message': 'User not found', 'code': 400})

    verify_otp = generate_otp()
    MongoAPI.change_otp(user_id, verify_otp)
    send_auth_email(
        user['email'],
        'Welcome To MAP',
        render_auth_email('resend_verification_code.html', user_id, verify_otp=verify_otp),
        verify_otp=verify_otp,
    )
    return jsonify({'message': 'OTP resent successfully', 'code': 200})


@app.route('/login_resend_otp', methods=['POST'])
def login_resend_otp():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    user_id = request.json.get('user_id')
    if not user_id:
        return jsonify({'message': 'Missing user_id parameter', 'code': 400})

    user = MongoAPI.authorizationCheck_otp(user_id)
    if not user:
        return jsonify({'message': 'User not found', 'code': 400})

    verify_otp = generate_otp()
    MongoAPI.change_otp(user_id, verify_otp)
    send_auth_email(
        user['email'],
        '2-Step Verification',
        render_auth_email('login_otp_html.html', user_id, verify_otp=verify_otp),
        verify_otp=verify_otp,
    )
    return jsonify({'message': 'OTP resent successfully', 'code': 200})


@app.route('/forgot_password_check', methods=['POST'])
def forgot_password_check():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    email = request.json.get('email')
    if not email:
        return jsonify({'msg': 'Missing email in request', 'code': 400})

    if MongoAPI.emailCheck(email) != 'Yes':
        return jsonify({'msg': 'Invalid Email', 'code': 400})

    user_data = MongoAPI.get_user_by_email(email)
    if user_data == 'no such name':
        return jsonify({'msg': 'Invalid Email', 'code': 400})

    send_auth_email(
        email,
        'Reset Your MAP Password',
        render_auth_email('forgot_password.html', user_data['id']),
    )
    return jsonify({'msg': 'Email sent successfully.', 'code': 200})


@app.route('/creat_new_password', methods=['POST'])
def creat_new_password():
    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    new_password = request.json.get('new_password')
    user_id = request.json.get('user_id')

    if not new_password:
        return jsonify({'msg': 'Missing new password parameter', 'code': 400})
    if not user_id:
        return jsonify({'msg': 'Missing user_id parameter', 'code': 400})

    if MongoAPI.confirm_Password(user_id, encode_password(new_password)) == 'Yes':
        user = MongoAPI.authorizationCheck(user_id)
        if not user:
            return jsonify({'msg': 'User password successfully updated !', 'code': 200})
        org_id = user.get('org_id')
        return jsonify({
            'msg': 'User password successfully updated !',
            'code': 200,
            'data': build_login_payload(user_id, org_id),
        })
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/add_lead', methods=['POST'])
@jwt_required()
def add_lead():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]

    if ordId == '':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request'})

    name = request.json.get('name', None)
    phone = request.json.get('phone', None)
    # company_name = request.json.get('company_name', None)
    description = request.json.get('description', None)
    customer_type = request.json.get('customer_type', None)
    email = request.json.get('email', None)

    if not name:
        return jsonify({'msg': 'Missing Name parameter', 'code': 400})

    org_id = int(ordId)
    data1 = json.loads(json_util.dumps(request.json))
    numbering = None
    lead_no = None
    response = None

    if org_id:
        numbering = MongoAPI.getNumberingSettings('lead', ordId)
        if not numbering:
            MongoAPI.getNumberingSettings2('lead', ordId)
            numbering = MongoAPI.getNumberingSettings('lead', ordId)

        if numbering:
            lead_no = f"{numbering['prefix']}/{numbering['sequence']}"
            data1['lead_no'] = lead_no

    response1 = MongoAPI.lead_submit(org_id, current_user, data1)
    response = json.loads(json_util.dumps(response1))
    lead_id = response

    if response:
        if numbering:
            try:
                next_sequence = int(numbering['sequence']) + 1
                MongoAPI.numberingUpdate(numbering['id'], next_sequence)
            except (KeyError, TypeError, ValueError):
                pass

        category_name = 'create'
        action = 'create'
        associate_to = 'lead'
        associate_id = ObjectId(response)
        via = 0
        extra_info = json.loads(json_util.dumps(data1))
        text_info = 'Created a Lead'
        title = 'Create'
        from_data = None
        to_data = None

        MongoAPI.user_activity(
            ordId, current_user, from_data, to_data,
            category_name, action, associate_to, associate_id, via,
            extra_info, text_info, title,
        )

        response1 = MongoAPI.get_lead_Details(ordId, lead_id, current_user)
        response = Uid.fix_array3(response1)

        if lead_no and isinstance(response, dict) and not response.get('lead_no'):
            response['lead_no'] = lead_no

        lead_list_id = response.get('_id')
        lead_assgined_to = response.get('assigned_to')

        user_details = MongoAPI.getUserDetails(org_id, lead_assgined_to)
        user_details = Uid.fix_array5(user_details)
        user_id = user_details.get('user_id')

        logo = _backend_logo_url()
        lead_detail_url = _client_app_url(f'lead_detail/{lead_list_id}')

        sales_lead_reminder = render_template(
            'sales_lead_reminder_org.html',
            lead_name=name,
            description=description,
            phone_no=phone,
            # company_name=company_name,
            logo=logo,
            lead_detail_url=lead_detail_url,
            email=email,
            company_id=lead_list_id,
        )

        if lead_assgined_to and lead_assgined_to != current_user and email:
            mail_data = defaultdict(list)
            mail_data['subject'] = 'Lead Reminder'
            mail_data['content'] = sales_lead_reminder
            mail_data['to'] = email
            mail_data['cc'] = ''
            mail_data['bcc'] = ''
            mail_data['associate_id'] = user_id
            mail_data['associate_to'] = 'signup'

            attachment = ''
            emailId = app_config.DEFAULT_FROM_EMAIL
            MongoAPI.emailSubmit(org_id, user_id or current_user, mail_data, emailId, attachment)

    return jsonify({'msg': 'Lead successfully created !', 'code': 200, 'data': response})


@app.route('/lead_list', methods=['GET', 'POST'])
@jwt_required()
def getlead_list():
    current_user = get_jwt_identity()

    org_id, filter_data, page, length, sort, order, search = extract_list_params(
        request, current_user,
    )

    if org_id is None:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    response1, search_count = MongoAPI.lead_list(
        org_id, current_user, length, page, filter_data, order, sort, search,
    )

    response = json.loads(json_util.dumps(response1))
    response1 = Uid.fix_array(response)

    total_count = MongoAPI.lead_count(org_id)

    resp = jsonify({
        'code': 200,
        'data': response1,
        'total_count': total_count,
        'search_count': search_count,
    })
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/lead_metrics', methods=['GET'])
@jwt_required()
def get_lead_metrics():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    try:
        aging_days = int(request.args.get('aging_days', 7))
        if aging_days < 1:
            aging_days = 7
    except (ValueError, TypeError):
        aging_days = 7

    metrics = MongoAPI.lead_metrics(int(org_id), current_user, aging_days)

    resp = jsonify({'code': 200, 'data': metrics})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/add_project', methods=['POST'])
@jwt_required()
def add_project():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    name = request.json.get('name')
    if not name:
        return jsonify({'msg': 'Missing Name parameter', 'code': 400})

    org_id = int(org_id)
    data1 = json.loads(json_util.dumps(request.json))
    branch_id = resolve_record_branch_id(user, data1.get('branch_id'))
    if branch_id and not MongoAPI.branch_exists(org_id, branch_id):
        return jsonify({'msg': 'Invalid branch_id', 'code': 400})
    if branch_id and not branch_allowed_for_user(user, branch_id):
        return jsonify({'msg': 'You do not have access to this branch', 'code': 403})
    if branch_id:
        data1['branch_id'] = branch_id

    project_no = None
    numbering = MongoAPI._ensure_project_numbering(org_id)

    if numbering:
        project_no = f"{numbering['prefix']}/{numbering['sequence']}"
        data1['project_no'] = project_no

    project_id = MongoAPI.project_submit(org_id, current_user, data1)
    if not project_id or project_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if numbering:
        try:
            next_sequence = int(numbering['sequence']) + 1
            MongoAPI.numberingUpdate(numbering['id'], next_sequence)
        except (KeyError, TypeError, ValueError):
            pass

    MongoAPI.user_activity(
        org_id, current_user, None, None,
        'create', 'create', 'project', ObjectId(project_id), 0,
        json.loads(json_util.dumps(data1)), 'Created a Project', 'Create',
    )

    response = MongoAPI.get_project_details(org_id, project_id, current_user)
    response = Uid.fix_array3(response)
    if project_no and isinstance(response, dict) and not response.get('project_no'):
        response['project_no'] = project_no

    return jsonify({
        'msg': 'Project successfully created !',
        'code': 200,
        'data': response,
    })


@app.route('/project_list', methods=['GET', 'POST'])
@jwt_required()
def get_project_list():
    current_user = get_jwt_identity()
    org_id, filter_data, page, length, sort, order, search = extract_list_params(
        request, current_user,
    )

    if org_id is None:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    response1, search_count = MongoAPI.project_list(
        org_id, current_user, length, page, filter_data, order, sort, search,
    )
    response = Uid.fix_array(json.loads(json_util.dumps(response1)))
    total_count = MongoAPI.project_count(org_id)

    resp = jsonify({
        'code': 200,
        'data': response,
        'total_count': total_count,
        'search_count': search_count,
    })
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/project_metrics', methods=['GET'])
@jwt_required()
def get_project_metrics():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    metrics = MongoAPI.project_metrics(int(org_id), current_user)
    resp = jsonify({'code': 200, 'data': metrics})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/booking_metrics', methods=['GET'])
@jwt_required()
def get_booking_metrics():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    metrics = MongoAPI.booking_metrics(int(org_id), current_user)
    resp = jsonify({'code': 200, 'data': metrics})
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/booking_list', methods=['GET', 'POST'])
@jwt_required()
def get_booking_list():
    current_user = get_jwt_identity()
    org_id, filter_data, page, length, sort, order, search = extract_list_params(
        request, current_user,
    )
    if org_id is None:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    project_id = request.args.get('project_id') or request.args.get('projectId')
    unit_id = request.args.get('unit_id') or request.args.get('unitId')
    status = request.args.get('status')

    if request.method == 'POST' and request.is_json and not search:
        body_search = request.json.get('search', {})
        if isinstance(body_search, dict):
            search = body_search.get('value', '') or search

    result = MongoAPI.booking_list(
        org_id, current_user, length, page, filter_data,
        order, sort, search, project_id, unit_id, status,
    )
    rows = Uid.fix_array(json.loads(json_util.dumps(result['rows'])))

    resp = jsonify({
        'code': 200,
        'data': {
            'bookings': rows,
            'summary': result['summary'],
        },
        'total_count': result['search_count'],
        'search_count': result['search_count'],
    })
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/booking_detail/<id>', methods=['GET'])
@jwt_required()
def get_booking_detail(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    data = MongoAPI.get_booking_details(int(org_id), id, current_user)
    data = Uid.fix_array3(data)
    if data:
        return jsonify({'msg': 'Booking details !', 'code': 200, 'data': data})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/add_booking', methods=['POST'])
@jwt_required()
def add_booking():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    org_id = int(org_id)
    data1 = json.loads(json_util.dumps(request.json))
    branch_id = resolve_record_branch_id(user, data1.get('branch_id'))
    if branch_id and not MongoAPI.branch_exists(org_id, branch_id):
        return jsonify({'msg': 'Invalid branch_id', 'code': 400})
    if branch_id and not branch_allowed_for_user(user, branch_id):
        return jsonify({'msg': 'You do not have access to this branch', 'code': 403})
    if branch_id:
        data1['branch_id'] = branch_id

    numbering = None
    if not str(data1.get('receipt_number') or '').strip():
        numbering = MongoAPI._ensure_booking_numbering(org_id)

    booking_id = MongoAPI.booking_submit(org_id, current_user, data1)
    booking_errors = {
        'duplicate_receipt': 'Receipt number already exists',
        'unit_booked': 'This unit already has an active booking',
        'unit_sold': 'Cannot add a payment — this unit is already sold',
    }
    if booking_id in booking_errors:
        return jsonify({'msg': booking_errors[booking_id], 'code': 400})
    if not booking_id or booking_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if numbering:
        try:
            next_sequence = int(numbering['sequence']) + 1
            MongoAPI.numberingUpdate(numbering['id'], next_sequence)
        except (KeyError, TypeError, ValueError):
            pass

    MongoAPI.user_activity(
        org_id, current_user, None, None,
        'create', 'create', 'booking', ObjectId(booking_id), 0,
        data1, 'Created a Booking', 'Create',
    )

    response = MongoAPI.get_booking_details(org_id, booking_id, current_user)
    return jsonify({
        'msg': 'Booking successfully created !',
        'code': 200,
        'data': Uid.fix_array3(response),
    })


@app.route('/booking_edit/<id>', methods=['PUT'])
@jwt_required()
def booking_update(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    org_id = int(org_id)
    if not MongoAPI.user_has_permission(org_id, current_user, 'edit_booking'):
        return jsonify({
            'msg': "You don't have permission to edit bookings",
            'code': 403,
        }), 403

    data1 = json.loads(json_util.dumps(request.json))
    response1 = MongoAPI.booking_update(org_id, current_user, data1, id)
    booking_update_errors = {
        'booking_not_found': 'Booking not found',
        'invalid_amount': 'Amount must be greater than zero',
        'invalid_payment_type': 'Invalid payment type',
        'invalid_transaction_type': 'Invalid transaction type',
        'invalid_dates': 'Registration date cannot be before booking date',
        'invalid_status': 'Invalid booking status',
    }
    if response1 in booking_update_errors:
        return jsonify({'msg': booking_update_errors[response1], 'code': 400})
    if response1 and response1 != '0':
        data = MongoAPI.get_booking_details(org_id, id, current_user)
        return jsonify({
            'msg': 'Booking successfully Updated !',
            'code': 200,
            'data': Uid.fix_array3(data) or data1,
        })
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


def _booking_delete_response(org_id, current_user, result, activity_payload):
    booking_delete_errors = {
        'booking_not_found': ('Booking not found', 404),
        'invalid_params': ('Invalid project_id or unit_id', 400),
    }
    if result in booking_delete_errors:
        msg, code = booking_delete_errors[result]
        return jsonify({'msg': msg, 'code': code}), code

    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if isinstance(result, list):
        deleted_ids = result
        activity_id = ObjectId(deleted_ids[0])
    else:
        deleted_ids = [result]
        activity_id = ObjectId(result)

    MongoAPI.user_activity(
        org_id, current_user, None, None,
        'delete', 'delete', 'booking', activity_id, 0,
        activity_payload, 'Deleted a Booking', 'Delete',
    )

    return jsonify({
        'msg': 'Booking successfully deleted !',
        'code': 200,
        'data': {
            'id': deleted_ids[0] if len(deleted_ids) == 1 else None,
            'ids': deleted_ids,
            'count': len(deleted_ids),
        },
    })


@app.route('/booking_delete', methods=['DELETE', 'PUT', 'GET'])
@jwt_required()
def booking_delete_by_unit():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)
    if not MongoAPI.user_has_permission(org_id, current_user, 'delete_booking'):
        return jsonify({
            'msg': "You don't have permission to delete bookings",
            'code': 403,
        }), 403

    project_id = request.args.get('project_id') or request.args.get('projectId')
    unit_id = request.args.get('unit_id') or request.args.get('unitId')
    if not project_id or not unit_id:
        return jsonify({
            'msg': 'Missing project_id or unit_id parameter',
            'code': 400,
        })

    result = MongoAPI.booking_delete_by_unit(
        org_id, current_user, project_id, unit_id,
    )
    return _booking_delete_response(
        org_id, current_user, result,
        {'project_id': project_id, 'unit_id': unit_id},
    )


@app.route('/booking_delete/<id>', methods=['DELETE', 'PUT'])
@jwt_required()
def booking_delete(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)
    if not MongoAPI.user_has_permission(org_id, current_user, 'delete_booking'):
        return jsonify({
            'msg': "You don't have permission to delete bookings",
            'code': 403,
        }), 403

    result = MongoAPI.booking_delete(org_id, current_user, id)
    return _booking_delete_response(
        org_id, current_user, result, {'booking_id': id},
    )


@app.route('/project_detail/<id>', methods=['GET'])
@jwt_required()
def get_project_detail(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    data = MongoAPI.get_project_details(int(org_id), id, current_user)
    data = Uid.fix_array3(data)
    if data:
        return jsonify({'msg': 'Project details !', 'code': 200, 'data': data})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/project_edit/<id>', methods=['PUT'])
@jwt_required()
def project_update(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data1 = json.loads(json_util.dumps(request.json))
    response1 = MongoAPI.project_update(int(org_id), current_user, data1, id)
    if response1:
        data = MongoAPI.get_project_details(int(org_id), id, current_user)
        data = Uid.fix_array3(data)
        return jsonify({
            'msg': 'Project successfully Updated !',
            'code': 200,
            'data': data or data1,
        })
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/project_units', methods=['GET', 'POST', 'PUT'])
@jwt_required()
def project_units():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)

    if request.method == 'GET':
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({'msg': 'Missing project_id parameter', 'code': 400})
        units = MongoAPI.project_units_list(org_id, project_id, current_user)
        return jsonify({
            'code': 200,
            'data': Uid.fix_array(json.loads(json_util.dumps(units))),
        })

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    if request.method == 'POST':
        data1 = json.loads(json_util.dumps(request.json))
        unit_id = MongoAPI.project_unit_submit(org_id, current_user, data1)
        if not unit_id or unit_id == '0':
            return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
        project_id = data1.get('project_id')
        units = MongoAPI.project_units_list(org_id, project_id, current_user)
        created = next((u for u in units if u.get('_id') == unit_id), None)
        return jsonify({
            'msg': 'Unit successfully created !',
            'code': 200,
            'data': Uid.fix_array3(created),
        })

    unit_id = request.json.get('_id') or request.json.get('unit_id')
    if not unit_id:
        return jsonify({'msg': 'Missing unit id parameter', 'code': 400})

    data1 = json.loads(json_util.dumps(request.json))
    response1 = MongoAPI.project_unit_update(org_id, current_user, data1, unit_id)
    if response1:
        return jsonify({
            'msg': 'Unit successfully Updated !',
            'code': 200,
            'data': data1,
        })
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/project_units/<project_id>', methods=['GET', 'POST', 'PUT'])
@jwt_required()
def project_units_by_project(project_id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)

    if request.method == 'GET':
        units = MongoAPI.project_units_list(org_id, project_id, current_user)
        return jsonify({
            'code': 200,
            'data': Uid.fix_array(json.loads(json_util.dumps(units))),
        })

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    if request.method == 'PUT':
        data1 = json.loads(json_util.dumps(request.json))
        unit_id = project_id
        response1 = MongoAPI.project_unit_update(org_id, current_user, data1, unit_id)
        if response1:
            return jsonify({
                'msg': 'Unit successfully Updated !',
                'code': 200,
                'data': data1,
            })
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    data1 = json.loads(json_util.dumps(request.json))
    data1['project_id'] = project_id
    unit_id = MongoAPI.project_unit_submit(org_id, current_user, data1)
    if not unit_id or unit_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    units = MongoAPI.project_units_list(org_id, project_id, current_user)
    created = next((u for u in units if u.get('_id') == unit_id), None)
    return jsonify({
        'msg': 'Unit successfully created !',
        'code': 200,
        'data': Uid.fix_array3(created),
    })


@app.route('/project_booking_units', methods=['GET'])
@jwt_required()
def project_booking_units():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    project_id = request.args.get('project_id')
    if not project_id:
        return jsonify({'msg': 'Missing project_id parameter', 'code': 400})

    units = MongoAPI.project_booking_units_list(
        int(org_id), project_id, current_user,
    )
    return jsonify({
        'code': 200,
        'data': Uid.fix_array(json.loads(json_util.dumps(units))),
    })


@app.route('/project_booking_units/<project_id>', methods=['GET'])
@jwt_required()
def project_booking_units_by_project(project_id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    units = MongoAPI.project_booking_units_list(
        int(org_id), project_id, current_user,
    )
    return jsonify({
        'code': 200,
        'data': Uid.fix_array(json.loads(json_util.dumps(units))),
    })


@app.route('/project_site_visits', methods=['GET', 'POST'])
@jwt_required()
def project_site_visits():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)

    if request.method == 'GET':
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({'msg': 'Missing project_id parameter', 'code': 400})
        visits = MongoAPI.project_site_visits_list(org_id, project_id, current_user)
        return jsonify({
            'code': 200,
            'data': Uid.fix_array(json.loads(json_util.dumps(visits))),
        })

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data1 = json.loads(json_util.dumps(request.json))
    visit_id = MongoAPI.project_site_visit_submit(org_id, current_user, data1)
    if not visit_id or visit_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    project_id = data1.get('project_id')
    visits = MongoAPI.project_site_visits_list(org_id, project_id, current_user)
    created = next((v for v in visits if v.get('_id') == visit_id), None)
    return jsonify({
        'msg': 'Site visit successfully created !',
        'code': 200,
        'data': Uid.fix_array3(created),
    })


@app.route('/project_site_visits/<project_id>', methods=['GET', 'POST'])
@jwt_required()
def project_site_visits_by_project(project_id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)

    if request.method == 'GET':
        visits = MongoAPI.project_site_visits_list(org_id, project_id, current_user)
        return jsonify({
            'code': 200,
            'data': Uid.fix_array(json.loads(json_util.dumps(visits))),
        })

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data1 = json.loads(json_util.dumps(request.json))
    data1['project_id'] = project_id
    visit_id = MongoAPI.project_site_visit_submit(org_id, current_user, data1)
    if not visit_id or visit_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    visits = MongoAPI.project_site_visits_list(org_id, project_id, current_user)
    created = next((v for v in visits if v.get('_id') == visit_id), None)
    return jsonify({
        'msg': 'Site visit successfully created !',
        'code': 200,
        'data': Uid.fix_array3(created),
    })


@app.route('/project_match_leads', methods=['GET'])
@jwt_required()
def project_match_leads():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    project_id = request.args.get('project_id')
    if not project_id:
        return jsonify({'msg': 'Missing project_id parameter', 'code': 400})

    matched = MongoAPI.project_match_leads(int(org_id), project_id, current_user)
    return jsonify({
        'code': 200,
        'data': Uid.fix_array(json.loads(json_util.dumps(matched))),
    })


@app.route('/project_documents', methods=['GET', 'POST'])
@jwt_required()
def project_documents():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)

    if request.method == 'GET':
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({'msg': 'Missing project_id parameter', 'code': 400})
        documents = MongoAPI.project_documents_list(org_id, project_id, current_user)
        return jsonify({
            'code': 200,
            'data': Uid.fix_array(json.loads(json_util.dumps(documents))),
        })

    project_id = request.form.get('project_id') or (
        request.json.get('project_id') if request.is_json else None
    )
    if not project_id:
        return jsonify({'msg': 'Missing project_id parameter', 'code': 400})

    name = request.form.get('name') or (
        request.json.get('name') if request.is_json else None
    )
    category = request.form.get('category') or (
        request.json.get('category') if request.is_json else 'other'
    ) or 'other'
    file_url = request.json.get('file_url') if request.is_json else None

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        if not allowed_file(file.filename, app_config.ALLOWED_EXTENSIONS):
            return jsonify({
                'msg': f"Allowed file types are {app_config.ALLOWED_EXTENSIONS}",
                'code': 400,
            })
        original_filename = secure_filename(file.filename)
        file_format = splitpart(file.filename, -1, '.')
        file_name = splitpart(file.filename, 0, '.')
        stored_filename = (
            file_name + time.strftime('_%d_%Y_%H_%M_%S') + '.' + file_format
        )
        upload_dir = app.config['UPLOAD_DOCUMENT_FOLDER']
        file.save(os.path.join(upload_dir, stored_filename))
        file_url = (
            f"{app_config.BASE_URL}{app_config.UPLOAD_OPEN_DOCUMENT_FOLDER}{stored_filename}"
        )
        if not name:
            name = original_filename

    if not file_url:
        return jsonify({'msg': 'Missing file or file_url parameter', 'code': 400})
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})

    doc_id = MongoAPI.project_document_submit(
        org_id, current_user, project_id, name, category, file_url,
    )
    if not doc_id or doc_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    documents = MongoAPI.project_documents_list(org_id, project_id, current_user)
    created = next((d for d in documents if d.get('_id') == doc_id), None)
    return jsonify({
        'msg': 'Document successfully uploaded !',
        'code': 200,
        'data': Uid.fix_array3(created),
    })


@app.route('/project_documents/<project_id>', methods=['GET', 'POST'])
@jwt_required()
def project_documents_by_project(project_id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    org_id = int(org_id)

    if request.method == 'GET':
        documents = MongoAPI.project_documents_list(org_id, project_id, current_user)
        return jsonify({
            'code': 200,
            'data': Uid.fix_array(json.loads(json_util.dumps(documents))),
        })

    name = request.form.get('name') or (
        request.json.get('name') if request.is_json else None
    )
    category = request.form.get('category') or (
        request.json.get('category') if request.is_json else 'other'
    ) or 'other'
    file_url = request.json.get('file_url') if request.is_json else None

    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        if not allowed_file(file.filename, app_config.ALLOWED_EXTENSIONS):
            return jsonify({
                'msg': f"Allowed file types are {app_config.ALLOWED_EXTENSIONS}",
                'code': 400,
            })
        original_filename = secure_filename(file.filename)
        file_format = splitpart(file.filename, -1, '.')
        file_name = splitpart(file.filename, 0, '.')
        stored_filename = (
            file_name + time.strftime('_%d_%Y_%H_%M_%S') + '.' + file_format
        )
        upload_dir = app.config['UPLOAD_DOCUMENT_FOLDER']
        file.save(os.path.join(upload_dir, stored_filename))
        file_url = (
            f"{app_config.BASE_URL}{app_config.UPLOAD_OPEN_DOCUMENT_FOLDER}{stored_filename}"
        )
        if not name:
            name = original_filename

    if not file_url:
        return jsonify({'msg': 'Missing file or file_url parameter', 'code': 400})
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})

    doc_id = MongoAPI.project_document_submit(
        org_id, current_user, project_id, name, category, file_url,
    )
    if not doc_id or doc_id == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    documents = MongoAPI.project_documents_list(org_id, project_id, current_user)
    created = next((d for d in documents if d.get('_id') == doc_id), None)
    return jsonify({
        'msg': 'Document successfully uploaded !',
        'code': 200,
        'data': Uid.fix_array3(created),
    })



@app.route('/bulk_delete', methods=['GET'])
@jwt_required()
def bulk_delete():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.args.get:
            return jsonify({"msg": "Missing JSON in request"})

        id =  request.args.get('associate_id', None)
        associate_to =  request.args.get('associate_to', None)


        if not id:
            return jsonify({"msg": "Missing associate id parameter","code": 400})
        if not associate_to:
            return jsonify({"msg": "Missing associate to parameter","code": 400})



        org_id = int(ordId)

        if org_id:
            response1 = MongoAPI.bulk_delete(org_id,current_user,ObjectId(id),associate_to)
            response = json.loads(json_util.dumps(response1))
            # response = response1.to_json()
            # print (response)
            data = {'followUp':response}

            if associate_to=='company':
                mes = 'Company Deleted Successfully!'
            if associate_to=='lead':
                mes = 'lead Deleted Successfully!'
            if associate_to=='project':
                mes = 'Project Deleted Successfully!'
        #v1 modified
            if associate_to=='opportunity':
                mes = 'Opportunity Deleted Successfully!'

            if associate_to=='contact':
                mes = 'Contact Deleted Successfully!'
            if associate_to=='product':
                mes = 'Product Deleted Successfully!'
            elif associate_to=='quote':
                mes = 'Quote Deleted Successfully!'
            elif associate_to=='companyattachment':
                mes = 'Attachment successfully deleted !'
            elif associate_to=='opportunityattachment':
                mes = 'Attachment successfully deleted !'
            elif associate_to=='companycustomfields':
                mes = 'Custom Field successfully deleted !'
            elif associate_to=='taskcustomfields':
                mes = 'Task Field successfully deleted !'
            elif associate_to=='dealcustomfields':
                mes = 'Custom Field successfully deleted !'
            elif associate_to=='contactcustomfields':
                mes = 'Custom Field successfully deleted !'
            elif associate_to=='sale_order':
                mes = 'Sale Order successfully deleted !'
            
            elif associate_to=='sales_process':
                mes = 'Sales Process successfully deleted !'

            else:
                mes = 'Successfully deleted !'


            if data:
                # action = 'DELETE'
                # associate_to = associate_to
                # associate_id = id
                # via = 0
                # extra_info = json.loads(json_util.dumps(request.args))
                # text_info = 'DELETE'
                # title = 'DELETE'

                # from_data = None
                # to_data = None
                # category_name = "delete"


                # MongoAPI.user_activity(ordId, current_user, from_data, to_data, category_name, action, associate_to, associate_id, via, extra_info, text_info, title)

                return jsonify({"msg": mes,"code": 200})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})



@app.route('/notes', methods=['POST'])
@jwt_required()
def notes():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.is_json:
            return jsonify({"msg": "Missing JSON in request"})

        note =  request.json.get('note', None)
        associate_id =  request.json.get('associate_id', None)
        associate_to =  request.json.get('associate_to', None)
        # print(associate_to,associate_id,"5555555555555555555555555")
        location = request.json.get('location', None)
        # print(location,longitude,accuracy,"5555555555555555555555555")

        if not note:
            return jsonify({"msg": "Missing note parameter","code": 400})
        if not associate_id:
            return jsonify({"msg": "Missing associate id parameter","code": 400})
        if not associate_to:
            return jsonify({"msg": "Missing associate to parameter","code": 400})


        data1 = json.loads(json_util.dumps(request.json))

        data = data1

        org_id = int(ordId)

        if org_id:
            response1 = MongoAPI.noteSubmit(org_id,current_user,data)

            response = json.loads(json_util.dumps(response1))

            # print(data,"74185209638888888558585858585858")
            data = {'id':response}
            if data:
            

                if data1['associate_to']=='task':


                    taskdetails = MongoAPI.task_details(org_id,data1['associate_id'],current_user)

                    response = Uid.fix_array_multiple(taskdetails)


                    assigneto = set(response.get('assigned_to', []))
                    watchers_list = set(response.get('watchers', []))

                    for item in assigneto:

                            data5 = {'task_id': data1['associate_id'], 'header_name': '', 'read_status': 1, 'associate_to': data1['associate_to'], 'commands': note, 'clear_status': 0, 'assigned_to': item}
                            filtered_results = MongoAPI.task_notifications(org_id, current_user, data5)
                            # print(watchers_list, "*************************")

                    for watchers_item in watchers_list:

                        if watchers_item not in assigneto:
                            data5 = {'task_id': data1['associate_id'], 'header_name': '', 'read_status': 1, 'associate_to': data1['associate_to'], 'commands': note, 'clear_status': 0, 'assigned_to': watchers_item}
                            filtered_results1 = MongoAPI.task_notifications(org_id, current_user, data5)
                            # print("hgvhgvhgvhgvhghgvhghgv",filtered_results1,"kkkkkkkkkkkkkkkkkkkkkkkkkkk")


                elif data1['associate_to']=="company":

                    data5 = {'company_id': data1['associate_id'],
                            'header_name': '', 'read_status': 1 , 'associate_to': data1['associate_to'], 'commands': ' commands in this compny ', 'clear_status': 0}


                return jsonify({"msg": "Notes successfully created !","code": 200,"data": data})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})




@app.route('/lead_detail/<id>',methods=['GET'])
@jwt_required()
def getlaed(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:

        response1 = MongoAPI.get_lead_Details(ordId,id,current_user)
        # print(response1,"Lead_response4444558")

        # response_next_previus = MongoAPI.get_company_next_previous(ordId,id,current_user)
        # print(response_next_previus,"next_previous")

        response = Uid.fix_array3(response1)
        # next_previous = Uid.fix_array3(response_next_previus)

        data = response
        # print(data,"dfgfjgfgfuphone_nbo")


        if data:
            return jsonify({"msg": "Company details !","code": 200,"data": data,})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})



@app.route('/lead_activity/<id>', methods=['GET'])
@jwt_required()
def lead_activity(id):
    partner_user = get_jwt_identity()
    partner_user_detail = AdminAPI.PartnerCheck(partner_user)
    partner_id = partner_user_detail.get('partner_id')

    partner_id = ''
    for user2 in partner_user_detail:
        if user2=='partner_id':
            partner_id = partner_user_detail[user2]

    if partner_id=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        # partner_id = ObjectId(partner_id)

        order =  request.args.get('order', None)
        sort =  request.args.get('sort', None)

        if not order:
            order=''
        if not sort:
            sort=''

        if order=='desc':
            order=-1
        elif order=='asc':
            order=1
        else:
            order=-1

        if sort:
            sort=sort
        else:
            sort='create_date'

        notes = AdminAPI.getNotes(partner_id,partner_user,ObjectId(id),'admin_lead',sort,order)
        notes = Uid.fix_array(notes)

        email = AdminAPI.getEmail(partner_id,partner_user,ObjectId(id),'admin_lead',sort,order)
        email = Uid.fix_array(email)

        document = AdminAPI.getDocument(partner_id,partner_user,ObjectId(id),'admin_lead',sort,order)
        document = Uid.fix_array(document)

        timeline = AdminAPI.getTimeline(partner_id,partner_user,id,'admin_lead',sort,order)
        timeline = Uid.fix_array(timeline)

        data={
            'notes':notes,
            'email':email,
           'document':document,
           'timeline':timeline,

        }

        if data:
            return jsonify({"msg": "Lead details !","code": 200,"data": data})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})





@app.route('/sales_lead_activity/<id>', methods=['GET'])
@jwt_required()
def sales_lead_activity(id):
    current_user = get_jwt_identity()
    # print(current_user,"difhjdfhdfojuser-1")
    user = MongoAPI.authorizationCheck(current_user)


    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        org_id = int(ordId)

        order =  request.args.get('order', None)
        sort =  request.args.get('sort', None)

        if not order:
            order=''
        if not sort:
            sort=''

        if order=='desc':
            order=-1
        elif order=='asc':
            order=1
        else:
            order=-1

        if sort:
            sort=sort
        else:
            sort='create_date'

        notes = MongoAPI.getNotes(org_id,current_user,ObjectId(id),'lead',sort,order)
        notes = Uid.fix_array(notes)

        # print(notes,"DFGDFGD")
        email = MongoAPI.getEmail(org_id,current_user,ObjectId(id),'lead',sort,order)
        email = Uid.fix_array(email)

        document = MongoAPI.getDocument(org_id,current_user,ObjectId(id),'lead',sort,order)
        document = Uid.fix_array(document)
        # print("moster",document,"looping")



        timeline = MongoAPI.getTimeline(org_id,current_user,id,'lead',sort,order)
        timeline = Uid.fix_array(timeline)

        # print(timeline,"kkkkkk")
        data={

            'notes':notes,
            'email': email,
           'document':document,
           'timeline':timeline,


        }

        if data:
            return jsonify({"msg": "lead details !","code": 200,"data": data})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})



@app.route('/lead_edit/<id>', methods=['PUT'])
@jwt_required()
def lead_update(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.is_json:
            return jsonify({"msg": "Missing JSON in request"})

        company_name =  request.json.get('company_name', None)
        name =  request.json.get('name', None)
        description =  request.json.get('description', None)
        url =  request.json.get('url', None)
        gstin =  request.json.get('gstin', None)

        # if not description:
        #     return jsonify({"msg": "Missing description parameter","code": 400})
        # if not url:
        #     return jsonify({"msg": "Missing url parameter","code": 400})
        # if not id:
        #     return jsonify({"msg": "Missing company_id parameter","code": 400})

        org_id = int(ordId)

        if not MongoAPI.user_has_permission(org_id, current_user, 'edit_lead'):
            return jsonify({
                'msg': "You don't have permission to edit leads",
                'code': 403,
            }), 403

        data1 = json.loads(json_util.dumps(request.json))
        data = data1

        # print(data,"phone_data")
        response1 = MongoAPI.lead_update(org_id,current_user,data1,id)
        # print(response1,"response1_response1")
        response = json.loads(json_util.dumps(response1))

    if response:
        return jsonify({"msg": "Lead successfully Updated !","code": 200,"data": data})
    else:
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})


@app.route('/lead_suggested_projects/<id>', methods=['GET', 'PUT'])
@jwt_required()
def lead_suggested_projects(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = user.get('org_id')
    if not ordId:
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    org_id = int(ordId)

    if request.method == 'GET':
        project_ids = MongoAPI.get_lead_suggested_projects(org_id, id)
        return jsonify({
            "msg": "Suggested projects fetched successfully!",
            "code": 200,
            "data": project_ids,
        })

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request", "code": 400})

    if not MongoAPI.user_has_permission(org_id, current_user, 'edit_lead'):
        return jsonify({
            'msg': "You don't have permission to edit leads",
            'code': 403,
        }), 403

    project_ids = request.json.get('suggested_projects', [])
    response = MongoAPI.update_lead_suggested_projects(org_id, id, project_ids)
    if response and response != '0':
        return jsonify({
            "msg": "Suggested projects updated successfully!",
            "code": 200,
            "data": project_ids,
        })

    return jsonify({"msg": "Oops,Something went wrong !", "code": 400})


def _lead_associates_response(org_id, lead_id, current_user):
    data = MongoAPI.sales_lead_associates(org_id, lead_id, current_user)
    if data:
        return jsonify({"msg": "Company details !", "code": 200, "data": data})
    return jsonify({"msg": "Oops,Something went wrong !", "code": 400})


@app.route('/lead_associates/<id>', methods=['GET'])
@app.route('/sales_lead_associates/<id>', methods=['GET'])
@jwt_required()
def lead_associates(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})
    return _lead_associates_response(int(org_id), id, current_user)


@app.route('/contact', methods=['POST'])
@jwt_required()
def contact_create():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request", "code": 400})

    contact_name = request.json.get('contact_name', None)
    company_id = request.json.get('company_id', None)
    phone = request.json.get('phone', None)

    if not contact_name:
        return jsonify({"msg": "Missing contact_name parameter", "code": 400})
    if not company_id:
        return jsonify({"msg": "Missing company_id parameter", "code": 400})
    if not phone:
        return jsonify({"msg": "Missing phone parameter", "code": 400})

    data1 = json.loads(json_util.dumps(request.json))
    response1 = MongoAPI.contactSubmit(int(org_id), current_user, data1)
    if not response1 or response1 == '0':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    data1['_id'] = response1
    return jsonify({
        "msg": "Contact successfully created !",
        "code": 200,
        "data": json.loads(json_util.dumps(data1)),
    })


@app.route('/contact/<id>', methods=['GET', 'PUT'])
@jwt_required()
def contact_detail(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if request.method == 'GET':
        response1 = MongoAPI.get_contact_Details(int(org_id), id, current_user)
        response = Uid.fix_array3(response1)
        if response:
            return jsonify({"msg": "Contact details !", "code": 200, "data": response})
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request", "code": 400})

    contact_name = request.json.get('contact_name', None)
    company_id = request.json.get('company_id', None)
    phone = request.json.get('phone', None)

    if not contact_name:
        return jsonify({"msg": "Missing contact_name parameter", "code": 400})
    if not company_id:
        return jsonify({"msg": "Missing company_id parameter", "code": 400})
    if not phone:
        return jsonify({"msg": "Missing phone parameter", "code": 400})

    data1 = json.loads(json_util.dumps(request.json))
    response1 = MongoAPI.contact_update(int(org_id), current_user, data1, id)
    if not response1 or response1 == '0':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    return jsonify({
        "msg": "Contact successfully Updated !",
        "code": 200,
        "data": json.loads(json_util.dumps(data1)),
    })




@app.route('/notes/<id>', methods=['PUT'])
@jwt_required()
def notes_edit(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.is_json:
            return jsonify({"msg": "Missing JSON in request"})
        note =  request.json.get('note', None)
        amount =  request.json.get('amount', None)

        if not note:
            return jsonify({"msg": "Missing note parameter","code": 400})

        org_id = int(ordId)

        data1 = json.loads(json_util.dumps(request.json))
        data = data1
        response1 = MongoAPI.notesedit(org_id,note,id)
        response = json.loads(json_util.dumps(response1))

    if response:
        return jsonify({"msg": "Opportunity successfully Updated !","code": 200,"data": data})
    else:
        return jsonify({"msg": "Oops,Somssething went wrong !","code": 400})




@app.route('/notes', methods=['GET'])
@jwt_required()
def getNotes():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.args.get:
            return jsonify({"msg": "Missing JSON in request"})

        id =  request.args.get('associate_id', None)
        associate_to =  request.args.get('associate_to', None)

        if not id:
            return jsonify({"msg": "Missing associate id parameter","code": 400})
        if not associate_to:
            return jsonify({"msg": "Missing associate to parameter","code": 400})

        data1 = json.loads(json_util.dumps(request.json))

        data = data1

        org_id = int(ordId)

        if org_id:
            response1 = MongoAPI.getNotes(org_id,current_user,ObjectId(id),associate_to)
            response = json.loads(json_util.dumps(response1))
            # response = response1.to_json()
            # print (response)
            data = {'notes':response}
            # print('time')
            # print(datetime.datetime.utcnow())
            if data:
                # print (response)
                return jsonify({"msg": "Notes list","code": 200,"data": data})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})


@app.route('/addleadsettings', methods=['POST'])
@jwt_required()
def addleadsettings():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    field_type = request.json.get('type', None)
    name = request.json.get('name', None)
    info = request.json.get('info', '')
    default = int(request.json.get('default', 0) or 0)
    color = request.json.get('color', '')
    weightage = request.json.get('weightage', '')

    if not field_type:
        return jsonify({'msg': 'Missing type parameter', 'code': 400})
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})
    if field_type not in MongoAPI.LEAD_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    check = MongoAPI.checkSettings(field_type, name, org_id)
    if check == 'No':
        count = MongoAPI.fieldsSettingsCount(field_type, org_id)
        response = MongoAPI.addleadsettings(
            field_type, name, info, org_id, count, default, color, weightage,
        )
        if response:
            return jsonify({'msg': 'Settings successfully created !', 'code': 200, 'data': response})
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
    return jsonify({'msg': 'Settings name already exists !', 'code': 400})


@app.route('/lead_settings_list', methods=['GET'])
@jwt_required()
def lead_settings_list():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    lead_status_data = MongoAPI.settingsData('lead_status', org_id)
    customer_type_data = MongoAPI.settingsData('customer_type', org_id)
    customer_requirement_data = MongoAPI.settingsData('customer_requirement', org_id)
    source_data = MongoAPI.settingsData('source', org_id)
    payment_data = MongoAPI.settingsData('payment', org_id)
    payment_terms_data = MongoAPI.settingsData('payment_terms', org_id)

    data = {
        'lead_status': Uid.fix_array(lead_status_data),
        'customer_type': Uid.fix_array(customer_type_data),
        'customer_requirement': Uid.fix_array(customer_requirement_data),
        'source': Uid.fix_array(source_data),
        'payment': Uid.fix_array(payment_data),
        'payment_terms': Uid.fix_array(payment_terms_data),
    }
    return jsonify({'msg': 'Lead settings list', 'code': 200, 'data': data})


@app.route('/lead_settings/<field_type>', methods=['GET'])
@jwt_required()
def leadsettings_by_type(field_type):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
    if field_type not in MongoAPI.LEAD_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    settings = MongoAPI.settingsData(field_type, org_id)
    return jsonify({
        'msg': 'Lead settings list',
        'code': 200,
        'data': Uid.fix_array(settings),
    })


@app.route('/updateleadsettings/<id>', methods=['PUT'])
@jwt_required()
def updateleadsettings(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    field_type = request.json.get('type', None)
    name = request.json.get('name', None)
    info = request.json.get('info', '')
    default = int(request.json.get('default', 0) or 0)
    color = request.json.get('color', '')
    weightage = request.json.get('weightage', '')

    if not field_type:
        return jsonify({'msg': 'Missing type parameter', 'code': 400})
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})
    if field_type not in MongoAPI.LEAD_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    response = MongoAPI.updateleadsettings(
        org_id, name, id, field_type, default, info, color, weightage,
    )
    if response:
        return jsonify({'msg': 'Settings successfully updated !', 'code': 200, 'data': response})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/leadsettings/<id>', methods=['DELETE'])
@jwt_required()
def deleteleadsettings(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    response = MongoAPI.deleteleadSettings(id, org_id)
    if response == 'Yes':
        return jsonify({'msg': 'Settings successfully deleted !', 'code': 200})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/leadsettings_default/<id>', methods=['PUT'])
@jwt_required()
def leadsettings_default(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    field_type = request.json.get('type', None)
    if not field_type:
        return jsonify({'msg': 'Missing type parameter', 'code': 400})
    if field_type not in MongoAPI.LEAD_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    response = MongoAPI.lead_settingsDefault(field_type, org_id, id)
    if response and response != '0':
        return jsonify({'msg': 'Default settings updated !', 'code': 200, 'data': {'id': response}})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/addprojectsettings', methods=['POST'])
@jwt_required()
def addprojectsettings():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    field_type = request.json.get('type', None)
    name = (request.json.get('name', None) or '').strip()
    info = request.json.get('info', '')
    default = int(request.json.get('default', 0) or 0)
    color = request.json.get('color', '')
    weightage = request.json.get('weightage', '')
    title = request.json.get('title', '')

    if not field_type:
        return jsonify({'msg': 'Missing type parameter', 'code': 400})
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})
    if field_type not in MongoAPI.PROJECT_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    check = MongoAPI.checkSettings(field_type, name, org_id)
    if check == 'No':
        count = MongoAPI.fieldsSettingsCount(field_type, org_id)
        response = MongoAPI.addprojectsettings(
            field_type, name, info, org_id, count, default, color, weightage, title,
        )
        if response:
            return jsonify({'msg': 'Settings successfully created !', 'code': 200, 'data': response})
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
    return jsonify({'msg': 'Settings name already exists !', 'code': 400})


@app.route('/project_settings_list', methods=['GET'])
@jwt_required()
def project_settings_list():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    data = {
        field_type: Uid.fix_array(MongoAPI.settingsData(field_type, org_id))
        for field_type in MongoAPI.PROJECT_SETTINGS_TYPES
    }
    return jsonify({'msg': 'Project settings list', 'code': 200, 'data': data})


@app.route('/project_settings/<field_type>', methods=['GET'])
@jwt_required()
def projectsettings_by_type(field_type):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
    if field_type not in MongoAPI.PROJECT_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    settings = MongoAPI.settingsData(field_type, org_id)
    return jsonify({
        'msg': 'Project settings list',
        'code': 200,
        'data': Uid.fix_array(settings),
    })


@app.route('/updateprojectsettings/<id>', methods=['PUT'])
@jwt_required()
def updateprojectsettings(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    field_type = request.json.get('type', None)
    name = (request.json.get('name', None) or '').strip()
    info = request.json.get('info', '')
    default = int(request.json.get('default', 0) or 0)
    color = request.json.get('color', '')
    weightage = request.json.get('weightage', '')
    title = request.json.get('title', None)

    if not field_type:
        return jsonify({'msg': 'Missing type parameter', 'code': 400})
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})
    if field_type not in MongoAPI.PROJECT_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    response = MongoAPI.updateprojectsettings(
        org_id, name, id, field_type, default, info, color, weightage, title,
    )
    if response:
        return jsonify({'msg': 'Settings successfully updated !', 'code': 200, 'data': response})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/projectsettings/<id>', methods=['DELETE'])
@jwt_required()
def deleteprojectsettings(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    field_type = request.args.get('type')
    response = MongoAPI.deleteleadSettings(id, org_id, field_type)
    if response == 'Yes':
        return jsonify({'msg': 'Settings successfully deleted !', 'code': 200})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


@app.route('/projectsettings_default/<id>', methods=['PUT'])
@jwt_required()
def projectsettings_default(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    field_type = request.json.get('type', None)
    if not field_type:
        return jsonify({'msg': 'Missing type parameter', 'code': 400})
    if field_type not in MongoAPI.PROJECT_SETTINGS_TYPES:
        return jsonify({'msg': 'Invalid type parameter', 'code': 400})

    response = MongoAPI.lead_settingsDefault(field_type, org_id, id)
    if response and response != '0':
        return jsonify({'msg': 'Default settings updated !', 'code': 200, 'data': {'id': response}})
    return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


LEAD_COLUMN_KEYS = [
    'lead_no',
    'name',
    'company_name',
    'phone',
    'email',
    'lead_status_name',
    'customer_type_name',
    'customer_requirement_name',
    'current_staying',
    'source_name',
    'assigned_to',
    'description',
    'project_name',
    'location',
    'designation',
    'url',
    'address1',
    'city',
    'state',
    'stage',
    'country',
    'pincode',
    'create_date',
    'date_aging',
    'target_date',
    'lead_type',
]


@app.route('/sales_leadColumnList', methods=['GET'])
@jwt_required()
def sales_leadColumnList():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    column_keys = list(LEAD_COLUMN_KEYS)
    selected_column_detail = MongoAPI.Column_customize_detail_user(org_id, current_user)
    selected_column_detail = Uid.fix_array3(selected_column_detail)

    return jsonify({
        'msg': 'Column Keys',
        'code': 200,
        'column_keys': column_keys,
        'selected_Coloumn_detail': selected_column_detail,
    })


@app.route('/column_customize', methods=['POST'])
@jwt_required()
def column_customize():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)
    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data1 = request.json or {}
    check = MongoAPI.Column_customize_Check(org_id, current_user)
    if check == 'No':
        response = MongoAPI.Column_customize_Submit(org_id, current_user, data1)
    else:
        detail = Uid.fix_array3(MongoAPI.Column_customize_detail_user(org_id, current_user))
        record_id = detail.get('_id')
        if not record_id:
            return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
        response = MongoAPI.Column_customize_update(org_id, current_user, data1, record_id)

    if not response:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})


    return jsonify({
        'msg': 'customfields_value successfully created !',
        'code': 200,
        'data': Uid.fix_array3(response),
    })


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@app.route('/usersList', methods=['GET'])
@jwt_required()
def users_list():
    current_user, user, org_id, error = require_user_management()
    if error:
        return error

    sort = request.args.get('sort', 'create_date') or 'create_date'
    order_str = request.args.get('order', 'desc') or 'desc'
    order = -1 if order_str.lower() == 'desc' else 1
    search = request.args.get('search', '') or ''
    status = request.args.get('status') or None

    users = MongoAPI.users_list(
        org_id, search=search, sort=sort, order=order, status=status, actor=user,
    )
    return jsonify({
        'code': 200,
        'msg': 'Users list',
        'data': users,
        'total_count': len(users),
    })


@app.route('/addUser', methods=['POST'])
@jwt_required()
def add_user():
    current_user, user, org_id, error = require_user_management()
    if error:
        return error

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data = request.json or {}
    name = data.get('name')
    email = data.get('email')
    if not name:
        return jsonify({'msg': 'Missing name parameter', 'code': 400})
    if not email:
        return jsonify({'msg': 'Missing email parameter', 'code': 400})

    if not data.get('password'):
        data['password'] = encode_password(os.urandom(8).hex())

    result = MongoAPI.add_user(org_id, data, current_user, actor=user)
    if result == 'missing_email':
        return jsonify({'msg': 'Missing email parameter', 'code': 400})
    if result == 'email_exists':
        return jsonify({'msg': 'Email id is already registered', 'code': 400})
    if isinstance(result, str) and result not in ('0',) and len(result) != 24:
        return jsonify({'msg': result, 'code': 403})
    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    user_data = MongoAPI.getUserDetails(org_id, result)
    return jsonify({
        'code': 200,
        'msg': 'User successfully created !',
        'data': user_data,
    })


@app.route('/userUpdate/<id>', methods=['PUT'])
@jwt_required()
def user_update(id):
    current_user, user, org_id, error = require_user_management()
    if error:
        return error

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data = request.json or {}
    result = MongoAPI.user_update(org_id, id, data, actor=user)
    if result == 'email_exists':
        return jsonify({'msg': 'Email id is already registered', 'code': 400})
    if isinstance(result, str) and result not in ('0',) and len(result) != 24:
        return jsonify({'msg': result, 'code': 403})
    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    user_data = MongoAPI.getUserDetails(org_id, id)
    return jsonify({
        'code': 200,
        'msg': 'User successfully updated !',
        'data': user_data,
    })


@app.route('/userChangeStatus/<id>', methods=['PUT'])
@jwt_required()
def user_change_status(id):
    current_user, user, org_id, error = require_user_management()
    if error:
        return error

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    status = (request.json or {}).get('status')
    if status not in ('active', 'inactive'):
        return jsonify({'msg': 'Invalid status. Use active or inactive', 'code': 400})

    if str(id) == str(current_user) and status == 'inactive':
        return jsonify({'msg': 'You cannot deactivate your own account', 'code': 400})

    result = MongoAPI.user_change_status(org_id, id, status, actor=user)
    if result == 'invalid_status':
        return jsonify({'msg': 'Invalid status', 'code': 400})
    if result == 'forbidden':
        return jsonify({'msg': 'You cannot manage this user', 'code': 403})
    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    return jsonify({
        'code': 200,
        'msg': f'User successfully {status}',
        'data': {'_id': id, 'status': status},
    })


@app.route('/roles', methods=['GET', 'POST'])
@jwt_required()
def roles():
    current_user, user, org_id, error = require_manage_settings()
    if error:
        return error

    if request.method == 'GET':
        items = MongoAPI.roles_list(org_id)
        return jsonify({
            'code': 200,
            'msg': 'Roles list',
            'data': {'items': items},
        })

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    role_name = (request.json or {}).get('role_name')
    if not role_name:
        return jsonify({'msg': 'Missing role_name parameter', 'code': 400})

    result = MongoAPI.role_create(org_id, current_user, role_name)
    if result == 'missing_name':
        return jsonify({'msg': 'Missing role_name parameter', 'code': 400})
    if result == 'duplicate':
        return jsonify({'msg': 'Role name already exists', 'code': 400})
    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    role_data = MongoAPI.getRolesListDetails(org_id, result)
    return jsonify({
        'code': 200,
        'msg': 'Role successfully created !',
        'data': Uid.fix_array_role(role_data),
    })


@app.route('/roles/<role_id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def role_detail(role_id):
    current_user, user, org_id, error = require_manage_settings()
    if error:
        return error

    if request.method == 'GET':
        role_data = MongoAPI.getRolesListDetails(org_id, role_id)
        if not role_data:
            return jsonify({'msg': 'Role not found', 'code': 404}), 404
        return jsonify({
            'code': 200,
            'msg': 'Role details',
            'data': Uid.fix_array_role(role_data),
        })

    if request.method == 'DELETE':
        result = MongoAPI.role_delete(org_id, role_id)
        if result == 'protected':
            return jsonify({'msg': 'Administrator role cannot be deleted', 'code': 400})
        if result == 'in_use':
            return jsonify({'msg': 'Role is assigned to users and cannot be deleted', 'code': 400})
        if not result or result == '0':
            return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})
        return jsonify({'code': 200, 'msg': 'Role successfully deleted !'})

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data = request.json or {}
    result = MongoAPI.role_update(org_id, role_id, data, actor_user_id=current_user)
    if result == 'duplicate':
        return jsonify({'msg': 'Role name already exists', 'code': 400})
    if isinstance(result, str) and result not in ('0',) and len(result) != 24:
        return jsonify({'msg': result, 'code': 403})
    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    role_data = MongoAPI.getRolesListDetails(org_id, role_id)
    return jsonify({
        'code': 200,
        'msg': 'Role successfully updated !',
        'data': Uid.fix_array_role(role_data),
    })


# ---------------------------------------------------------------------------
# Branch Management
# ---------------------------------------------------------------------------

@app.route('/branch_list', methods=['GET'])
@jwt_required()
def branch_list():
    current_user, user, error = require_authenticated_user()
    if error:
        return error

    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    branches = MongoAPI.branch_list(org_id, actor=user)
    return jsonify({
        'code': 200,
        'msg': 'Branches list',
        'data': branches,
    })


@app.route('/add_branch', methods=['POST'])
@jwt_required()
def add_branch():
    current_user, user, org_id, error = require_branch_management()
    if error:
        return error

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data = request.json or {}
    result = MongoAPI.branch_create(org_id, data)
    if result == 'missing_name':
        return jsonify({'msg': 'Missing name parameter', 'code': 400})
    if result == 'missing_code':
        return jsonify({'msg': 'Missing code parameter', 'code': 400})
    if result in ('duplicate_code', 'duplicate_id'):
        return jsonify({'msg': 'Branch code already exists', 'code': 400})
    if result == 'invalid_id':
        return jsonify({'msg': 'Invalid branch_id', 'code': 400})
    if not result or result == '0':
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    branch_data = next(
        (item for item in MongoAPI.branch_list(org_id) if item.get('id') == result),
        {'id': result},
    )
    return jsonify({
        'code': 200,
        'msg': 'Branch successfully created !',
        'data': branch_data,
    })


@app.route('/branch_edit/<branch_id>', methods=['PUT'])
@jwt_required()
def branch_edit(branch_id):
    current_user, user, org_id, error = require_branch_management()
    if error:
        return error

    if not request.is_json:
        return jsonify({'msg': 'Missing JSON in request', 'code': 400})

    data = request.json or {}
    result = MongoAPI.branch_update(org_id, branch_id, data)
    if result == 'duplicate_code':
        return jsonify({'msg': 'Branch code already exists', 'code': 400})
    if not result or result == '0':
        return jsonify({'msg': 'Branch not found', 'code': 404})

    branch_data = next(
        (item for item in MongoAPI.branch_list(org_id) if item.get('id') == result),
        {'id': result},
    )
    return jsonify({
        'code': 200,
        'msg': 'Branch successfully updated !',
        'data': branch_data,
    })


@app.route('/branch_delete/<branch_id>', methods=['PUT', 'DELETE'])
@jwt_required()
def branch_delete(branch_id):
    current_user, user, org_id, error = require_branch_management()
    if error:
        return error

    result = MongoAPI.branch_deactivate(org_id, branch_id)
    if not result or result == '0':
        return jsonify({'msg': 'Branch not found', 'code': 404})

    return jsonify({
        'code': 200,
        'msg': 'Branch successfully deactivated',
        'data': {'id': result, 'status': 'inactive'},
    })


@app.route('/user_permissions', methods=['GET'])
@jwt_required()
def user_permissions():
    current_user, user, error = require_authenticated_user()
    if error:
        return error

    org_id = user.get('org_id')
    role_data = build_role_data(org_id, current_user)
    plan_data = MongoAPI.get_plan_data(org_id)

    return jsonify({
        'code': 200,
        'msg': 'User permissions',
        'data': {
            'roleData': role_data,
            'planData': plan_data,
        },
    })


@app.route('/active_users_list', methods=['GET'])
@jwt_required()
def active_users_list():
    current_user, user, error = require_authenticated_user()
    if error:
        return error

    org_id = user.get('org_id')
    users = MongoAPI.active_users_list(org_id)
    return jsonify({
        'code': 200,
        'msg': 'Active users list',
        'data': users,
    })


@app.route('/crm_tasks', methods=['POST'])
@jwt_required()
def crm_tasks_submit():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]

    if ordId == '':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request"})

    associate_id = request.json.get('associate_id', None)
    associate_to = request.json.get('associate_to', None)
    description = request.json.get('description', None)
    new_task_type = request.json.get('new_task_type', None)
    time = request.json.get('time', None)
    date = request.json.get('date', None)
    assigned_to = request.json.get('assigned_to', None)

    if not associate_id:
        return jsonify({"msg": "Missing associate_id parameter", "code": 400})
    if not associate_to:
        return jsonify({"msg": "Missing associate_to parameter", "code": 400})
    if not description:
        return jsonify({"msg": "Missing description parameter", "code": 400})
    if not new_task_type:
        return jsonify({"msg": "Missing new_task_type parameter", "code": 400})
    if not time:
        return jsonify({"msg": "Missing time parameter", "code": 400})
    if not date:
        return jsonify({"msg": "Missing date parameter", "code": 400})
    if not assigned_to:
        return jsonify({"msg": "Missing assigned_to parameter", "code": 400})

    org_id = int(ordId)
    payload = request.json
    data1 = json.loads(json_util.dumps(payload))

    module_key = ''
    if isinstance(associate_to, str):
        module_key = associate_to.strip().lower().replace(' ', '_')
        data1['associate_to'] = module_key

    data = data1
    response1 = MongoAPI.crm_tasks_Submit(org_id, current_user, data1)
    response = json.loads(json_util.dumps(response1))
    display_date = datetime.datetime.strptime(date, '%Y-%m-%d').strftime('%d/%m/%Y')

    if not response or response == '0':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    def normalize_id(value):
        if isinstance(value, dict):
            return value.get('$oid') or value.get('oid') or ''
        return str(value) if value else ''

    def get_module_email_context(module, assoc_id):
        assoc_id_str = normalize_id(assoc_id)
        subject_prefix = module.replace('_', ' ').title() if module else 'Task'
        display_name = ''
        detail_url = _client_app_url()
        template_company_id = assoc_id_str

        try:
            if module == 'lead':
                lead_detail = MongoAPI.get_lead_Details(ordId, assoc_id, current_user)
                if isinstance(lead_detail, list):
                    lead_detail = lead_detail[0] if lead_detail else {}
                display_name = lead_detail.get("name", '')
                detail_url = _client_app_url(f'lead_detail/{assoc_id_str}')
            else:
                return None
        except Exception as exc:
            print(f"Error preparing CRM task email context for module {module}: {exc}")
            return None

        if not display_name:
            display_name = subject_prefix

        subject = f"{subject_prefix} Task Reminder"
        return {
            'subject': subject,
            'display_name': display_name,
            'detail_url': detail_url or _client_app_url(),
            'template_company_id': template_company_id or assoc_id_str,
        }

    email_context = get_module_email_context(module_key, associate_id)
    user_details = MongoAPI.getUserDetails(ordId, assigned_to)
    email = user_details.get("email")
    user_id = user_details.get("user_id")
    user_details = Uid.fix_array5(user_details)

    logo = _backend_logo_url()

    if email_context:
        sales_task_reminder = render_template(
            'curace/sales_task_reminder.html',
            task_title=description,
            company_name=email_context.get('display_name', ''),
            date=display_date,
            time=time,
            company_id=email_context.get('template_company_id', ''),
            logo=logo,
            company_detail_url=email_context.get('detail_url', _client_app_url()),
        )
    else:
        sales_task_reminder = None

    if assigned_to != current_user and email_context and email and sales_task_reminder:
        email_payload = defaultdict(list)
        email_payload['subject'] = email_context.get('subject', 'Task Reminder')
        email_payload['content'] = sales_task_reminder
        email_payload['to'] = email
        email_payload['cc'] = ''
        email_payload['bcc'] = ''
        email_payload['associate_id'] = user_id
        email_payload['associate_to'] = 'signup'
        attachment = ''
        emailId = 'info@farazon.com'
        MongoAPI.emailSubmit(org_id, user_id, email_payload, emailId, attachment)

    return jsonify({"msg": "followp_task successfully created !", "code": 200, "data": data})


@app.route('/crm_tasks/<id>', methods=['PUT'])
@jwt_required()
def crm_tasks_update(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]

    if ordId == '':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request"})

    associate_id = request.json.get('associate_id', None)
    associate_to = request.json.get('associate_to', None)
    description = request.json.get('description', None)
    new_task_type = request.json.get('new_task_type', None)
    time = request.json.get('time', None)
    date = request.json.get('date', None)
    assigned_to = request.json.get('assigned_to', None)

    if not associate_id:
        return jsonify({"msg": "Missing associate_id parameter", "code": 400})
    if not associate_to:
        return jsonify({"msg": "Missing associate_to parameter", "code": 400})
    if not description:
        return jsonify({"msg": "Missing description parameter", "code": 400})
    if not new_task_type:
        return jsonify({"msg": "Missing new_task_type parameter", "code": 400})
    if not time:
        return jsonify({"msg": "Missing time parameter", "code": 400})
    if not date:
        return jsonify({"msg": "Missing date parameter", "code": 400})
    if not assigned_to:
        return jsonify({"msg": "Missing assigned_to parameter", "code": 400})

    org_id = int(ordId)
    data1 = json.loads(json_util.dumps(request.json))
    data = data1
    response1 = MongoAPI.crm_tasks_update(org_id, current_user, data1, id)
    response = json.loads(json_util.dumps(response1))

    if response and response != '0':
        return jsonify({"msg": "Followp Task successfully Updated !", "code": 200, "data": data})
    return jsonify({"msg": "Oops,Something went wrong !", "code": 400})


@app.route('/crm_tasks/<id>', methods=['GET'])
@jwt_required()
def crm_tasks_detail(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]

    if ordId == '':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    response1 = MongoAPI.crm_tasks_detail(ordId, current_user, id)
    response = Uid.fix_array3(response1)
    data = response

    if data:
        return jsonify({"msg": "Task details !", "code": 200, "data": data})
    return jsonify({"msg": "Oops,Something went wrong !", "code": 400})


@app.route('/task_calender', methods=['GET'])
@jwt_required()
def task_calender():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]

    if ordId == '':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    page = request.args.get('page', None)
    length = request.args.get('length', None)
    date_from = request.args.get('date_from', None)
    date_to = request.args.get('date_to', None)
    owner = request.args.get('owner', None)
    status = request.args.get('status', None)

    if page:
        page = int(page)
    if length:
        length = int(length)

    org_id = int(ordId)

    task = MongoAPI.task_calender(org_id, current_user, length, page, date_from, date_to)
    task = json.loads(json_util.dumps(task))
    task = Uid.fix_array(task)

    sub_task = MongoAPI.subtask_calender(org_id, current_user, date_from, date_to)
    sub_task = json.loads(json_util.dumps(sub_task))
    sub_task = Uid.fix_array(sub_task)

    all_crm_tasks = MongoAPI.all_crm_tasks_calender(
        org_id, current_user, date_from, date_to, owner, status,
    )
    all_crm_tasks = json.loads(json_util.dumps(all_crm_tasks))
    all_crm_tasks = Uid.fix_array(all_crm_tasks)

    total_count = MongoAPI.gettask_count(org_id)
    combined_response = task + sub_task + all_crm_tasks

    return jsonify({
        "code": 200,
        "data": combined_response,
        "total_count": total_count,
    })


@app.route('/tasks_completed/<id>', methods=['PUT'])
@jwt_required()
def crm_tasks_completed(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]

    if ordId == '':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request"})

    note = request.json.get('note', None)
    associate_id = request.json.get('associate_id', None)
    associate_to = request.json.get('associate_to', None)
    in_time = request.json.get('in_time', '')
    out_time = request.json.get('out_time', '')

    org_id = int(ordId)
    data = {
        "note": note,
        "associate_id": associate_id,
        "associate_to": associate_to,
    }

    response1 = MongoAPI.crm_tasks_status_update(org_id, 'Completed', id, in_time, out_time)
    if response1 == 1 and note:
        if not associate_id:
            return jsonify({"msg": "Missing associate id parameter", "code": 400})
        if not associate_to:
            return jsonify({"msg": "Missing associate to parameter", "code": 400})

        notes_data = MongoAPI.noteSubmit(org_id, current_user, data)
        if notes_data:
            MongoAPI.crm_tasks_note_id_update(org_id, id, notes_data)

    response = json.loads(json_util.dumps(response1))

    if response:
        return jsonify({"msg": "Followp Task successfully Updated !", "code": 200})
    return jsonify({"msg": "Oops,Something went wrong !", "code": 400})


@app.route('/countries', methods=['GET'])
@jwt_required()
def get_countries():
    current_user, user, error = require_authenticated_user()
    if error:
        return error

    countries = MongoAPI.get_countries()
    return jsonify({
        'code': 200,
        'msg': 'Countries list',
        'data': countries,
    })


@app.route('/statesName/<country_name>', methods=['GET'])
@jwt_required()
def get_states_by_country(country_name):
    current_user, user, error = require_authenticated_user()
    if error:
        return error

    decoded_country = unquote(country_name or '').strip()
    states = MongoAPI.get_states_by_country(decoded_country)
    return jsonify({
        'code': 200,
        'msg': 'States list',
        'data': states,
    })




 
@app.route('/users_gmailList', methods=['GET'])
@jwt_required()
def users_gmailList():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2 == 'org_id':
            ordId = user[user2]
    if ordId == '':
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})
    else:
        org_id=int(ordId)
        users1 = MongoAPI.users_gmaillist(org_id,current_user)
        users = Uid.fix_array(users1)
        # print (users)
        if users1:
            return jsonify({"msg": "Gmail List","code": 200,"data": users})
        else:
            return jsonify({"msg": "No Gmail List","code": 400})




@app.route('/mail_signature_get', methods=['GET'])
@jwt_required()
def getmail_signature():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = int(user[user2])

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if ordId:
            response1 = MongoAPI.getmail_signature(ordId)
            response = Uid.fix_array(response1)
            # data = {'template':response}

            if response:
                return jsonify({"msg": "Mail Signature!","code": 200,"data": response})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})



###### email template ######
@app.route('/emailTemplate', methods=['POST'])
@jwt_required()
def emailTemplate():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId =int(user[user2])

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.is_json:
            return jsonify({"msg": "Missing JSON in request"})
        name =  request.json.get('name', None)
        default = 0
        default =  request.json.get('default', default)
        template =  request.json.get('template', None)
        subject =  request.json.get('subject', None)


        if not name:
            return jsonify({"msg": "Missing user field name parameter","code": 400})
        if not template:
            return jsonify({"msg": "Missing template parameter","code": 400})
        if not subject:
            return jsonify({"msg": "Missing subject parameter","code": 400})

        org_id = int(ordId)

        check = MongoAPI.checkEmailTemplate(name,org_id)
        if check=='No':
            count = MongoAPI.emailTemplateCount(org_id)

            data1 = json.loads(json_util.dumps(request.json))

            response = MongoAPI.addEmailTemplate(name,template,subject,org_id,count,default)
            response1 = json.loads(json_util.dumps(response))

            if response:
                return jsonify({"msg": "Email template add successfully","code": 200,"response": response1})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})
        else:
            return jsonify({"msg": "Email template is already add","code": 400})


@app.route('/emailTemplate', methods=['GET'])
@jwt_required()
def getEmailTemplates():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = int(user[user2])

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if ordId:
            response1 = MongoAPI.getEmailTemplates(ordId)
            response = Uid.fix_array(response1)
            data = {'template':response}

            if data:
                return jsonify({"msg": "Email template list!","code": 200,"data": data})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})


@app.route('/emailTemplate/<id>', methods=['GET'])
@jwt_required()
def getEmailTemplate(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = int(user[user2])

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if ordId:
            response1 = MongoAPI.getEmailTemplateDetails(ordId,id)
            response = Uid.fix_array3(response1)
            data = {'template':response}

            if data:
                return jsonify({"msg": "Email template details!","code": 200,"data": data})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})


@app.route('/emailTemplate/<id>', methods=['PUT'])
@jwt_required()
def updateEmailTemplate(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId =int(user[user2])

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not request.is_json:
            return jsonify({"msg": "Missing JSON in request"})
        name =  request.json.get('name', None)
        default = 0
        default =  request.json.get('default', default)
        template =  request.json.get('template', None)
        subject =  request.json.get('subject', None)


        if not name:
            return jsonify({"msg": "Missing user field name parameter","code": 400})
        if not template:
            return jsonify({"msg": "Missing template parameter","code": 400})
        if not subject:
            return jsonify({"msg": "Missing subject parameter","code": 400})

        org_id = int(ordId)

        # check = MongoAPI.checkEmailTemplate(name,org_id)
        check='No'
        if check=='No':

            data1 = json.loads(json_util.dumps(request.json))

            id = ObjectId(id)

            response = MongoAPI.updateEmailTemplate(id,name,template,subject,org_id,default)
            response1 = json.loads(json_util.dumps(response))

            if response:
                return jsonify({"msg": "Email template update successfully","code": 200,"response": response1})
            else:
                return jsonify({"msg": "Oops,Something went wrong !","code": 400})
        else:
            return jsonify({"msg": "Email template is already update","code": 400})


@app.route('/emailTemplate/<id>', methods=['DELETE'])
@jwt_required()
def deleteEmailTemplate(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:

        org_id = int(ordId)
        id = ObjectId(id)

        response = MongoAPI.deleteEmailTemplate(id)
        response1 = json.loads(json_util.dumps(response))

        if response:
            return jsonify({"msg": "Email template delete successfully","code": 200,"response": response1})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})



@app.route('/emailTemplateDefault/<id>', methods=['GET'])
@jwt_required()
def emailTemplateDefault(id):
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        if not id:
            return jsonify({"msg": "Missing id parameter","code": 400})


        org_id = int(ordId)
        response = MongoAPI.emailTemplateDefault(org_id, id)
        response1 = json.loads(json_util.dumps(response))
        if response:
            return jsonify({"msg": "Default set successfully","code": 200,"response": response1})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})




@app.route('/history', methods=['GET'])
@jwt_required()
def gethistory():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)


    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]

    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 400})
    else:
        org_id = int(ordId)

        order =  request.args.get('order', None)
        sort =  request.args.get('sort', None)

        if not order:
            order=''
        if not sort:
            sort=''

        if order=='desc':
            order=-1
        elif order=='asc':
            order=1
        else:
            order=-1

        if sort:
            sort=sort
        else:
            sort='create_date'


        history = MongoAPI.gethistory(org_id,current_user,'email_template',sort,order)
        data = Uid.fix_array(history)

        if data:
            return jsonify({"msg": "Template History Details !","code": 200,"data": data})
        else:
            return jsonify({"msg": "Oops,Something went wrong !","code": 400})



@app.route('/emailDocuments', methods=['POST'])
@jwt_required()
def emailDocuments():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ordId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]
    if request.method == 'POST':

        if 'document[]' not in request.files:
            resp = jsonify({'msg' : 'No file part in the request','code':'400'})
            return resp
        else:
            filenameData = []
            files = request.files.getlist('document[]')
            for file in files:
                if file and allowed_file(file.filename,app_config.ALLOWED_EXTENSIONS):
                    filename = secure_filename(file.filename)
                    file_type = file.filename
                    file_format = splitpart(file_type,-1,'.')
                    file_name = splitpart(file_type,0,'.')
                    filename1 = file_name + time.strftime('_%d_%Y_%H_%M_%S') +'.'+file_format
                    file.save(os.path.join(app.config['UPLOAD_EMAIL_FOLDER'], filename1))
                    this_file={
                        'name':filename,
                        'url':os.path.join(str(app_config.BASE_URL),app.config['UPLOAD_EMAIL_FOLDER'], filename1)
                    }
                    filenameData.append(this_file)
            return jsonify({"msg": "File(s) Added","code": 200,"filelist":filenameData})

    else:
        return jsonify({"msg": "Invalid method for input","code": 400})



@app.route('/folderList', methods=['GET'])
@jwt_required()
def getfolderlist():
    current_user = get_jwt_identity()
    # print (current_user)
    user = MongoAPI.authorizationCheck(current_user)
    ordId = ''
    userId = ''
    for user2 in user:
        if user2=='org_id':
            ordId = user[user2]
        elif user2=='_id':
            userId = user[user2]
    if ordId=='':
        return jsonify({"msg": "Oops,Something went wrong !","code": 600})
    else:
        page =  request.args.get('page', None)
        length =  request.args.get('length', None)
        search =  request.args.get('search', None)
        sort =  request.args.get('sort', None)
        order =  request.args.get('order', None)
        folder_id = request.args.get('folder_id', None) or request.args.get('folder_name', None)


        if not page:
            page=1
        if not length:
            length=10
        if not search:
            search=''

        if not order:
            order=''
        if not sort:
            sort=''

        if order=='desc':
            order=-1
        elif order=='asc':
            order=1
        else:
            order=1

        if sort=='folder_name':
            sort='folder_name'
        elif sort:
            sort=sort
        else:
            sort='folder_name'

        length = int(length)
        page = int(page)

        response = MongoAPI.getfolderlist(ordId, length, page, search, sort, order, folder_id)
        response1 = json.loads(json_util.dumps(response))
        response1 = Uid.fix_array(response1)
        count = len(response1)
        data = {'total_count': count, 'items': response1}
        return jsonify({"msg": "Folder list", "code": 200, "data": data, **data})


@app.route('/single_email', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True)
def single_email():
    if request.method == 'OPTIONS':
        return '', 204

    current_user = get_jwt_identity()
    if not current_user:
        return jsonify({'msg': 'Authorization token is missing', 'code': 401}), 401

    user = MongoAPI.authorizationCheck(current_user)
    if not user:
        return jsonify({'msg': 'Invalid user', 'code': 401}), 401

    org_id = user.get('org_id')
    if not org_id:
        return jsonify({'msg': 'Oops,Something went wrong !', 'code': 400})

    from_email = request.form.get('fromEmail', '').strip()
    subject = request.form.get('subject', '').strip()
    content = request.form.get('content', '').strip()
    to = request.form.get('to', '').strip()
    cc = request.form.get('cc', '').strip()
    bcc = request.form.get('bcc', '').strip()
    associate_id = request.form.get('associate_id', '').strip()
    associate_to = request.form.get('associate_to', 'lead').strip()
    attachment_list = request.form.get('attachment_list', '').strip()
    thread_id = request.form.get('thread_id', 'None')

    if not from_email:
        return jsonify({'msg': 'Missing fromEmail parameter', 'code': 400})
    if not subject:
        return jsonify({'msg': 'Missing subject parameter', 'code': 400})
    if not content:
        return jsonify({'msg': 'Missing content parameter', 'code': 400})
    if not to:
        return jsonify({'msg': 'Missing to parameter', 'code': 400})
    if not associate_id:
        return jsonify({'msg': 'Missing associate_id parameter', 'code': 400})

    content = content.replace('undefined', '').strip()

    attachment_paths = _resolve_local_attachment_paths(attachment_list)
    email_sent = send_crm_email(
        from_email=from_email,
        to=to,
        subject=subject,
        html=content,
        cc=cc,
        bcc=bcc,
        attachments=attachment_paths,
    )

    mail_data = {
        'subject': subject,
        'content': content,
        'to': to,
        'cc': cc,
        'bcc': bcc,
        'associate_id': associate_id,
        'associate_to': associate_to,
    }

    email_record_id = MongoAPI.singleEmailSubmit(
        org_id,
        current_user,
        mail_data,
        from_email,
        attachment_list,
        thread_id,
    )

    if email_record_id and email_record_id != '0':
        MongoAPI.user_activity(
            int(org_id),
            current_user,
            None,
            None,
            'email',
            'create',
            associate_to,
            ObjectId(associate_id),
            0,
            {'subject': subject, 'to': to},
            f'Email sent: {subject}',
            'Email',
        )

    if not email_sent:
        return jsonify({
            'msg': 'Email saved but delivery failed. Check MAIL_ENABLED and Gmail SMTP settings in .env',
            'code': 400,
            'email_id': email_record_id if email_record_id != '0' else None,
        })

    return jsonify({
        'msg': 'Email sent successfully',
        'code': 200,
        'email_id': email_record_id,
    })


@app.route('/document', methods=['POST'])
@jwt_required()
def document():
    current_user = get_jwt_identity()
    user = MongoAPI.authorizationCheck(current_user)

    ord_id = ''
    for key in user:
        if key == 'org_id':
            ord_id = user[key]

    if not ord_id:
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    associate_id = request.form.get('associate_id')
    associate_to = request.form.get('associate_to')

    if not associate_id:
        return jsonify({"msg": "Missing associate id parameter", "code": 400})
    if not associate_to:
        return jsonify({"msg": "Missing associate to parameter", "code": 400})

    try:
        associate_object_id = ObjectId(associate_id)
    except Exception:
        return jsonify({"msg": "Invalid associate id parameter", "code": 400})

    if 'document' not in request.files:
        return jsonify({'msg': 'No file part in the request', 'code': 400})

    file = request.files['document']

    if not file or file.filename == '':
        return jsonify({'msg': 'No file selected for uploading', 'code': 400})

    if not allowed_file(file.filename, app_config.ALLOWED_EXTENSIONS):
        return jsonify({
            "msg": f"Allowed file types are {app_config.ALLOWED_EXTENSIONS}",
            "code": 400,
        })

    original_filename = secure_filename(file.filename)
    file_format = splitpart(file.filename, -1, '.')
    file_name = splitpart(file.filename, 0, '.')
    stored_filename = (
        file_name + time.strftime('_%d_%Y_%H_%M_%S') + '.' + file_format
    )

    upload_dir = app.config['UPLOAD_DOCUMENT_FOLDER']
    file.save(os.path.join(upload_dir, stored_filename))

    document_id = MongoAPI.documentSubmit(
        ord_id,
        current_user,
        associate_id,
        associate_to,
        stored_filename,
        original_filename,
    )

    if str(document_id) == '0':
        saved_path = os.path.join(upload_dir, stored_filename)
        if os.path.exists(saved_path):
            os.remove(saved_path)
        return jsonify({"msg": "Oops,Something went wrong !", "code": 400})

    document_url = (
        f"{app_config.BASE_URL}{app_config.UPLOAD_OPEN_DOCUMENT_FOLDER}{stored_filename}"
    )
    data = {
        'document': str(document_id),
        'name': original_filename,
        'url': document_url,
    }

    return jsonify({
        "msg": "Document upload successfully !",
        "code": 200,
        "data": data,
    })





