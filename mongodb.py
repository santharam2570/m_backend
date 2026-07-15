import datetime
import json
import re
from collections import defaultdict
from datetime import timedelta

from bson import ObjectId, json_util
from bson.errors import InvalidId
from mongoengine.errors import NotUniqueError, ValidationError
from pytz import timezone

import app_config
from common_config import Uid
from datatable import LastDataId
from date_filter import DATE_FORMAT, DATE_FORMAT1, DATE_FORMAT2, DATE_FORMAT3, DATE_FORMAT4, DateFilter, calculate_age
from permissions_config import (
    ALL_ROLE_KEYS,
    DEFAULT_ADMIN_PERMISSIONS,
    DEFAULT_PLAN_DATA,
    DEFAULT_ROLE_PERMISSIONS,
    MODULE_KEYS,
    ORG_LEVEL_PERMISSIONS,
    SYSTEM_ROLE_DEFAULTS,
    SYSTEM_ROLE_NAMES,
    VIEW_SCOPE_GROUPS,
    apply_view_scope_exclusivity,
    flatten_role_permission_payload,
)
from rbac import (
    SUPER_ADMIN_IDENTITY_ERROR,
    can_manage_target_user,
    effective_tier,
    get_accessible_branch_ids,
    is_super_admin_role_name,
    is_super_admin_user,
    normalize_tier,
    validate_permission_grant,
    validate_user_tier_branch,
)
from user_details_validator import normalize_user_detail_payload
from models import (
    Admin_email,
    Branch,
    Booking,
    Column_customize,
    Contact,
    Countries,
    Crm_tasks,
    Document,
    Email,
    Email_template,
    Email_template_history,
    Fields,
    Folder,
    Gmail_tokens,
    Lead,
    Note,
    Numbering,
    Project,
    ProjectDocument,
    ProjectSiteVisit,
    ProjectUnit,
    Organization,
    Plan_wise_modules,
    RevokedToken,
    Role,
    States,
    Task,
    Team,
    User,
    User_audit,
    UserActivity,
    notifications,
)


class MongoAPI:
    _USER_BRANCH_MIGRATED_ORGS = set()

    @staticmethod
    def _parse_date_value(value):
        if value is None or value == '' or str(value).lower() == 'none':
            return None
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, dict) and '$date' in value:
            value = value['$date']
        if not isinstance(value, str):
            value = str(value)
        raw = value.rstrip('Z')
        for fmt in (DATE_FORMAT, DATE_FORMAT4, DATE_FORMAT3, DATE_FORMAT1, '%Y-%m-%d'):
            try:
                return datetime.datetime.strptime(raw, fmt)
            except ValueError:
                continue
        try:
            return datetime.datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError:
            return None

    @staticmethod
    def _format_display_date(value):
        if not value:
            return ''
        parsed = MongoAPI._parse_date_value(value)
        if parsed is not None:
            return parsed.strftime(DATE_FORMAT1)
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _user_dict(user):
        create_date = MongoAPI._format_display_date(user.create_date)
        role_tier = getattr(user, 'role_tier', None) or None
        MongoAPI._ensure_user_branch_object_id(user)
        branch_ref = getattr(user, 'branch_id', None)
        branch_id = MongoAPI._serialize_user_branch_id(user.org_id, branch_ref)
        role_name = None

        if user.role:
            try:
                role = Role.objects.get(id=user.role)
                role_name = role.role_name
                if role.role_name in ('Super Admin', 'Administrator'):
                    role_tier = 'super_admin'
            except Role.DoesNotExist:
                pass
        if not role_tier:
            role_tier = 'branch_user'

        aadhaar_number = getattr(user, 'aadhaar_number', None) or None
        aadhaar_document = getattr(user, 'aadhaar_document', None) or None
        pan_number = getattr(user, 'pan_number', None) or None
        pan_document = getattr(user, 'pan_document', None) or None
        address = getattr(user, 'address', None) or None
        source = getattr(user, 'source', None) or None
        referred_by = getattr(user, 'referred_by', None) or None
        reference_contact_number = (
            getattr(user, 'reference_contact_number', None) or None
        )
        passport_number = getattr(user, 'passport_number', None) or None
        assigned_project_ids, assigned_project_names = MongoAPI._resolve_assigned_projects(
            user.org_id,
            getattr(user, 'assigned_project_ids', None) or [],
        )

        return {
            'id': str(user.id),
            '_id': str(user.id),
            'name': user.name or '',
            'email': user.email,
            'phone': getattr(user, 'phone', '') or '',
            'create_date': create_date,
            'role': str(user.role) if user.role else None,
            'role_name': role_name,
            'org_id': user.org_id,
            'status': user.status,
            'role_tier': role_tier,
            'branch_id': branch_id,
            'profile_image': getattr(user, 'profile_image', '') or '',
            'aadhaar_number': aadhaar_number,
            'aadhaar_document': aadhaar_document,
            'pan_number': pan_number,
            'pan_document': pan_document,
            'address': address,
            'source': source,
            'referred_by': referred_by,
            'reference_contact_number': reference_contact_number,
            'passport_number': passport_number,
            'permission_overrides': dict(getattr(user, 'permission_overrides', None) or {}),
            # Frontend alias keys
            'aadhaar': aadhaar_number,
            'aadhaar_doc': aadhaar_document,
            'pan': pan_number,
            'pan_doc': pan_document,
            'referredBy': referred_by,
            'reference_contact': reference_contact_number,
            'reference_phone': reference_contact_number,
            'assigned_project_ids': assigned_project_ids,
            'assigned_project_names': assigned_project_names,
        }

    @staticmethod
    def selectLogin(email, password):
        try:
            user = User.objects.get(
                email=MongoAPI._normalize_email(email),
                password=password,
            )
            return MongoAPI._user_dict(user)
        except User.DoesNotExist:
            return 'no such name'

    @staticmethod
    def _normalize_email(email):
        return str(email or '').strip().lower()

    @staticmethod
    def get_user_by_email(email):
        try:
            user = User.objects.get(email=MongoAPI._normalize_email(email))
            return MongoAPI._user_dict(user)
        except User.DoesNotExist:
            return 'no such name'

    @staticmethod
    def get_user_password_hash(user_id):
        try:
            user = User.objects.only('password').get(id=ObjectId(user_id))
            return user.password or ''
        except (User.DoesNotExist, InvalidId):
            return ''

    @staticmethod
    def emailCheck(email):
        return MongoAPI.userCheck(email)

    @staticmethod
    def userCheck(email):
        try:
            User.objects.get(email=MongoAPI._normalize_email(email))
            return 'Yes'
        except User.DoesNotExist:
            return 'No'

    @staticmethod
    def userRoleUpdate(user_id, role_id):
        try:
            user = User.objects.get(id=ObjectId(user_id))
            target = MongoAPI._user_dict(user)
            if is_super_admin_user(target):
                admin_role_id = MongoAPI.userAdministratorRole(target.get('org_id'))
                if admin_role_id and str(role_id) != str(admin_role_id):
                    return 'protected'
            User.objects(id=ObjectId(user_id)).update_one(role=ObjectId(role_id))
            return 'Yes'
        except Exception:
            return 'No'

    @staticmethod
    def userAdministratorRole(org_id):
        for role_name in ('Super Admin', 'Administrator'):
            try:
                role = Role.objects.get(org_id=int(org_id), role_name=role_name)
                if role_name == 'Administrator' and role.role_name != 'Super Admin':
                    role.role_name = 'Super Admin'
                    role.is_system_role = 1
                    role.save()
                return str(role.id)
            except Role.DoesNotExist:
                continue
        return 0

    @staticmethod
    def roleSubmit(org_id, user_id, data):
        try:
            role_name = data['role_name']
            defaults = SYSTEM_ROLE_DEFAULTS.get(role_name, DEFAULT_ROLE_PERMISSIONS)
            role_data = {
                'org_id': org_id,
                'role_name': role_name,
                'create_by': ObjectId(user_id),
                'is_system_role': 1 if role_name in SYSTEM_ROLE_NAMES else 0,
                **defaults,
            }
            role = Role(**role_data)
            role.save()
            return str(role.id)
        except NotUniqueError:
            return '0'

    @staticmethod
    def _role_is_system(role):
        if int(getattr(role, 'is_system_role', 0) or 0) == 1:
            return True
        return role.role_name in SYSTEM_ROLE_NAMES

    @staticmethod
    def _role_permissions_from_role(role):
        # Super Admin is always treated as having every permission, even if
        # older role documents were seeded before new permission keys existed.
        if is_super_admin_role_name(getattr(role, 'role_name', None)):
            return {key: 1 for key in ALL_ROLE_KEYS}
        return {key: int(getattr(role, key, 0) or 0) for key in ALL_ROLE_KEYS}

    @staticmethod
    def _role_to_dict(role):
        data = {
            'id': str(role.id),
            'role_id': str(role.id),
            '_id': str(role.id),
            'org_id': role.org_id,
            'role_name': role.role_name,
            'is_system': MongoAPI._role_is_system(role),
        }
        data.update(MongoAPI._role_permissions_from_role(role))
        return data

    @staticmethod
    def _role_to_detail(role):
        return {
            '_id': str(role.id),
            'role_name': role.role_name,
            'org_id': role.org_id,
            'is_system': MongoAPI._role_is_system(role),
            'permissions': MongoAPI._role_permissions_from_role(role),
        }

    @staticmethod
    def _role_list_item(role, org_id):
        return {
            '_id': str(role.id),
            'role_name': role.role_name,
            'org_id': role.org_id,
            'is_system': MongoAPI._role_is_system(role),
            'user_count': MongoAPI.users_count_by_role(org_id, str(role.id)),
            'permissions': MongoAPI._role_permissions_from_role(role),
        }

    @staticmethod
    def getRolesListDetails(org_id, role_id):
        try:
            role = Role.objects.get(org_id=int(org_id), id=ObjectId(role_id))
            return MongoAPI._role_to_dict(role)
        except (Role.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def get_role_detail(org_id, role_id):
        try:
            role = Role.objects.get(org_id=int(org_id), id=ObjectId(role_id))
            return MongoAPI._role_to_detail(role)
        except (Role.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def get_user_role_data(org_id, user_id):
        user = MongoAPI.getUserDetails(org_id, user_id)
        role_id = user.get('role')
        if not role_id:
            return {}
        role_data = MongoAPI.getRolesListDetails(org_id, role_id)
        return MongoAPI._apply_user_permission_overrides(role_data, user)

    @staticmethod
    def _normalize_permission_overrides(raw_overrides):
        if not isinstance(raw_overrides, dict):
            return {}
        normalized = {}
        for key, value in raw_overrides.items():
            if key not in ALL_ROLE_KEYS:
                continue
            try:
                normalized[key] = 1 if int(value) == 1 else 0
            except (TypeError, ValueError):
                continue
        return normalized

    @staticmethod
    def _apply_user_permission_overrides(role_data, user):
        """Merge per-user permission overrides onto role permissions."""
        if not role_data:
            return role_data
        if is_super_admin_user(user, role_data):
            return role_data

        overrides = MongoAPI._normalize_permission_overrides(
            (user or {}).get('permission_overrides')
        )
        if not overrides:
            return role_data

        merged = dict(role_data)
        merged.update(overrides)

        # When a view-scope override is present, keep exclusivity against the
        # effective permission set (role + overrides).
        exclusive = apply_view_scope_exclusivity(
            {key: merged.get(key, 0) for key in ALL_ROLE_KEYS}
        )
        for group in VIEW_SCOPE_GROUPS:
            if any(member in overrides for member in group):
                for key in group:
                    merged[key] = 1 if int(exclusive.get(key, 0) or 0) == 1 else 0

        return merged

    @staticmethod
    def get_user_effective_permissions(org_id, user_id):
        role_data = MongoAPI.get_user_role_data(org_id, user_id)
        if not role_data:
            return {}
        user = MongoAPI.getUserDetails(org_id, user_id)
        permissions = {
            key: int(role_data.get(key, 0) or 0) for key in ALL_ROLE_KEYS
        }
        return {
            'role_id': user.get('role'),
            'role_name': role_data.get('role_name'),
            'permissions': permissions,
            'overrides': MongoAPI._normalize_permission_overrides(
                user.get('permission_overrides')
            ),
        }

    @staticmethod
    def update_user_permission(org_id, user_id, permission_key, value, actor=None):
        if permission_key not in ALL_ROLE_KEYS:
            return f'unknown_permission:{permission_key}'

        try:
            target = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
        except (User.DoesNotExist, InvalidId):
            return '0'

        target_dict = MongoAPI._user_dict(target)
        if actor and not can_manage_target_user(actor, target_dict):
            return 'You cannot manage this user'

        if is_super_admin_user(target_dict):
            return SUPER_ADMIN_IDENTITY_ERROR

        enabled = 1 if int(value) == 1 else 0
        if actor:
            actor_role_data = MongoAPI.get_user_role_data(
                org_id,
                str(actor.get('id') or actor.get('_id') or ''),
            )
            ok, error_msg = validate_permission_grant(
                actor, actor_role_data, permission_key, enabled,
            )
            if not ok:
                return error_msg

        overrides = MongoAPI._normalize_permission_overrides(
            getattr(target, 'permission_overrides', None) or {}
        )
        overrides[permission_key] = enabled

        # Keep view-scope exclusivity inside stored overrides.
        scoped = apply_view_scope_exclusivity({**overrides, permission_key: enabled})
        for group in VIEW_SCOPE_GROUPS:
            if permission_key in group:
                for key in group:
                    if int(scoped.get(key, 0) or 0) == 1:
                        overrides[key] = 1
                    elif key in overrides or key == permission_key:
                        overrides[key] = 0

        target.permission_overrides = overrides
        target.modify_date = MongoAPI._utc_now()
        target.save()
        return str(target.id)

    @staticmethod
    def user_has_permission(org_id, user_id, permission_key):
        user = MongoAPI.getUserDetails(org_id, user_id)
        if not user:
            return False
        if effective_tier(user) == 'super_admin':
            return True
        role_data = MongoAPI.get_user_role_data(org_id, user_id)
        if not role_data:
            return False
        if role_data.get('role_name') in ('Super Admin', 'Administrator'):
            return True
        return int(role_data.get(permission_key, 0) or 0) == 1

    @staticmethod
    def get_plan_data(org_id):
        organization = Organization.objects.filter(org_id=int(org_id)).first()
        plan_data = dict(DEFAULT_PLAN_DATA)
        if not organization or not organization.plan_id:
            return plan_data

        active_modules = Plan_wise_modules.objects(
            plan_id=organization.plan_id,
            status='active',
        )
        if not active_modules:
            return plan_data

        plan_data = {key: 0 for key in MODULE_KEYS}
        for module in active_modules:
            module_name = (module.module_name or '').strip().lower()
            if module_name in plan_data:
                plan_data[module_name] = 1
        return plan_data

    @staticmethod
    def users_list(
        org_id,
        search='',
        sort='create_date',
        order=-1,
        status=None,
        actor=None,
        branch_id=None,
        filter_data=None,
    ):
        query = User.objects(org_id=int(org_id))
        if status in ('active', 'inactive'):
            query = query.filter(status=status)

        branch_filter_ids = MongoAPI._resolve_user_branch_filter_ids(
            org_id, actor, branch_id, filter_data,
        )
        if branch_filter_ids is not None:
            if not branch_filter_ids:
                return []
            query = query.filter(branch_id__in=branch_filter_ids)

        users = list(query)
        if actor:
            actor_tier = effective_tier(actor)
            filtered = []
            for user in users:
                target = MongoAPI._user_dict(user)
                target_tier = effective_tier(target)
                if actor_tier == 'super_admin':
                    filtered.append(user)
                elif actor_tier == 'admin':
                    if target_tier != 'super_admin':
                        filtered.append(user)
                else:
                    # Branch managers / branch users with manage_users see
                    # same-branch non-admin users only.
                    if target_tier in ('super_admin', 'admin'):
                        continue
                    actor_branch = str(actor.get('branch_id') or '')
                    target_branch = str(target.get('branch_id') or '')
                    if actor_branch and target_branch and actor_branch == target_branch:
                        filtered.append(user)
                    elif str(target.get('id') or '') == str(actor.get('id') or ''):
                        filtered.append(user)
            users = filtered

        if search:
            search_lower = search.lower()
            users = [
                user for user in users
                if search_lower in (user.name or '').lower()
                or search_lower in (user.email or '').lower()
                or search_lower in (getattr(user, 'phone', '') or '').lower()
            ]

        reverse = order == -1 or str(order).lower() == 'desc'
        sort_key = sort if sort in ('name', 'email', 'create_date', 'status') else 'create_date'

        def sort_value(user):
            value = getattr(user, sort_key, None)
            if isinstance(value, datetime.datetime):
                return value.isoformat()
            return (value or '').lower() if isinstance(value, str) else (value or '')

        users.sort(key=sort_value, reverse=reverse)
        user_dicts = [MongoAPI._user_dict(user) for user in users]
        return MongoAPI._attach_branch_names(org_id, user_dicts)

    @staticmethod
    def active_users_list(org_id, actor=None, branch_id=None):
        query = User.objects(org_id=int(org_id), status='active')
        branch_filter_ids = MongoAPI._resolve_user_branch_filter_ids(
            org_id, actor, branch_id,
        )
        if branch_filter_ids is not None:
            if not branch_filter_ids:
                return []
            query = query.filter(branch_id__in=branch_filter_ids)
        return [
            MongoAPI._user_dict(user)
            for user in query.order_by('name')
        ]

    @staticmethod
    def add_user(org_id, data, created_by, actor=None):
        email = (data.get('email') or '').strip().lower()
        if not email:
            return 'missing_email'
        if MongoAPI.userCheck(email) == 'Yes':
            return 'email_exists'

        actor_user = actor or MongoAPI.getUserDetails(org_id, created_by)
        actor_id = actor_user.get('id') or created_by
        actor_role_data = MongoAPI.get_user_role_data(org_id, actor_id) if actor_id else {}
        ok, error_msg = validate_user_tier_branch(
            actor_user,
            data,
            lambda branch_id: MongoAPI.user_branch_exists(org_id, branch_id),
            actor_role_data=actor_role_data,
        )
        if not ok:
            return error_msg

        name = (data.get('name') or '').strip()
        phone = str(data.get('phone') or '')
        role_id = data.get('role')
        if not role_id:
            return 'role_required'
        password = data.get('password') or ''
        role_tier = data.get('role_tier') or 'branch_user'
        branch_id = MongoAPI._parse_user_branch_id(data.get('branch_id'), org_id)

        try:
            user_data = {
                'email': email,
                'name': name,
                'phone': phone,
                'org_id': int(org_id),
                'status': 'active',
                'create_date': datetime.datetime.now(timezone('UTC')),
                'role_tier': role_tier,
                'role': ObjectId(role_id),
            }
            if branch_id:
                user_data['branch_id'] = branch_id
            if password:
                user_data['password'] = password

            user = User(**user_data)
            user.save()

            return str(user.id)
        except (NotUniqueError, InvalidId):
            return '0'

    @staticmethod
    def user_update(org_id, user_id, data, actor=None):
        try:
            user = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
        except (User.DoesNotExist, InvalidId):
            return '0'

        actor_user = actor or {}
        actor_id = actor_user.get('id')
        actor_role_data = MongoAPI.get_user_role_data(org_id, actor_id) if actor_id else {}
        existing_target = MongoAPI._user_dict(user)
        ok, error_msg = validate_user_tier_branch(
            actor_user,
            data,
            lambda branch_id: MongoAPI.user_branch_exists(org_id, branch_id),
            existing_target=existing_target,
            actor_role_data=actor_role_data,
        )
        if not ok:
            return error_msg

        email = data.get('email')
        if email:
            email = email.strip().lower()
            existing = User.objects(email=email).first()
            if existing and str(existing.id) != str(user_id):
                return 'email_exists'
            user.email = email

        if 'name' in data:
            user.name = (data.get('name') or '').strip()
        if 'phone' in data:
            user.phone = str(data.get('phone') or '')
        if data.get('role'):
            user.role = ObjectId(data['role'])
        if 'role_tier' in data:
            user.role_tier = data.get('role_tier') or 'branch_user'
        if 'branch_id' in data:
            user.branch_id = MongoAPI._parse_user_branch_id(data.get('branch_id'), org_id)
        if 'assigned_project_ids' in data:
            user.assigned_project_ids = MongoAPI._extract_object_id_list(
                data.get('assigned_project_ids'),
            )

        detail_fields = normalize_user_detail_payload(data)
        if detail_fields:
            uniqueness_error = MongoAPI._apply_user_detail_fields(
                user, detail_fields, org_id, user_id,
            )
            if uniqueness_error:
                return uniqueness_error

        user.modify_date = datetime.datetime.now(timezone('UTC'))
        user.save()
        return str(user.id)

    @staticmethod
    def _apply_user_detail_fields(user, detail_fields, org_id, user_id):
        if 'aadhaar_number' in detail_fields:
            aadhaar_number = detail_fields.get('aadhaar_number')
            if aadhaar_number:
                existing = User.objects(
                    org_id=int(org_id), aadhaar_number=aadhaar_number,
                ).first()
                if existing and str(existing.id) != str(user_id):
                    return 'aadhaar_exists'
            user.aadhaar_number = aadhaar_number

        if 'pan_number' in detail_fields:
            pan_number = detail_fields.get('pan_number')
            if pan_number:
                existing = User.objects(
                    org_id=int(org_id), pan_number=pan_number,
                ).first()
                if existing and str(existing.id) != str(user_id):
                    return 'pan_exists'
            user.pan_number = pan_number

        for field in (
            'aadhaar_document', 'pan_document', 'address', 'source',
            'referred_by', 'reference_contact_number', 'passport_number',
        ):
            if field in detail_fields:
                setattr(user, field, detail_fields.get(field))

        return None

    @staticmethod
    def user_change_status(org_id, user_id, status, actor=None):
        if status not in ('active', 'inactive'):
            return 'invalid_status'
        try:
            user = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
        except (User.DoesNotExist, InvalidId):
            return '0'

        if actor:
            target = MongoAPI._user_dict(user)
            if not can_manage_target_user(actor, target):
                return 'forbidden'

        try:
            User.objects(id=ObjectId(user_id), org_id=int(org_id)).update_one(status=status)
            return str(user_id)
        except (InvalidId, Exception):
            return '0'

    @staticmethod
    def _migrate_removed_branch_manager_tier(org_id):
        User.objects(org_id=int(org_id), role_tier='branch_manager').update(
            set__role_tier='branch_user',
        )

    @staticmethod
    def _cleanup_legacy_system_roles(org_id, super_admin_role):
        """Remove old seeded default roles only; keep user-created custom roles."""
        if not super_admin_role:
            return
        for legacy_name in ('Manager', 'Standard User', 'Administrator'):
            legacy = Role.objects(org_id=int(org_id), role_name=legacy_name).first()
            if not legacy:
                continue
            if int(getattr(legacy, 'is_system_role', 0) or 0) != 1:
                continue
            User.objects(org_id=int(org_id), role=legacy.id).update(
                set__role=super_admin_role.id,
            )
            legacy.delete()

    @staticmethod
    def roles_list(org_id):
        MongoAPI._migrate_removed_branch_manager_tier(org_id)
        super_admin = Role.objects(org_id=int(org_id), role_name='Super Admin').first()
        if not super_admin:
            old_admin = Role.objects(org_id=int(org_id), role_name='Administrator').first()
            if old_admin:
                old_admin.role_name = 'Super Admin'
                old_admin.is_system_role = 1
                old_admin.save()
                super_admin = old_admin

        roles = Role.objects(org_id=int(org_id)).order_by('role_name')
        return [MongoAPI._role_list_item(role, org_id) for role in roles]

    @staticmethod
    def role_create(org_id, user_id, role_name, permissions=None, actor_user_id=None):
        role_name = (role_name or '').strip()
        if not role_name:
            return 'missing_name'
        if Role.objects(org_id=int(org_id), role_name=role_name).first():
            return 'duplicate'

        permission_updates = apply_view_scope_exclusivity(
            flatten_role_permission_payload(permissions or {}),
        )
        for key in permission_updates:
            if key not in ALL_ROLE_KEYS:
                return f'unknown_permission:{key}'

        actor = None
        actor_role_data = None
        if actor_user_id:
            actor = MongoAPI.getUserDetails(org_id, actor_user_id)
            actor_role_data = MongoAPI.get_user_role_data(org_id, actor_user_id)

        try:
            role_data = {
                'org_id': int(org_id),
                'role_name': role_name,
                'create_by': ObjectId(user_id),
                'is_system_role': 0,
                **DEFAULT_ROLE_PERMISSIONS,
            }
            for key, value in permission_updates.items():
                if actor_user_id:
                    ok, error_msg = validate_permission_grant(
                        actor, actor_role_data, key, value,
                    )
                    if not ok:
                        return error_msg
                role_data[key] = 1 if int(value) == 1 else 0

            role = Role(**role_data)
            role.save()
            return str(role.id)
        except (NotUniqueError, InvalidId):
            return '0'

    @staticmethod
    def role_update(org_id, role_id, data, actor_user_id=None):
        try:
            role = Role.objects.get(org_id=int(org_id), id=ObjectId(role_id))
        except (Role.DoesNotExist, InvalidId):
            return '0'

        actor = None
        actor_role_data = None
        if actor_user_id:
            actor = MongoAPI.getUserDetails(org_id, actor_user_id)
            actor_role_data = MongoAPI.get_user_role_data(org_id, actor_user_id)

        is_system = MongoAPI._role_is_system(role)
        if is_system and actor_user_id and effective_tier(actor) != 'super_admin':
            return 'protected_system_role'

        if 'role_name' in data:
            if is_system or role.role_name in SYSTEM_ROLE_NAMES:
                new_name = (data.get('role_name') or '').strip()
                if new_name != role.role_name:
                    return 'protected_super_admin_role_name'
            elif data.get('role_name'):
                new_name = data['role_name'].strip()
                existing = Role.objects(org_id=int(org_id), role_name=new_name).first()
                if existing and str(existing.id) != str(role_id):
                    return 'duplicate'
                role.role_name = new_name

        permission_updates = apply_view_scope_exclusivity(flatten_role_permission_payload(data))
        for key in permission_updates:
            if key not in ALL_ROLE_KEYS:
                return f'unknown_permission:{key}'

        for key, value in permission_updates.items():
            if actor_user_id:
                ok, error_msg = validate_permission_grant(
                    actor, actor_role_data, key, value,
                )
                if not ok:
                    return error_msg
            role[key] = 1 if int(value) == 1 else 0

        role.save()
        return str(role.id)

    @staticmethod
    def role_delete(org_id, role_id, reassign_to=None):
        try:
            role = Role.objects.get(org_id=int(org_id), id=ObjectId(role_id))
        except (Role.DoesNotExist, InvalidId):
            return '0'

        if MongoAPI._role_is_system(role):
            return 'protected'

        users_with_role = User.objects(org_id=int(org_id), role=ObjectId(role_id)).count()
        if users_with_role > 0:
            if not reassign_to:
                return 'in_use'
            try:
                target_role = Role.objects.get(org_id=int(org_id), id=ObjectId(reassign_to))
            except (Role.DoesNotExist, InvalidId):
                return 'invalid_reassign'
            if str(target_role.id) == str(role_id):
                return 'invalid_reassign'
            User.objects(org_id=int(org_id), role=ObjectId(role_id)).update(
                set__role=ObjectId(reassign_to),
            )

        role.delete()
        return str(role_id)

    @staticmethod
    def seed_default_roles(org_id, user_id):
        created = {}

        # Rename old Administrator role to Super Admin if present
        old_admin = Role.objects(org_id=int(org_id), role_name='Administrator').first()
        if old_admin:
            old_admin.role_name = 'Super Admin'
            old_admin.is_system_role = 1
            for key, value in DEFAULT_ADMIN_PERMISSIONS.items():
                setattr(old_admin, key, value)
            old_admin.save()

        for role_name, defaults in SYSTEM_ROLE_DEFAULTS.items():
            existing = Role.objects(org_id=int(org_id), role_name=role_name).first()
            if existing:
                if int(getattr(existing, 'is_system_role', 0) or 0) != 1:
                    existing.is_system_role = 1
                # Keep Super Admin in sync with the full permission catalog.
                for key, value in defaults.items():
                    setattr(existing, key, value)
                existing.save()
                created[role_name] = str(existing.id)
                continue
            role_data = {
                'org_id': int(org_id),
                'role_name': role_name,
                'create_by': ObjectId(user_id),
                'is_system_role': 1,
                **defaults,
            }
            role = Role(**role_data)
            role.save()
            created[role_name] = str(role.id)

        # Remove legacy seeded default roles (reassign users to Super Admin)
        super_admin = Role.objects(org_id=int(org_id), role_name='Super Admin').first()
        MongoAPI._cleanup_legacy_system_roles(org_id, super_admin)

        MongoAPI._migrate_removed_branch_manager_tier(org_id)
        return created

    @staticmethod
    def users_count_by_role(org_id, role_id):
        return User.objects(org_id=int(org_id), role=ObjectId(role_id)).count()

    @staticmethod
    def _parse_branch_id(branch_id):
        if branch_id is None or branch_id == '':
            return None
        try:
            return int(branch_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_branch_id_list(branch_values):
        if branch_values is None:
            return []
        if isinstance(branch_values, str):
            if not branch_values.strip():
                return []
            parts = branch_values.split(',') if ',' in branch_values else [branch_values]
        elif isinstance(branch_values, (list, tuple)):
            parts = branch_values
        else:
            parts = [branch_values]

        branch_ids = []
        for part in parts:
            parsed = MongoAPI._parse_branch_id(part)
            if parsed is not None:
                branch_ids.append(parsed)
        return branch_ids

    @staticmethod
    def _branch_ids_from_filter_data(filter_data):
        branch_ids = []
        for data in filter_data or []:
            field = data.get('field')
            if field not in ('branch_id', 'branch'):
                continue
            branch_ids.extend(
                MongoAPI._parse_branch_id_list(data.get('selected_values') or []),
            )
        return branch_ids

    @staticmethod
    def _parse_user_branch_id(branch_id, org_id=None):
        if branch_id is None or branch_id == '':
            return None
        object_id = MongoAPI._extract_object_id(branch_id)
        if object_id is not None:
            return object_id
        parsed_int = MongoAPI._parse_branch_id(branch_id)
        if parsed_int is not None and org_id is not None:
            return MongoAPI._branch_int_to_object_id(org_id, parsed_int)
        return None

    @staticmethod
    def _parse_user_branch_id_list(branch_values, org_id=None):
        if branch_values is None:
            return []
        if isinstance(branch_values, str):
            if not branch_values.strip():
                return []
            parts = branch_values.split(',') if ',' in branch_values else [branch_values]
        elif isinstance(branch_values, (list, tuple)):
            parts = branch_values
        else:
            parts = [branch_values]

        branch_ids = []
        for part in parts:
            parsed = MongoAPI._parse_user_branch_id(part, org_id)
            if parsed is not None:
                branch_ids.append(parsed)
        return branch_ids

    @staticmethod
    def _user_branch_ids_from_filter_data(filter_data, org_id=None):
        branch_ids = []
        for data in filter_data or []:
            field = data.get('field')
            if field not in ('branch_id', 'branch'):
                continue
            branch_ids.extend(
                MongoAPI._parse_user_branch_id_list(
                    data.get('selected_values') or [], org_id,
                ),
            )
        return branch_ids

    @staticmethod
    def _branch_int_to_object_id(org_id, branch_int):
        if branch_int is None:
            return None
        try:
            branch = Branch.objects.get(org_id=int(org_id), branch_id=int(branch_int))
            return branch.id
        except Branch.DoesNotExist:
            return None

    @staticmethod
    def _branch_object_id_to_int(org_id, branch_ref):
        object_id = MongoAPI._parse_user_branch_id(branch_ref, org_id)
        if object_id is None:
            return None
        try:
            branch = Branch.objects.get(org_id=int(org_id), id=object_id)
            return branch.branch_id
        except Branch.DoesNotExist:
            return None

    @staticmethod
    def branch_ref_to_int(org_id, branch_ref):
        if branch_ref is None or branch_ref == '':
            return None
        parsed_int = MongoAPI._parse_branch_id(branch_ref)
        if parsed_int is not None:
            return parsed_int
        return MongoAPI._branch_object_id_to_int(org_id, branch_ref)

    @staticmethod
    def _branch_object_ids_to_ints(org_id, branch_refs):
        branch_ints = []
        for branch_ref in branch_refs or []:
            parsed_int = MongoAPI.branch_ref_to_int(org_id, branch_ref)
            if parsed_int is not None:
                branch_ints.append(parsed_int)
        return branch_ints

    @staticmethod
    def _resolve_user_branch_filter_ids(org_id, actor=None, branch_id=None, filter_data=None):
        """Resolve Branch ObjectIds for user queries."""
        explicit = MongoAPI._parse_user_branch_id_list(branch_id, org_id)
        if not explicit:
            explicit = MongoAPI._user_branch_ids_from_filter_data(filter_data, org_id)
        if explicit:
            if actor:
                accessible = MongoAPI.get_actor_accessible_branch_ids(actor, org_id)
                if accessible != 'all':
                    accessible_set = {str(item) for item in accessible}
                    explicit = [
                        item for item in explicit if str(item) in accessible_set
                    ]
            return explicit

        if actor:
            accessible = MongoAPI.get_actor_accessible_branch_ids(actor, org_id)
            if accessible != 'all':
                return [
                    parsed
                    for item in accessible
                    if (parsed := MongoAPI._parse_user_branch_id(item, org_id))
                ] or []
        return None

    @staticmethod
    def _resolve_branch_filter_ids(org_id, actor=None, branch_id=None, filter_data=None):
        """Resolve integer branch IDs for lead/project/booking queries."""
        explicit = MongoAPI._parse_branch_id_list(branch_id)
        if not explicit:
            explicit = MongoAPI._branch_ids_from_filter_data(filter_data)
        if not explicit:
            explicit = MongoAPI._branch_object_ids_to_ints(
                org_id,
                MongoAPI._parse_user_branch_id_list(branch_id, org_id),
            )
        if not explicit:
            explicit = MongoAPI._branch_object_ids_to_ints(
                org_id,
                MongoAPI._user_branch_ids_from_filter_data(filter_data, org_id),
            )
        if explicit:
            if actor:
                accessible = MongoAPI.get_actor_accessible_branch_ids(actor, org_id)
                if accessible != 'all':
                    accessible_ints = MongoAPI._branch_object_ids_to_ints(org_id, accessible)
                    explicit = [bid for bid in explicit if bid in accessible_ints]
            return explicit

        if actor:
            accessible = MongoAPI.get_actor_accessible_branch_ids(actor, org_id)
            if accessible != 'all':
                return MongoAPI._branch_object_ids_to_ints(org_id, accessible)
        return None

    @staticmethod
    def _apply_integer_list_filter(
        match_filter, filter_key, selected_values, indicator, org_id=None,
    ):
        values = MongoAPI._parse_branch_id_list(selected_values)
        if not values and org_id is not None:
            values = MongoAPI._branch_object_ids_to_ints(
                org_id,
                MongoAPI._parse_user_branch_id_list(selected_values, org_id),
            )
        if not values:
            return
        if indicator == 'is':
            match_filter[filter_key] = {'$in': values}
        else:
            match_filter[filter_key] = {'$nin': values}

    @staticmethod
    def _apply_branch_scope_to_match_filter(
        match_filter, actor, filter_data=None, branch_id=None, org_id=None,
        include_unset_branch=False,
    ):
        """Apply dynamic branch scope. Returns False when the result set must be empty."""
        branch_filter_ids = MongoAPI._resolve_branch_filter_ids(
            org_id, actor, branch_id, filter_data,
        )
        if branch_filter_ids is None:
            return True
        if not branch_filter_ids:
            return False
        branch_values = list(branch_filter_ids)
        if include_unset_branch:
            branch_values.append(None)
        match_filter['branch_id'] = {'$in': branch_values}
        return True

    @staticmethod
    def _resolve_lead_branch_id(org_id, data, actor_id=None):
        explicit_branch = data.get('branch_id')
        if explicit_branch not in (None, ''):
            resolved = MongoAPI.branch_ref_to_int(org_id, explicit_branch)
            if resolved is not None:
                return resolved

        for user_ref in (data.get('assigned_to'), actor_id):
            user_id = MongoAPI._extract_object_id(user_ref)
            if not user_id:
                continue
            user = MongoAPI.getUserDetails(org_id, user_id)
            if not user:
                continue
            branch_int = MongoAPI.branch_ref_to_int(org_id, user.get('branch_id'))
            if branch_int is not None:
                return branch_int
        return None

    @staticmethod
    def _attach_branch_names(org_id, user_dicts):
        branch_object_ids = []
        for item in user_dicts:
            branch_id = item.get('branch_id')
            if branch_id is None:
                continue
            object_id = MongoAPI._parse_user_branch_id(branch_id, org_id)
            if object_id is not None:
                branch_object_ids.append(object_id)
        if not branch_object_ids:
            return user_dicts

        name_by_id = {
            str(branch.id): branch.name
            for branch in Branch.objects(org_id=int(org_id), id__in=branch_object_ids)
        }
        for item in user_dicts:
            branch_id = item.get('branch_id')
            if branch_id is not None:
                item['branch_name'] = name_by_id.get(str(branch_id), '')
        return user_dicts

    @staticmethod
    def _next_branch_id(org_id):
        last_branch = Branch.objects(org_id=int(org_id)).order_by('-branch_id').first()
        if last_branch and last_branch.branch_id is not None:
            return int(last_branch.branch_id) + 1
        return 1

    @staticmethod
    def _migrate_branch_ids_to_int(org_id):
        org_id = int(org_id)
        coll = Branch._get_collection()
        branches = list(coll.find({'org_id': org_id}))
        if not branches:
            return
        if all(isinstance(b.get('branch_id'), int) for b in branches):
            return

        branches.sort(key=lambda b: (
            b.get('create_date') or datetime.datetime.min.replace(tzinfo=timezone('UTC')),
            str(b.get('branch_id', '')),
        ))

        mapping = {}
        next_id = 1
        for branch in branches:
            old_id = branch.get('branch_id')
            if isinstance(old_id, int):
                mapping[old_id] = old_id
                next_id = max(next_id, old_id + 1)
            elif old_id not in mapping:
                mapping[old_id] = next_id
                next_id += 1

        ref_models = (Lead, Project, Booking)
        for old_id, new_id in mapping.items():
            if old_id == new_id:
                continue
            coll.update_one(
                {'org_id': org_id, 'branch_id': old_id},
                {'$set': {'branch_id': new_id}},
            )
            for model in ref_models:
                model._get_collection().update_many(
                    {'org_id': org_id, 'branch_id': old_id},
                    {'$set': {'branch_id': new_id}},
                )

    @staticmethod
    def _serialize_user_branch_id(org_id, branch_ref):
        """Return Branch document ObjectId as string for API responses."""
        object_id = MongoAPI._parse_user_branch_id(branch_ref, org_id)
        return str(object_id) if object_id else None

    @staticmethod
    def _ensure_user_branch_object_id(user):
        """Migrate legacy integer branch_id to Branch ObjectId on read.

        Does not clear unknown values — that belongs in bulk migration only.
        """
        branch_ref = getattr(user, 'branch_id', None)
        if branch_ref is None:
            return
        if isinstance(branch_ref, ObjectId):
            return

        org_id = int(user.org_id)
        branch = None
        if isinstance(branch_ref, int):
            branch = Branch.objects(org_id=org_id, branch_id=branch_ref).first()
        elif isinstance(branch_ref, str) and branch_ref.strip().isdigit():
            branch = Branch.objects(org_id=org_id, branch_id=int(branch_ref.strip())).first()
        else:
            object_id = MongoAPI._extract_object_id(branch_ref)
            if object_id is not None:
                branch = Branch.objects(org_id=org_id, id=object_id).first()

        if branch and user.branch_id != branch.id:
            user.branch_id = branch.id
            user.save()

    @staticmethod
    def _migrate_user_branch_ids_to_object_id(org_id):
        org_id = int(org_id)
        if org_id in MongoAPI._USER_BRANCH_MIGRATED_ORGS:
            return

        MongoAPI._migrate_branch_ids_to_int(org_id)
        coll = User._get_collection()
        needs_migration = coll.count_documents({
            'org_id': org_id,
            'branch_id': {'$exists': True, '$ne': None, '$not': {'$type': 'objectId'}},
        })
        if needs_migration == 0:
            MongoAPI._USER_BRANCH_MIGRATED_ORGS.add(org_id)
            return

        for user in coll.find({'org_id': org_id, 'branch_id': {'$exists': True, '$ne': None}}):
            branch_ref = user.get('branch_id')
            if isinstance(branch_ref, ObjectId):
                continue
            branch = None
            if isinstance(branch_ref, int):
                branch = Branch.objects(org_id=org_id, branch_id=branch_ref).first()
            elif isinstance(branch_ref, str) and branch_ref.strip().isdigit():
                branch = Branch.objects(org_id=org_id, branch_id=int(branch_ref.strip())).first()
            else:
                object_id = MongoAPI._extract_object_id(branch_ref)
                if object_id is not None:
                    branch = Branch.objects(org_id=org_id, id=object_id).first()
            if branch:
                coll.update_one(
                    {'_id': user['_id']},
                    {'$set': {'branch_id': branch.id}},
                )
            elif branch_ref is not None:
                coll.update_one(
                    {'_id': user['_id']},
                    {'$unset': {'branch_id': ''}},
                )
        MongoAPI._USER_BRANCH_MIGRATED_ORGS.add(org_id)

    @staticmethod
    def _branch_dict(branch):
        return {
            'id': str(branch.id),
            'branch_id': branch.branch_id,
            'org_id': branch.org_id,
            'name': branch.name,
            'code': branch.code,
            'status': branch.status or 'active',
            'manager_user_id': branch.manager_user_id or None,
        }

    @staticmethod
    def _org_assigned_branch_object_id_strings(org_id):
        """Branches that have at least one user or project assigned in the org."""
        org_id = int(org_id)
        object_ids = set()

        for user in User.objects(
            org_id=org_id,
            branch_id__exists=True,
            branch_id__ne=None,
        ).only('branch_id'):
            if user.branch_id:
                object_ids.add(user.branch_id)

        for project in Project.objects(
            org_id=org_id,
            branch_id__exists=True,
            branch_id__ne=None,
        ).only('branch_id'):
            branch_oid = MongoAPI._branch_int_to_object_id(org_id, project.branch_id)
            if branch_oid is not None:
                object_ids.add(branch_oid)

        return [str(branch_oid) for branch_oid in object_ids]

    @staticmethod
    def get_actor_accessible_branch_ids(actor, org_id=None):
        """Resolve accessible branch ids for list/query scoping."""
        if not actor:
            return 'all'

        resolved_org_id = org_id or actor.get('org_id')
        branch_id = actor.get('branch_id')
        if branch_id not in (None, ''):
            serialized = MongoAPI._serialize_user_branch_id(resolved_org_id, branch_id)
            return [serialized] if serialized else []

        # Org-level tiers see all branches; do not narrow to "in-use" branches.
        return get_accessible_branch_ids(actor)

    @staticmethod
    def branch_exists(org_id, branch_id):
        parsed = MongoAPI._parse_branch_id(branch_id)
        if parsed:
            return Branch.objects(
                org_id=int(org_id),
                branch_id=parsed,
                status='active',
            ).first() is not None
        object_id = MongoAPI._parse_user_branch_id(branch_id, org_id)
        if object_id is None:
            return False
        return Branch.objects(
            org_id=int(org_id),
            id=object_id,
            status='active',
        ).first() is not None

    @staticmethod
    def user_branch_exists(org_id, branch_id):
        object_id = MongoAPI._parse_user_branch_id(branch_id, org_id)
        if object_id is None:
            return False
        return Branch.objects(
            org_id=int(org_id),
            id=object_id,
            status='active',
        ).first() is not None

    @staticmethod
    def branch_allowed_for_record(user, org_id, record_branch_id):
        parsed = MongoAPI._parse_branch_id(record_branch_id)
        if not parsed:
            return False
        accessible = MongoAPI.get_actor_accessible_branch_ids(user, org_id)
        if accessible == 'all':
            return True
        branch_oid = MongoAPI._branch_int_to_object_id(org_id, parsed)
        if branch_oid is None:
            return False
        return any(str(item) == str(branch_oid) for item in accessible)

    @staticmethod
    def seed_default_branches(org_id):
        defaults = [
            ('Branch A', 'A'),
            ('Branch B', 'B'),
            ('Branch C', 'C'),
        ]
        created = []
        for name, code in defaults:
            if Branch.objects(org_id=int(org_id), code=code).first():
                continue
            branch_id = MongoAPI._next_branch_id(org_id)
            branch = Branch(
                branch_id=branch_id,
                org_id=int(org_id),
                name=name,
                code=code,
                status='active',
            )
            branch.save()
            created.append(branch_id)
        return created

    @staticmethod
    def set_user_tier(org_id, user_id, role_tier, branch_id=None):
        try:
            user = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
            existing = MongoAPI._user_dict(user)
            if is_super_admin_user(existing):
                if normalize_tier(role_tier) != 'super_admin':
                    return False
                if branch_id:
                    return False
            user.role_tier = role_tier
            user.branch_id = MongoAPI._parse_user_branch_id(branch_id, org_id)
            user.save()
            return True
        except (InvalidId, User.DoesNotExist, Exception):
            return False

    @staticmethod
    def branch_list(org_id, actor=None, for_management=False):
        MongoAPI._migrate_branch_ids_to_int(org_id)
        MongoAPI._migrate_user_branch_ids_to_object_id(org_id)
        query = Branch.objects(org_id=int(org_id))
        # Management screens need the full org catalog; record modules keep actor scoping.
        accessible = (
            'all'
            if for_management or not actor
            else MongoAPI.get_actor_accessible_branch_ids(actor, org_id)
        )
        if accessible != 'all':
            if not accessible:
                return []
            accessible_ids = [
                parsed
                for item in accessible
                if (parsed := MongoAPI._parse_user_branch_id(item, org_id))
            ]
            if not accessible_ids:
                return []
            query = query.filter(id__in=accessible_ids)
        branches = list(query.order_by('name'))
        if (
            not branches
            and actor
            and effective_tier(actor) == 'admin'
            and accessible == 'all'
        ):
            MongoAPI.seed_default_branches(org_id)
            branches = list(Branch.objects(org_id=int(org_id)).order_by('name'))
        return [MongoAPI._branch_dict(branch) for branch in branches]

    @staticmethod
    def _find_branch_payload(org_id, result, fallback=None):
        """Match a create/update result by ObjectId string or legacy integer branch_id."""
        branches = MongoAPI.branch_list(org_id, for_management=True)
        result_str = str(result) if result is not None else ''
        for item in branches:
            if item.get('id') == result_str:
                return item
            if result_str.isdigit() and item.get('branch_id') == int(result_str):
                return item
            if item.get('branch_id') == result:
                return item
        payload = {'id': result_str} if result_str else {}
        if fallback:
            payload.update(fallback)
        return payload

    @staticmethod
    def branch_create(org_id, data):
        name = (data.get('name') or '').strip()
        code = (data.get('code') or '').strip().upper()
        if not name:
            return 'missing_name'
        if not code:
            return 'missing_code'

        branch_id = MongoAPI._parse_branch_id(data.get('branch_id'))
        if branch_id is None and data.get('branch_id') not in (None, ''):
            return 'invalid_id'
        if branch_id is None:
            branch_id = MongoAPI._next_branch_id(org_id)
        if Branch.objects(org_id=int(org_id), code=code).first():
            return 'duplicate_code'
        if Branch.objects(org_id=int(org_id), branch_id=branch_id).first():
            return 'duplicate_id'

        try:
            branch = Branch(
                branch_id=branch_id,
                org_id=int(org_id),
                name=name,
                code=code,
                status='active',
                manager_user_id=data.get('manager_user_id') or None,
            )
            branch.save()
            return str(branch.id)
        except (NotUniqueError, ValidationError):
            return '0'

    @staticmethod
    def _get_branch_for_update(org_id, branch_id):
        """Resolve branch by Mongo ObjectId or legacy integer branch_id."""
        object_id = MongoAPI._parse_user_branch_id(branch_id, org_id)
        if object_id is not None:
            try:
                return Branch.objects.get(org_id=int(org_id), id=object_id)
            except Branch.DoesNotExist:
                pass

        parsed_branch_id = MongoAPI._parse_branch_id(branch_id)
        if not parsed_branch_id:
            return None
        try:
            return Branch.objects.get(org_id=int(org_id), branch_id=parsed_branch_id)
        except Branch.DoesNotExist:
            return None

    @staticmethod
    def branch_update(org_id, branch_id, data):
        branch = MongoAPI._get_branch_for_update(org_id, branch_id)
        if branch is None:
            return '0'

        if data.get('name'):
            branch.name = data['name'].strip()
        if data.get('code'):
            new_code = data['code'].strip().upper()
            existing = Branch.objects(org_id=int(org_id), code=new_code).first()
            if existing and existing.branch_id != branch.branch_id:
                return 'duplicate_code'
            branch.code = new_code
        if 'manager_user_id' in data:
            branch.manager_user_id = data.get('manager_user_id') or None
        if data.get('status') in ('active', 'inactive'):
            branch.status = data['status']

        branch.modify_date = datetime.datetime.now(timezone('UTC'))
        branch.save()
        return str(branch.id)

    @staticmethod
    def branch_deactivate(org_id, branch_id):
        parsed_branch_id = MongoAPI._parse_branch_id(branch_id)
        if not parsed_branch_id:
            return '0'
        try:
            branch = Branch.objects.get(org_id=int(org_id), branch_id=parsed_branch_id)
        except Branch.DoesNotExist:
            return '0'
        branch.status = 'inactive'
        branch.modify_date = datetime.datetime.now(timezone('UTC'))
        branch.save()
        return branch.branch_id

    @staticmethod
    def organizationInfo(org_id):
        organization = Organization.objects.filter(org_id=org_id).first()
        if not organization:
            return {}
        info = {
            'id': str(organization.id),
            'org_id': organization.org_id,
            'user_name': getattr(organization, 'user_name', '') or '',
            'organization_name': organization.organization_name,
            'email': organization.email,
            'signup_via': organization.signup_via,
            'status': organization.status,
            'two_step': organization.two_step,
        }
        if organization.plan_id:
            info['plan_id'] = str(organization.plan_id)
        if organization.trial:
            info['trial'] = organization.trial
        if organization.partner_id:
            info['partner_id'] = organization.partner_id
        return info

    @staticmethod
    def _parse_optional_datetime(value):
        if not value:
            return None
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, str):
            for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                try:
                    return datetime.datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return None

    @staticmethod
    def change_otp(user_id, otp):
        try:
            User.objects(id=ObjectId(user_id)).update_one(verify_otp=otp)
            return 'Yes'
        except Exception:
            return 'No'

    @staticmethod
    def authorizationCheck(user_id):
        try:
            user = User.objects.get(id=ObjectId(user_id), status='active')
            return MongoAPI._user_dict(user)
        except (User.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def authorizationCheck_otp(user_id):
        try:
            user = User.objects.get(id=ObjectId(user_id), status='active')
            data = MongoAPI._user_dict(user)
            data['verify_otp'] = user.verify_otp
            return data
        except User.DoesNotExist:
            return {}

    @staticmethod
    def confirm_Password(user_id, password):
        try:
            user = User.objects.get(id=ObjectId(user_id))
            user.update(password=password)
            return 'Yes'
        except (User.DoesNotExist, InvalidId):
            return 'No'
        except Exception:
            return 'No'

    @staticmethod
    def _next_org_id():
        last_org = Organization.objects.order_by('-org_id').first()
        return (last_org.org_id if last_org else 0) + 1

    @staticmethod
    def create_organization(email, name='', signup_via='email', user_name=''):
        return MongoAPI.create_organization_planData(
            email, name, None, None, None, None, signup_via, None, user_name=user_name,
        )

    @staticmethod
    def create_organization_planData(
        email,
        name,
        plan_id,
        trial,
        plan_start_date,
        plan_end_date,
        signup_via,
        partner_id,
        coupon='',
        user_name='',
    ):
        try:
            last_data_id = int(LastDataId.getOrganizationLastDataId('org_id')) + 1
            organization_data = {
                'org_id': last_data_id,
                'user_name': user_name or '',
                'organization_name': name or '',
                'email': email,
                'signup_via': signup_via or 'email',
                'trial': trial,
                'plan_start_date': MongoAPI._parse_optional_datetime(plan_start_date),
                'plan_end_date': MongoAPI._parse_optional_datetime(plan_end_date),
                'partner_id': partner_id,
                'coupon': coupon or '',
            }
            if plan_id:
                organization_data['plan_id'] = ObjectId(plan_id)
            Organization(**organization_data).save()
            return last_data_id
        except (NotUniqueError, InvalidId):
            return '0'

    @staticmethod
    def create_user(email, name, org_id, verify_otp, password=''):
        return MongoAPI.createUser_plan(
            email,
            password,
            name,
            org_id,
            None,
            None,
            None,
            verify_otp,
        )

    @staticmethod
    def createUser_plan(
        email,
        data_enc,
        name,
        org_id,
        create_date,
        plan_start_date,
        plan_end_date,
        verify_otp,
    ):
        try:
            user_data = {
                'email': email,
                'name': name or '',
                'org_id': org_id,
                'verify_otp': verify_otp,
                'status': 'active',
                'create_date': MongoAPI._parse_optional_datetime(create_date) or datetime.datetime.now(
                    timezone('UTC')
                ),
                'plan_start_date': MongoAPI._parse_optional_datetime(plan_start_date),
                'plan_end_date': MongoAPI._parse_optional_datetime(plan_end_date),
                'report_days': [
                    'Monday',
                    'Tuesday',
                    'Wednesday',
                    'Thursday',
                    'Friday',
                    'Saturday',
                ],
            }
            if data_enc:
                user_data['password'] = data_enc
            user = User(**user_data)
            user.save()
            return {'user_id': str(user.id)}
        except NotUniqueError:
            return ''

    @staticmethod
    def insertDemoData(org_id, user_id):
        return True

    @staticmethod
    def emailSubmit_signup(org_id, user_id, data1, email_id, attachment):
        try:
            to_list = data1['to'].split(',') if data1.get('to') else []
            cc_list = data1['cc'].split(',') if data1.get('cc') else []
            bcc_list = data1['bcc'].split(',') if data1.get('bcc') else []

            email_record = Email(
                email_id=Uid.generateUUID(),
                org_id=org_id,
                email_type='bulk',
                fromEmail=email_id,
                to=to_list,
                cc=cc_list,
                bcc=bcc_list,
                subject=data1.get('subject', ''),
                content=data1.get('content', ''),
                attachment=attachment.split(',') if attachment else [],
                associate_to=data1.get('associate_to', 'signup'),
                associate_id=ObjectId(data1['associate_id']) if data1.get('associate_id') else None,
                create_by=ObjectId(user_id),
                create_date=datetime.datetime.now(timezone('UTC')),
            )
            email_record.save()
            return str(email_record.id)
        except (NotUniqueError, InvalidId, Exception):
            return '0'

    @staticmethod
    def singleEmailSubmit(org_id, user_id, data1, from_email, attachment_list='', thread_id=None):
        try:
            to_list = [email.strip() for email in data1.get('to', '').split(',') if email.strip()]
            cc_list = [email.strip() for email in data1.get('cc', '').split(',') if email.strip()]
            bcc_list = [email.strip() for email in data1.get('bcc', '').split(',') if email.strip()]

            attachments = []
            if attachment_list and str(attachment_list).strip().lower() not in ('none', 'null', 'undefined'):
                attachments = [
                    item.strip()
                    for item in str(attachment_list).split(',')
                    if item.strip()
                ]

            thread_id_value = None
            if thread_id and str(thread_id).strip().lower() not in ('none', 'null', 'undefined', ''):
                thread_id_value = str(thread_id)

            email_record = Email(
                email_id=Uid.generateUUID(),
                org_id=int(org_id),
                email_type='single',
                fromEmail=from_email,
                to=to_list,
                cc=cc_list,
                bcc=bcc_list,
                subject=data1.get('subject', ''),
                content=data1.get('content', ''),
                attachment=attachments,
                associate_to=data1.get('associate_to', 'lead'),
                associate_id=ObjectId(data1['associate_id']) if data1.get('associate_id') else None,
                thread_id=thread_id_value,
                create_by=ObjectId(user_id),
                create_date=datetime.datetime.now(timezone('UTC')),
                status='1',
            )
            email_record.save()
            return str(email_record.id)
        except (NotUniqueError, InvalidId, Exception):
            return '0'

    @staticmethod
    def create_administrator_role(org_id, user_id):
        MongoAPI.seed_default_roles(org_id, user_id)
        admin_role_id = MongoAPI.userAdministratorRole(org_id)
        if admin_role_id and admin_role_id != 0:
            MongoAPI.userRoleUpdate(user_id, admin_role_id)
            return admin_role_id
        return '0'

    @staticmethod
    def updateDeviceID(org_id, user_id, device_id):
        try:
            User.objects(org_id=org_id, id=ObjectId(user_id)).update(device_id=device_id)
            return True
        except Exception:
            return False

    @staticmethod
    def clearDeviceID(org_id, user_id):
        return MongoAPI.updateDeviceID(org_id, user_id, '')

    @staticmethod
    def _today_audit_filter(user_id, app_type=None):
        today = datetime.datetime.today()
        from_date = datetime.datetime(today.year, today.month, today.day, 0, 0)
        to_date = datetime.datetime(today.year, today.month, today.day, 23, 59)
        audit_filter = {
            'user_id': ObjectId(user_id),
            'start_time': {'$gte': from_date, '$lte': to_date},
        }
        if app_type:
            audit_filter['app_type'] = app_type
        return audit_filter

    @staticmethod
    def _find_today_audit_id(user_id, app_type=None):
        pipeline = [{'$match': MongoAPI._today_audit_filter(user_id, app_type)}]
        data = User_audit.objects.aggregate(*pipeline)
        check_data = json.loads(json_util.dumps(data))
        if not check_data:
            return None
        return check_data[-1]['_id']['$oid']

    @staticmethod
    def userAudit(user_id, org_id, start_time, app_type):
        try:
            if MongoAPI._find_today_audit_id(user_id):
                return '1'
            audit = User_audit(
                user_id=ObjectId(user_id),
                org_id=org_id,
                start_time=start_time,
                end_time=start_time,
                app_type=app_type,
            )
            audit.save()
            return str(audit.id)
        except NotUniqueError:
            return ''
        except Exception:
            return ''

    @staticmethod
    def userLogoutWeb(user_id, org_id, end_time):
        return MongoAPI._user_logout(user_id, org_id, end_time, 'web')

    @staticmethod
    def userLogoutMobile(user_id, org_id, end_time):
        return MongoAPI._user_logout(user_id, org_id, end_time, 'mobile')

    @staticmethod
    def _user_logout(user_id, org_id, end_time, app_type):
        try:
            audit_id = MongoAPI._find_today_audit_id(user_id, app_type)
            if not audit_id:
                return '1'
            User_audit.objects(id=ObjectId(audit_id)).update(end_time=end_time)
            return user_id
        except NotUniqueError:
            return ''
        except Exception:
            return ''

    @staticmethod
    def revoke_token(jti, user_id=None):
        try:
            RevokedToken(jti=jti, user_id=str(user_id) if user_id else None).save()
            return True
        except NotUniqueError:
            return True
        except Exception:
            return False

    @staticmethod
    def is_token_revoked(jti):
        return RevokedToken.objects(jti=jti).first() is not None

    @staticmethod
    def _lead_dict(lead):
        return {
            '_id': str(lead.id),
            'id': str(lead.id),
            'org_id': lead.org_id,
            'name': lead.name,
            'email': lead.email or '',
            'phone': lead.phone or '',
            'project_name': lead.project_name or '',
            'company_name': lead.company_name or lead.project_name or '',
            'customer_type': str(lead.customer_type) if lead.customer_type else None,
            'customer_requirement': MongoAPI._format_object_id_list(lead.customer_requirement),
            'current_staying': lead.current_staying or '',
            'lead_no': lead.lead_no or '',
            'description': lead.description or '',
            'status': lead.status,
            'assigned_to': str(lead.assigned_to) if lead.assigned_to else None,
            'create_by': str(lead.create_by) if lead.create_by else None,
        }

    @staticmethod
    def create_lead(org_id, user_id, data):
        lead_id = MongoAPI.lead_submit(org_id, user_id, data)
        if not lead_id:
            return None
        try:
            lead = Lead.objects.get(id=ObjectId(lead_id), org_id=int(org_id))
            return MongoAPI._lead_dict(lead)
        except (Lead.DoesNotExist, InvalidId):
            return None

    @staticmethod
    def _utc_now():
        return datetime.datetime.now(timezone('UTC'))

    @staticmethod
    def _extract_object_id(value):
        if value is None or value == '':
            return None
        if isinstance(value, ObjectId):
            return value
        if isinstance(value, dict):
            if '$oid' in value:
                value = value['$oid']
            elif '_id' in value:
                value = value['_id']
                if isinstance(value, dict) and '$oid' in value:
                    value = value['$oid']
            else:
                return None
        try:
            return ObjectId(str(value))
        except (InvalidId, TypeError, ValueError):
            return None

    @staticmethod
    def _extract_object_id_list(value):
        if value is None or value == '':
            return []
        if isinstance(value, str) and ',' in value:
            value = [part.strip() for part in value.split(',') if part.strip()]
        elif not isinstance(value, list):
            value = [value]
        object_ids = []
        for item in value:
            object_id = MongoAPI._extract_object_id(item)
            if object_id is not None:
                object_ids.append(object_id)
        return object_ids

    @staticmethod
    def _format_object_id_list(value):
        if value is None or value == '':
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        return [str(value)]

    @staticmethod
    def _resolve_assigned_projects(org_id, assigned_project_ids):
        object_ids = MongoAPI._extract_object_id_list(assigned_project_ids)
        project_id_strings = [str(project_id) for project_id in object_ids]
        project_names = []

        for project_id in object_ids:
            try:
                project = Project.objects.get(id=project_id, org_id=int(org_id))
                project_names.append(project.name or '')
            except Project.DoesNotExist:
                project_names.append('')

        return project_id_strings, project_names

    @staticmethod
    def _parse_lead_settings_info(info):
        if info is None or info == '':
            return {}
        if isinstance(info, dict):
            return dict(info)
        if isinstance(info, str):
            try:
                parsed = json.loads(info)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                return {'field_type': info}
        return {}

    @staticmethod
    def _merge_lead_settings_info(existing_info, incoming_info):
        existing = MongoAPI._parse_lead_settings_info(existing_info)
        incoming = MongoAPI._parse_lead_settings_info(incoming_info)

        if not incoming:
            return json.dumps(existing) if existing else (existing_info or '')

        merged = {**existing, **incoming}
        field_type = incoming.get('field_type') or existing.get('field_type', '')
        is_dropdown = field_type in ('dropdown-single', 'dropdown-multiple')

        if is_dropdown:
            incoming_options = incoming.get('options')
            if incoming_options is None or (
                isinstance(incoming_options, list) and len(incoming_options) == 0
            ):
                if existing.get('options'):
                    merged['options'] = existing['options']

        for key in ('currency', 'placeholder', 'label', 'required'):
            if key not in incoming and existing.get(key):
                merged[key] = existing[key]

        return json.dumps(merged) if merged else ''

    @staticmethod
    def _normalize_lead_settings_info(info):
        if info is None or info == '':
            return ''
        if isinstance(info, dict):
            return json.dumps(info)
        return str(info)

    @staticmethod
    def _map_lead_payment_input(data1):
        if 'payment' in data1 and 'payment_terms' not in data1:
            data1['payment_terms'] = data1['payment']
        data1.pop('payment', None)

    @staticmethod
    def _apply_lead_payment_output(settings):
        payment_terms = settings.get('payment_terms')
        if payment_terms and not settings.get('payment'):
            if isinstance(payment_terms, dict) and '$oid' in payment_terms:
                settings['payment'] = payment_terms['$oid']
            else:
                settings['payment'] = str(payment_terms)

    @staticmethod
    def _sanitize_object_id_fields(data, field_names):
        for field in field_names:
            if field not in data:
                continue
            object_id = MongoAPI._extract_object_id(data[field])
            if object_id is None:
                data.pop(field, None)
            else:
                data[field] = str(object_id)

    @staticmethod
    def lead_submit(org_id, user_id, data1):
        try:
            data1['create_by'] = user_id
            data1.pop('create_date', None)
            data1['org_id'] = org_id
            data1['phone'] = str(data1.get('phone') or '')
            data1['alternate_phone'] = str(data1.get('alternate_phone') or '')
            data1['whatsapp_no'] = str(data1.get('whatsapp_no') or '')
            data1['referred_mobile_no'] = str(data1.get('referred_mobile_no') or '')

            if 'date_of_birth' in data1 and 'dob' not in data1:
                data1['dob'] = data1['date_of_birth']
            if 'source_of_deal' in data1 and 'sod' not in data1:
                data1['sod'] = data1['source_of_deal']
            MongoAPI._map_lead_payment_input(data1)
            data1['sod'] = str(data1.get('sod') or '')

            parsed_dob = MongoAPI._parse_date_value(data1.get('dob'))
            if parsed_dob is not None:
                data1['dob'] = parsed_dob.strftime(DATE_FORMAT4)

            if 'contact_name' in data1:
                del data1['contact_name']

            if 'customer_requirement' in data1:
                data1['customer_requirement'] = [
                    str(object_id)
                    for object_id in MongoAPI._extract_object_id_list(data1['customer_requirement'])
                ]

            MongoAPI._sanitize_object_id_fields(data1, [
                'lead_status', 'customer_type',
                'source', 'industry', 'application', 'assigned_to',
                'payment_terms',
            ])

            branch_id = MongoAPI._resolve_lead_branch_id(org_id, data1, user_id)
            if branch_id is not None:
                data1['branch_id'] = branch_id

            lead = Lead.from_json(json.dumps(data1))
            lead.save()
            return str(lead.id)
        except NotUniqueError:
            return '0'

    @staticmethod
    def getNumberingSettings(module, org_id):
        try:
            numbering = Numbering.objects.get(org_id=int(org_id), module=module)
            return {
                'id': str(numbering.id),
                'org_id': numbering.org_id,
                'module': numbering.module,
                'prefix': numbering.prefix,
                'sequence': numbering.sequence,
            }
        except Numbering.DoesNotExist:
            return None

    @staticmethod
    def getNumberingSettings2(module, org_id):
        try:
            numbering = Numbering(
                org_id=int(org_id),
                module=module,
                prefix='LD',
                sequence=1,
            )
            numbering.save()
            return str(numbering.id)
        except Exception:
            return None

    @staticmethod
    def numberingUpdate(numbering_id, next_sequence):
        try:
            Numbering.objects(id=ObjectId(numbering_id)).update_one(
                sequence=int(next_sequence),
            )
            return 'Yes'
        except (InvalidId, Exception):
            return 'No'

    # @staticmethod
    # def get_lead_Details(org_id, lead_id, user_id):
    #     try:
    #         lead = Lead.objects.get(
    #             id=ObjectId(lead_id),
    #             org_id=int(org_id),
    #             status='active',
    #         )
    #         return lead.to_mongo().to_dict()
    #     except (Lead.DoesNotExist, InvalidId):
    #         return {}

    @staticmethod
    def getUserDetails(org_id, user_id):
        if not user_id:
            return {}
        user_id = MongoAPI._extract_object_id(user_id)
        if user_id is None:
            return {}
        try:
            user = User.objects.get(id=user_id, org_id=int(org_id))
            data = MongoAPI._user_dict(user)
            data['user_id'] = data['id']
            return data
        except (User.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def get_profile_details(org_id, user_id):
        try:
            user = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
            data = MongoAPI._user_dict(user)

            branch_ref = getattr(user, 'branch_id', None)
            if branch_ref:
                branch_oid = MongoAPI._parse_user_branch_id(branch_ref, org_id)
                if branch_oid:
                    branch = Branch.objects(
                        org_id=int(org_id), id=branch_oid,
                    ).first()
                    if branch:
                        data['branch_name'] = branch.name
                        data['branch_id'] = str(branch_oid)

            org = Organization.objects.filter(org_id=int(org_id)).first()
            if org:
                data['organization_name'] = org.organization_name

            return data
        except (User.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def update_user_profile(org_id, user_id, name, phone=None, profile_image=None):
        try:
            user = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
            name = (name or '').strip()
            updates = {
                'name': name,
                'phone': str(phone or ''),
                'modify_date': datetime.datetime.now(timezone('UTC')),
            }
            if profile_image is not None:
                updates['profile_image'] = profile_image
            user.update(**updates)

            # Keep organization.user_name in sync for the account owner
            org = Organization.objects.filter(org_id=int(org_id)).first()
            if org and name and (not getattr(org, 'user_name', None) or org.email == user.email):
                org.user_name = name
                org.save()

            return MongoAPI.get_profile_details(org_id, user_id)
        except (User.DoesNotExist, InvalidId):
            return None

    @staticmethod
    def update_organization_profile(org_id, user_id, user_name='', organization_name=''):
        try:
            user = User.objects.get(id=ObjectId(user_id), org_id=int(org_id))
            org = Organization.objects.filter(org_id=int(org_id)).first()
            if not org:
                return None

            user_name = (user_name or '').strip()
            organization_name = (organization_name or '').strip()

            if user_name:
                user.update(
                    name=user_name,
                    modify_date=datetime.datetime.now(timezone('UTC')),
                )
                if org.email == user.email:
                    org.user_name = user_name

            if organization_name:
                org.organization_name = organization_name

            org.save()
            return MongoAPI.get_profile_details(org_id, user_id)
        except (User.DoesNotExist, InvalidId):
            return None

    @staticmethod
    def get_user_mail_signature(user_id):
        try:
            user = User.objects.get(id=ObjectId(user_id), status='active')
            return getattr(user, 'mail_signature', '') or ''
        except (User.DoesNotExist, InvalidId):
            return ''

    @staticmethod
    def update_user_mail_signature(user_id, signature):
        try:
            User.objects(id=ObjectId(user_id)).update_one(
                mail_signature=signature or '',
                modify_date=datetime.datetime.now(timezone('UTC')),
            )
            return True
        except Exception:
            return False

    @staticmethod
    def emailSubmit(org_id, user_id, data1, email_id, attachment):
        return MongoAPI.emailSubmit_signup(org_id, user_id, data1, email_id, attachment)

    @staticmethod
    def user_activity(
        org_id,
        user_id,
        from_data,
        to_data,
        category_name,
        action,
        associate_to,
        associate_id,
        via,
        extra_info,
        text_info,
        title,
    ):
        try:
            activity = UserActivity(
                org_id=int(org_id),
                user_id=ObjectId(user_id),
                category_name=category_name,
                action=action,
                associate_to=associate_to,
                associate_id=associate_id,
                via=via,
                extra_info=extra_info or {},
                text_info=text_info,
                title=title,
                from_data=from_data,
                to_data=to_data,
                create_date=datetime.datetime.now(timezone('UTC')),
            )
            activity.save()
            return str(activity.id)
        except (InvalidId, Exception):
            return None

    @staticmethod
    def commontimeset(current_user, org_id):
        try:
            if current_user:
                user = MongoAPI.authorizationCheck(current_user)
                if user.get('time_zone'):
                    timezone_name = user['time_zone']
                else:
                    timezone_name = 'Asia/Kolkata'
                return MongoAPI.offsettimezone(timezone_name)
            return 5.5
        except Exception:
            return 5.5

    @staticmethod
    def offsettimezone(timezone_name):
        timezone_offsets = {
            'Asia/Kolkata': 5.5,
            'UTC': 0,
            'America/New_York': -5,
            'Europe/London': 0,
        }
        return timezone_offsets.get(timezone_name, 5.5)

    @staticmethod
    def lead_statusactive_statuses_objectId(org_id):
        try:
            fields = Fields.objects(
                type='lead_status',
                org_id=int(org_id),
                active=1,
            )
            return [field.id for field in fields]
        except Exception:
            return []

    @staticmethod
    def lead_count(org_id):
        try:
            return Lead.objects(org_id=org_id, status='active').count()
        except NotUniqueError:
            return 0

    @staticmethod
    def _build_lead_base_filter(org_id, current_user, branch_id=None, filter_data=None):
        match_filter = {
            'org_id': int(org_id),
            'status': 'active',
        }
        actor = MongoAPI.getUserDetails(org_id, current_user)
        explicit_branch = MongoAPI._branch_ids_from_filter_data(filter_data or [])
        if branch_id not in (None, '', 'all') or explicit_branch:
            if not MongoAPI._apply_branch_scope_to_match_filter(
                match_filter,
                actor,
                filter_data=filter_data,
                branch_id=branch_id if branch_id not in (None, '', 'all') else None,
                org_id=org_id,
                include_unset_branch=False,
            ):
                match_filter['branch_id'] = {'$in': []}
        elif not MongoAPI._apply_branch_scope_to_match_filter(
            match_filter, actor, org_id=org_id, include_unset_branch=True,
        ):
            match_filter['branch_id'] = {'$in': []}
        MongoAPI._apply_lead_visibility_filter(match_filter, org_id, current_user)
        return match_filter

    @staticmethod
    def _lead_metrics_month_range():
        today = datetime.datetime.today()
        first_day = datetime.datetime(today.year, today.month, 1)
        next_month = today.month % 12 + 1
        next_month_year = today.year if next_month > 1 else today.year + 1
        last_day = datetime.datetime(next_month_year, next_month, 1) - timedelta(days=1)
        last_day = last_day.replace(hour=23, minute=59, second=59, microsecond=999999)
        return first_day, last_day

    @staticmethod
    def lead_metrics(org_id, current_user, aging_days=7, branch_id=None):
        empty = {
            'active_leads': 0,
            'aging_leads': 0,
            'aging_days': int(aging_days),
            'followup_today': 0,
            'followups_this_week': 0,
            'pending_followups': 0,
            'created_this_week': 0,
            'converted_this_week': 0,
            'created_this_month': 0,
            'converted_this_month': 0,
        }
        try:
            base_filter = MongoAPI._build_lead_base_filter(
                org_id, current_user, branch_id=branch_id,
            )
            active_leads = Lead.objects(__raw__=base_filter).count()

            aging_filter = dict(base_filter)
            aging_cutoff = datetime.datetime.now() - timedelta(days=int(aging_days))
            aging_filter['create_date'] = {'$lt': aging_cutoff}
            aging_leads = Lead.objects(__raw__=aging_filter).count()

            date_from, date_to = DateFilter.date_range_filter('today', current_user, org_id)
            followup_today = 0
            if date_from and date_to:
                task_filter = {
                    'org_id': int(org_id),
                    'status': 'Open',
                    'associate_to': 'lead',
                    'date': {'$gte': date_from, '$lte': date_to},
                }
                lead_ids = Crm_tasks.objects(__raw__=task_filter).distinct('associate_id')
                if lead_ids:
                    followup_filter = dict(base_filter)
                    followup_filter['_id'] = {'$in': lead_ids}
                    followup_today = Lead.objects(__raw__=followup_filter).count()

            week_start, week_end = DateFilter.date_range_filter(
                'this_week', current_user, org_id,
            )
            followups_this_week = 0
            if week_start and week_end:
                week_task_filter = {
                    'org_id': int(org_id),
                    'status': 'Open',
                    'associate_to': 'lead',
                    'date': {'$gte': week_start, '$lte': week_end},
                }
                week_lead_ids = Crm_tasks.objects(__raw__=week_task_filter).distinct(
                    'associate_id',
                )
                if week_lead_ids:
                    week_followup_filter = dict(base_filter)
                    week_followup_filter['_id'] = {'$in': week_lead_ids}
                    followups_this_week = Lead.objects(__raw__=week_followup_filter).count()

            pending_followups = 0
            today_start, _ = DateFilter.date_range_filter('today', current_user, org_id)
            if today_start:
                overdue_task_filter = {
                    'org_id': int(org_id),
                    'status': 'Open',
                    'associate_to': 'lead',
                    'date': {'$lt': today_start},
                }
                overdue_lead_ids = Crm_tasks.objects(__raw__=overdue_task_filter).distinct(
                    'associate_id',
                )
                if overdue_lead_ids:
                    overdue_followup_filter = dict(base_filter)
                    overdue_followup_filter['_id'] = {'$in': overdue_lead_ids}
                    pending_followups = Lead.objects(__raw__=overdue_followup_filter).count()

            created_week_filter = dict(base_filter)
            if week_start and week_end:
                created_week_filter['create_date'] = {'$gte': week_start, '$lte': week_end}
            created_this_week = Lead.objects(__raw__=created_week_filter).count()

            converted_week_filter = {
                'org_id': int(org_id),
                'status': 'converted',
            }
            if week_start and week_end:
                converted_week_filter['converted_date'] = {'$gte': week_start, '$lte': week_end}
            if 'branch_id' in base_filter:
                converted_week_filter['branch_id'] = base_filter['branch_id']
            MongoAPI._apply_lead_visibility_filter(converted_week_filter, org_id, current_user)
            converted_this_week = Lead.objects(__raw__=converted_week_filter).count()

            first_day, last_day = MongoAPI._lead_metrics_month_range()
            created_month_filter = dict(base_filter)
            created_month_filter['create_date'] = {'$gte': first_day, '$lte': last_day}
            created_this_month = Lead.objects(__raw__=created_month_filter).count()

            converted_month_filter = {
                'org_id': int(org_id),
                'status': 'converted',
                'converted_date': {'$gte': first_day, '$lte': last_day},
            }
            if 'branch_id' in base_filter:
                converted_month_filter['branch_id'] = base_filter['branch_id']
            MongoAPI._apply_lead_visibility_filter(converted_month_filter, org_id, current_user)
            converted_this_month = Lead.objects(__raw__=converted_month_filter).count()

            return {
                'active_leads': active_leads,
                'aging_leads': aging_leads,
                'aging_days': int(aging_days),
                'followup_today': followup_today,
                'followups_this_week': followups_this_week,
                'pending_followups': pending_followups,
                'created_this_week': created_this_week,
                'converted_this_week': converted_this_week,
                'created_this_month': created_this_month,
                'converted_this_month': converted_this_month,
            }
        except Exception:
            return empty

    @staticmethod
    def _apply_lead_list_object_id_filter(match_filter, filter_key, selected_values, indicator):
        object_ids = []
        for value in selected_values:
            if value == 'active' and filter_key == 'lead_status':
                object_ids.extend(MongoAPI.lead_statusactive_statuses_objectId(match_filter.get('org_id')))
                continue
            try:
                object_ids.append(ObjectId(value))
            except InvalidId:
                continue
        if not object_ids:
            return
        if indicator == 'is':
            match_filter[filter_key] = {'$in': object_ids}
        else:
            match_filter[filter_key] = {'$nin': object_ids}

    @staticmethod
    def _apply_lead_list_filters(match_filter, filter_data, current_user, org_id):
        for data in filter_data:
            if 'field' not in data:
                continue

            filter_key = data['field']
            field_origin = data.get('field_orgin', 'default')
            indicator = data.get('indictor', 'is')
            selected_values = data.get('selected_values') or []

            if field_origin != 'default':
                if field_origin == 'custom_dropdown':
                    values = list(selected_values)
                    key = 'custom_fields_value.single_value'
                    match_filter[key] = {'$in': values} if indicator == 'is' else {'$nin': values}
                elif field_origin == 'custom_multiselect':
                    values = list(selected_values)
                    key = 'custom_fields_value.multiple_value'
                    match_filter[key] = {'$in': values} if indicator == 'is' else {'$nin': values}
                continue

            if filter_key == 'create_date' and selected_values:
                for option in selected_values:
                    custom_start = data.get('custom_start')
                    custom_end = data.get('custom_end')
                    date_from, date_to = DateFilter.date_range_filter(
                        option,
                        current_user,
                        org_id,
                        custom_start=custom_start,
                        custom_end=custom_end,
                    )
                    if date_from and date_to:
                        if indicator == 'is':
                            match_filter['create_date'] = {'$gte': date_from, '$lte': date_to}
                        else:
                            match_filter['create_date'] = {
                                '$not': {'$gte': date_from, '$lte': date_to},
                            }
            elif filter_key == 'target_date' and selected_values:
                for option in selected_values:
                    date_from, date_to = DateFilter.date_range_filter(option, current_user, org_id)
                    if date_from and date_to:
                        if indicator == 'is':
                            match_filter['target_date'] = {'$gte': date_from, '$lte': date_to}
                        else:
                            match_filter['target_date'] = {
                                '$not': {'$gte': date_from, '$lte': date_to},
                            }
            elif filter_key == 'lead_status' and selected_values:
                MongoAPI._apply_lead_list_object_id_filter(
                    match_filter, filter_key, selected_values, indicator,
                )
            elif filter_key == 'active_leads' and selected_values and 'true' in selected_values:
                if indicator == 'is':
                    match_filter['status'] = 'active'
                else:
                    match_filter['status'] = {'$ne': 'active'}
            elif filter_key == 'date_aging_filter' and selected_values:
                days_threshold = int(selected_values[0]) if str(selected_values[0]).isdigit() else 7
                aging_date = datetime.datetime.now() - timedelta(days=days_threshold)
                if indicator == 'is':
                    match_filter['create_date'] = {'$lt': aging_date}
                else:
                    match_filter['create_date'] = {'$gte': aging_date}
            elif filter_key == 'today_followup' and selected_values and 'true' in selected_values:
                date_from, date_to = DateFilter.date_range_filter('today', current_user, org_id)
                if date_from and date_to:
                    if indicator == 'is':
                        match_filter['target_date'] = {'$gte': date_from, '$lte': date_to}
                    else:
                        match_filter['target_date'] = {
                            '$not': {'$gte': date_from, '$lte': date_to},
                        }
            elif filter_key == 'overdue_followup' and selected_values and 'true' in selected_values:
                today_start, _ = DateFilter.date_range_filter('today', current_user, org_id)
                if today_start:
                    if indicator == 'is':
                        match_filter['target_date'] = {'$lt': today_start}
                    else:
                        match_filter['target_date'] = {'$gte': today_start}
            elif filter_key == 'created_this_month' and selected_values and 'true' in selected_values:
                today = datetime.datetime.today()
                first_day = datetime.datetime(today.year, today.month, 1)
                next_month = today.month % 12 + 1
                next_month_year = today.year if next_month > 1 else today.year + 1
                last_day = datetime.datetime(next_month_year, next_month, 1) - timedelta(days=1)
                last_day = last_day.replace(hour=23, minute=59, second=59, microsecond=999999)
                if indicator == 'is':
                    match_filter['create_date'] = {'$gte': first_day, '$lte': last_day}
                else:
                    match_filter['create_date'] = {'$not': {'$gte': first_day, '$lte': last_day}}
            elif filter_key == 'converted' and selected_values and 'true' in selected_values:
                today = datetime.datetime.today()
                first_day = datetime.datetime(today.year, today.month, 1)
                if today.month == 12:
                    next_month = 1
                    next_month_year = today.year + 1
                else:
                    next_month = today.month + 1
                    next_month_year = today.year
                last_day = datetime.datetime(next_month_year, next_month, 1) - timedelta(seconds=1)
                if indicator == 'is':
                    match_filter['status'] = 'converted'
                    match_filter['converted_date'] = {'$gte': first_day, '$lte': last_day}
                else:
                    match_filter['$or'] = [
                        {'status': {'$ne': 'converted'}},
                        {'converted_date': {'$lt': first_day}},
                        {'converted_date': {'$gt': last_day}},
                    ]
            elif filter_key in ('customer_type', 'customer_requirement', 'source') and selected_values:
                MongoAPI._apply_lead_list_object_id_filter(
                    match_filter, filter_key, selected_values, indicator,
                )
            elif filter_key in ('branch_id', 'branch') and selected_values:
                MongoAPI._apply_integer_list_filter(
                    match_filter, 'branch_id', selected_values, indicator, org_id,
                )
            elif filter_key == 'create_by' and selected_values:
                MongoAPI._apply_lead_list_object_id_filter(
                    match_filter, filter_key, selected_values, indicator,
                )
            elif selected_values:
                MongoAPI._apply_lead_list_object_id_filter(
                    match_filter, filter_key, selected_values, indicator,
                )

    @staticmethod
    def _deny_assigned_to_filter(match_filter):
        match_filter['assigned_to'] = ObjectId('000000000000000000000000')

    @staticmethod
    def _team_member_user_ids(org_id, user_details):
        """User ObjectIds considered teammates (same branch), including the actor."""
        actor_oid = MongoAPI._extract_object_id(
            (user_details or {}).get('id') or (user_details or {}).get('_id'),
        )
        if actor_oid is None:
            return []

        branch_oid = MongoAPI._parse_user_branch_id(
            (user_details or {}).get('branch_id'), org_id,
        )
        if branch_oid is None:
            return [actor_oid]

        member_ids = [
            user.id
            for user in User.objects(
                org_id=int(org_id),
                status='active',
                branch_id=branch_oid,
            ).only('id')
        ]
        if actor_oid not in member_ids:
            member_ids.append(actor_oid)
        return member_ids

    @staticmethod
    def _intersect_assigned_to_filter(match_filter, allowed_ids):
        """Constrain assigned_to to allowed_ids, intersecting any existing filter."""
        if not allowed_ids:
            MongoAPI._deny_assigned_to_filter(match_filter)
            return

        allowed = list(allowed_ids)
        existing = match_filter.get('assigned_to')
        if existing is None:
            if len(allowed) == 1:
                match_filter['assigned_to'] = allowed[0]
            else:
                match_filter['assigned_to'] = {'$in': allowed}
            return

        if isinstance(existing, dict) and '$in' in existing:
            existing_ids = {
                oid for oid in (MongoAPI._extract_object_id(v) for v in existing['$in'])
                if oid is not None
            }
        elif isinstance(existing, dict) and '$nin' in existing:
            excluded = {
                oid for oid in (MongoAPI._extract_object_id(v) for v in existing['$nin'])
                if oid is not None
            }
            existing_ids = set(allowed) - excluded
        else:
            existing_oid = MongoAPI._extract_object_id(existing)
            existing_ids = {existing_oid} if existing_oid is not None else set()

        intersection = [oid for oid in allowed if oid in existing_ids]
        if not intersection:
            MongoAPI._deny_assigned_to_filter(match_filter)
        elif len(intersection) == 1:
            match_filter['assigned_to'] = intersection[0]
        else:
            match_filter['assigned_to'] = {'$in': intersection}

    @staticmethod
    def _apply_lead_visibility_filter(match_filter, org_id, current_user):
        """Apply lead visibility based on role view-scope permissions.

        - Super Admin: all leads in existing branch/org scope
        - lead_view_all: all leads in existing branch/org scope
        - lead_view_team: leads assigned to users in the same branch (team)
        - lead_view_own: only leads assigned to the current user
        - none: deny (empty result)
        """
        user_details = MongoAPI.getUserDetails(org_id, current_user)
        if not user_details:
            MongoAPI._deny_assigned_to_filter(match_filter)
            return

        role_details = MongoAPI.get_user_role_data(org_id, current_user)
        if is_super_admin_user(user_details, role_details):
            return

        lead_view_all = int(role_details.get('lead_view_all', 0) or 0)
        lead_view_team = int(role_details.get('lead_view_team', 0) or 0)
        lead_view_own = int(role_details.get('lead_view_own', 0) or 0)

        if lead_view_all == 1:
            return
        if lead_view_team == 1:
            MongoAPI._intersect_assigned_to_filter(
                match_filter,
                MongoAPI._team_member_user_ids(org_id, user_details),
            )
            return
        if lead_view_own == 1:
            actor_oid = MongoAPI._extract_object_id(current_user)
            MongoAPI._intersect_assigned_to_filter(
                match_filter,
                [actor_oid] if actor_oid is not None else [],
            )
            return
        MongoAPI._deny_assigned_to_filter(match_filter)

    @staticmethod
    def _lead_no_search_candidates(lead_no):
        raw = (lead_no or '').strip()
        if not raw:
            return []

        candidates = {raw}
        match = re.match(r'^([A-Za-z]+)[\s\-/]+(\d+)$', raw, re.I)
        if match:
            prefix = match.group(1).upper()
            sequence = match.group(2)
            for separator in ('/', '-', ' '):
                candidates.add(f'{prefix}{separator}{sequence}')
        return list(candidates)

    @staticmethod
    def get_lead_id_by_lead_no(org_id, lead_no, current_user):
        candidates = MongoAPI._lead_no_search_candidates(lead_no)
        if not candidates:
            return None

        for candidate in candidates:
            match_filter = {
                'org_id': int(org_id),
                'status': 'active',
                'lead_no': {'$regex': f'^{re.escape(candidate)}$', '$options': 'i'},
            }
            MongoAPI._apply_lead_visibility_filter(match_filter, org_id, current_user)
            lead = Lead.objects(__raw__=match_filter).only('id').first()
            if lead:
                return str(lead.id)
        return None

    @staticmethod
    def search_leads_for_chat(org_id, search_text, current_user, limit=5):
        text = (search_text or '').strip()
        if not text:
            return []

        match_filter = {
            'org_id': int(org_id),
            'status': 'active',
        }
        MongoAPI._apply_lead_visibility_filter(match_filter, org_id, current_user)

        or_conditions = []
        digits = re.sub(r'\D', '', text)
        if len(digits) >= 7:
            phone_regex = {'$regex': re.escape(digits), '$options': 'i'}
            or_conditions.extend([
                {'phone': phone_regex},
                {'alternate_phone': phone_regex},
                {'whatsapp_no': phone_regex},
            ])

        if '@' in text:
            or_conditions.append({'email': {'$regex': re.escape(text), '$options': 'i'}})

        name_regex = MongoAPI._flexible_search_regex(text) or {
            '$regex': re.escape(text), '$options': 'i',
        }
        or_conditions.extend([
            {'name': name_regex},
            {'company_name': name_regex},
            {'lead_no': name_regex},
            {'project_name': name_regex},
        ])

        match_filter['$or'] = or_conditions
        leads = Lead.objects(__raw__=match_filter).only('id', 'name', 'lead_no', 'phone', 'company_name')[:limit]
        return [
            {
                'id': str(lead.id),
                'name': lead.name or '',
                'lead_no': lead.lead_no or '',
                'phone': lead.phone or '',
                'company_name': lead.company_name or '',
            }
            for lead in leads
        ]

    @staticmethod
    def get_project_id_by_project_no(org_id, project_no, current_user):
        candidates = MongoAPI._lead_no_search_candidates(project_no)
        if not candidates:
            return None

        for candidate in candidates:
            project = Project.objects(
                org_id=int(org_id),
                project_no={'$regex': f'^{re.escape(candidate)}$', '$options': 'i'},
            ).only('id').first()
            if project:
                return str(project.id)
        return None

    @staticmethod
    def _normalize_numeric_value(text):
        cleaned = re.sub(r'[^\d.]', '', str(text or ''))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def search_projects_by_price_for_chat(org_id, price_value, current_user, limit=5):
        price_value = MongoAPI._normalize_numeric_value(price_value)
        if not price_value or price_value <= 0:
            return []

        tolerance = max(1.0, price_value * 0.001)
        low = price_value - tolerance
        high = price_value + tolerance
        price_text = str(int(price_value)) if price_value == int(price_value) else str(price_value)

        projects = Project.objects(__raw__={
            'org_id': int(org_id),
            '$or': [
                {'price_per_sqft': {'$gte': low, '$lte': high}},
                {
                    'price_range_min': {'$lte': high},
                    'price_range_max': {'$gte': low},
                },
                {'price_per_cent': {'$regex': re.escape(price_text), '$options': 'i'}},
            ],
        }).only(
            'id', 'name', 'project_no', 'location', 'status',
            'price_per_sqft', 'price_per_cent',
        )[:limit]

        matches = []
        seen_ids = set()
        for project in projects:
            project_id = str(project.id)
            if project_id in seen_ids:
                continue

            matched = False
            sqft = project.price_per_sqft or 0
            if sqft and low <= sqft <= high:
                matched = True
            cent_value = MongoAPI._normalize_numeric_value(project.price_per_cent)
            if cent_value and low <= cent_value <= high:
                matched = True
            if matched:
                seen_ids.add(project_id)
                matches.append({
                    'id': project_id,
                    'name': project.name or '',
                    'project_no': project.project_no or '',
                    'location': project.location or '',
                    'status': project.status or '',
                    'price_per_sqft': project.price_per_sqft or 0,
                    'price_per_cent': project.price_per_cent or '',
                })
        return matches[:limit]

    @staticmethod
    def _flexible_search_regex(text):
        text = (text or '').strip()
        if not text:
            return None
        parts = [re.escape(part) for part in text.split() if part]
        if not parts:
            return None
        if len(parts) == 1:
            return {'$regex': parts[0], '$options': 'i'}
        return {'$regex': r'\s+'.join(parts), '$options': 'i'}

    @staticmethod
    def get_leads_for_project_for_chat(org_id, project_id, current_user, limit=50):
        try:
            project = Project.objects.get(id=ObjectId(project_id), org_id=int(org_id))
        except (Project.DoesNotExist, InvalidId):
            return []

        project_oid = ObjectId(project_id)
        project_name = (project.name or '').strip()
        leads_by_id = {}

        match_filter = {
            'org_id': int(org_id),
            'status': 'active',
        }
        MongoAPI._apply_lead_visibility_filter(match_filter, org_id, current_user)

        or_conditions = [{'suggested_projects': project_oid}]
        name_regex = MongoAPI._flexible_search_regex(project_name)
        if name_regex:
            or_conditions.append({'project_name': name_regex})

        match_filter['$or'] = or_conditions
        direct_leads = Lead.objects(__raw__=match_filter).only(
            'id', 'name', 'lead_no', 'phone', 'company_name', 'location', 'project_name',
        )
        for lead in direct_leads:
            lead_id = str(lead.id)
            leads_by_id[lead_id] = {
                'id': lead_id,
                'name': lead.name or '',
                'lead_no': lead.lead_no or '',
                'phone': lead.phone or '',
                'company_name': lead.company_name or '',
                'location': lead.location or '',
                'project_name': lead.project_name or '',
                'link_type': 'linked',
            }

        for item in MongoAPI.project_match_leads(org_id, project_id, current_user):
            lead_id = item.get('_id')
            if not lead_id or lead_id in leads_by_id:
                continue
            try:
                lead = Lead.objects.get(id=ObjectId(lead_id), org_id=int(org_id))
            except (Lead.DoesNotExist, InvalidId):
                continue
            leads_by_id[lead_id] = {
                'id': lead_id,
                'name': lead.name or item.get('name') or '',
                'lead_no': lead.lead_no or '',
                'phone': lead.phone or item.get('phone') or '',
                'company_name': lead.company_name or '',
                'location': item.get('location') or lead.location or '',
                'project_name': lead.project_name or '',
                'link_type': 'matched',
                'match_score': item.get('match_score'),
                'match_reasons': item.get('match_reasons') or [],
            }

        return list(leads_by_id.values())[:limit]

    @staticmethod
    def search_projects_for_chat(org_id, search_text, current_user, limit=5):
        text = (search_text or '').strip()
        if not text:
            return []

        search_regex = MongoAPI._flexible_search_regex(text)
        if not search_regex:
            return []

        projects = Project.objects(__raw__={
            'org_id': int(org_id),
            '$or': [
                {'name': search_regex},
                {'location': search_regex},
                {'project_no': search_regex},
                {'area_locality': search_regex},
                {'dtcp_number': search_regex},
                {'rera_number': search_regex},
                {'price_per_cent': search_regex},
            ],
        }).only('id', 'name', 'project_no', 'location', 'status')[:limit]

        return [
            {
                'id': str(project.id),
                'name': project.name or '',
                'project_no': project.project_no or '',
                'location': project.location or '',
                'status': project.status or '',
            }
            for project in projects
        ]

    @staticmethod
    def search_bookings_for_chat(org_id, search_text, current_user, limit=5):
        text = (search_text or '').strip()
        if not text:
            return []

        match_filter = {'org_id': int(org_id), 'status': 'active'}
        MongoAPI._apply_booking_visibility_filter(match_filter, org_id, current_user)
        escaped = re.escape(text)
        search_regex = {'$regex': escaped, '$options': 'i'}
        match_filter['$or'] = [
            {'customer_name': search_regex},
            {'receipt_number': search_regex},
            {'project_name': search_regex},
            {'unit_no': search_regex},
        ]

        bookings = Booking.objects(__raw__=match_filter).only(
            'id', 'customer_name', 'receipt_number', 'project_name', 'unit_no', 'amount_paid',
        )[:limit]
        return [
            {
                'id': str(booking.id),
                'customer_name': booking.customer_name or '',
                'receipt_number': booking.receipt_number or '',
                'project_name': booking.project_name or '',
                'unit_no': booking.unit_no or '',
                'amount_paid': booking.amount_paid or 0,
            }
            for booking in bookings
        ]

    @staticmethod
    def get_crm_chat_snapshot(org_id, current_user):
        org_id = int(org_id)
        today = datetime.datetime.now().strftime('%d/%m/%Y')
        followups = MongoAPI.all_crm_tasks_calender(
            org_id, current_user, today, today, None, 'Open',
        )
        followups = (Uid.fix_array(followups) or [])[:5]

        projects, _ = MongoAPI.project_list(
            org_id, current_user, 5, 1, {}, -1, 'create_date', '',
        )
        booking_data = MongoAPI.booking_list(
            org_id, current_user, 5, 1, {}, -1, 'booking_date', '', None, None, None,
        )
        bookings = (booking_data or {}).get('rows') or []

        return {
            'lead_metrics': MongoAPI.lead_metrics(org_id, current_user),
            'project_metrics': MongoAPI.project_metrics(org_id, current_user),
            'booking_metrics': MongoAPI.booking_metrics(org_id, current_user),
            'recent_projects': [
                {
                    'name': item.get('name', ''),
                    'project_no': item.get('project_no', ''),
                    'location': item.get('location', ''),
                    'available_units': item.get('available_units', 0),
                    'total_units': item.get('total_units', 0),
                }
                for item in (projects or [])[:5]
            ],
            'recent_bookings': [
                {
                    'customer_name': item.get('customer_name', ''),
                    'receipt_number': item.get('receipt_number', ''),
                    'project_name': item.get('project_name', ''),
                    'unit_no': item.get('unit_no', ''),
                    'amount_paid': item.get('amount_paid', 0),
                }
                for item in bookings[:5]
            ],
            'followups_today': [
                {
                    'description': item.get('description') or item.get('task_name', ''),
                    'date': item.get('date', ''),
                    'associate_to': item.get('associate_to', ''),
                }
                for item in followups
            ],
        }

    @staticmethod
    def _format_lead_list_item(item, org_id, current_user):
        settings = defaultdict(list)
        for field_name, field_value in item.items():
            settings[field_name] = field_value

            if field_name == 'currency_symbol' and field_value:
                for lookup_item in field_value:
                    settings['currency_symbol'] = lookup_item.get('symbol', '')
            elif field_name == 'currency_name' and field_value:
                for lookup_item in field_value:
                    settings[field_name] = lookup_item.get('name', '')
            elif field_name == 'company_detail' and field_value:
                for lookup_item in field_value:
                    settings['company_name'] = lookup_item.get('company_name', '')
            elif field_name == 'contact_detail' and field_value:
                for lookup_item in field_value:
                    settings['contact_name'] = lookup_item.get('contact_name', '')
            elif field_name == 'assigned' and field_value:
                for lookup_item in field_value:
                    settings['assigned_to_name'] = lookup_item.get('name', '')
                    assignee_id = lookup_item.get('_id')
                    if assignee_id is not None:
                        settings['assigned_to'] = str(assignee_id)
            elif field_name == 'create_date' and field_value:
                create_date1 = str(field_value).rstrip('Z')
                try:
                    utc_date = datetime.datetime.strptime(create_date1, DATE_FORMAT).strftime(DATE_FORMAT4)
                    create_date_obj = datetime.datetime.strptime(create_date1, DATE_FORMAT)
                except ValueError:
                    utc_date = datetime.datetime.strptime(create_date1, DATE_FORMAT4).strftime(DATE_FORMAT4)
                    create_date_obj = datetime.datetime.strptime(create_date1, DATE_FORMAT4)
                settings['create_date_utc'] = utc_date
                create_date = create_date_obj.strftime(DATE_FORMAT1)
                settings['create_date'] = create_date
                settings['date_aging'] = calculate_age(create_date)
            elif field_name == 'target_date' and field_value:
                end_date1 = field_value
                offset = MongoAPI.commontimeset(current_user, org_id)
                utc_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                settings['create_date_utc'] = utc_date
                end_date1 = end_date1 + timedelta(hours=offset)
                target_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                settings['target_date'] = target_date
                settings['end_time'] = end_time
                settings['date_aging'] = calculate_age(
                    datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1),
                )
            elif field_name == 'lead_status_name' and field_value:
                for lookup_item in field_value:
                    settings['lead_status_name'] = lookup_item.get('name', '')
                    settings['lead_status_color'] = lookup_item.get('color', '')
            elif field_name == 'customer_type_name' and field_value:
                for lookup_item in field_value:
                    settings['customer_type_name'] = lookup_item.get('name', '')
                    settings['customer_type_color'] = lookup_item.get('color', '')
            elif field_name == 'customer_requirement_name' and field_value:
                settings['customer_requirement_name'] = [
                    lookup_item.get('name', '') for lookup_item in field_value
                ]
                settings['customer_requirement_color'] = [
                    lookup_item.get('color', '') for lookup_item in field_value
                ]
            elif field_name == 'source_name' and field_value:
                for lookup_item in field_value:
                    settings['source_name'] = lookup_item.get('name', '')
            elif field_name == 'payment_terms_name' and field_value:
                for lookup_item in field_value:
                    settings['payment_terms_name'] = lookup_item.get('name', '')
                    settings['payment_terms_color'] = lookup_item.get('color', '')

        MongoAPI._apply_lead_payment_output(settings)
        return dict(settings)

    @staticmethod
    def lead_list(org_id, current_user, length, page, filter_data, order, sort, search_string):
        try:
            skip = 0
            if page:
                skip1 = page * length
                skip = skip1 - length

            match_filter = {
                'org_id': org_id,
                'status': 'active',
            }
            MongoAPI._apply_lead_list_filters(match_filter, filter_data, current_user, org_id)
            if not MongoAPI._branch_ids_from_filter_data(filter_data):
                actor = MongoAPI.getUserDetails(org_id, current_user)
                if not MongoAPI._apply_branch_scope_to_match_filter(
                    match_filter, actor, org_id=org_id, include_unset_branch=True,
                ):
                    return [], 0
            MongoAPI._apply_lead_visibility_filter(match_filter, org_id, current_user)

            search_text = (search_string or '').strip()
            if search_text:
                search_regex = {'$regex': search_text, '$options': 'i'}
                match_filter['$or'] = [
                    {'company_name': search_regex},
                    {'name': search_regex},
                    {'phone': search_regex},
                    {'email': search_regex},
                ]

            pipeline = [
                {'$lookup': app_config.user_lookup},
                {'$lookup': app_config.company_lookup},
                {'$lookup': app_config.contact_lookup},
                {'$lookup': app_config.lead_status_lookup},
                {'$lookup': app_config.customfields_value_lookup},
                {'$lookup': app_config.lead_customer_type_lookup},
                {'$lookup': app_config.lead_customer_requirement_lookup},
                {'$lookup': app_config.lead_source_type_lookup},
                {'$lookup': app_config.lead_payment_terms_lookup},
                {'$lookup': app_config.curr_name_Lookup},
                {'$sort': {sort: order}},
                {'$match': match_filter},
                {'$skip': skip},
                {'$limit': length},
            ]
            count_pipeline = [
                {'$lookup': app_config.user_lookup},
                {'$lookup': app_config.company_lookup},
                {'$lookup': app_config.contact_lookup},
                {'$lookup': app_config.customfields_value_lookup},
                {'$match': match_filter},
                {'$group': {'_id': None, 'count': {'$sum': 1}}},
            ]

            settings6 = []
            for item in Lead.objects.aggregate(*pipeline):
                settings = MongoAPI._format_lead_list_item(item, org_id, current_user)
                if settings:
                    settings6.append(settings)

            settings2 = json.loads(json_util.dumps(settings6))
            search_count = next(Lead.objects.aggregate(*count_pipeline), {'count': 0}).get('count', 0)
            return settings2, search_count
        except NotUniqueError:
            return [], 0
        except Exception:
            return [], 0

    @staticmethod
    def _ensure_project_numbering(org_id):
        numbering = MongoAPI.getNumberingSettings('project', org_id)
        if numbering:
            return numbering
        try:
            Numbering(
                org_id=int(org_id),
                module='project',
                prefix='PRJ',
                sequence=1,
            ).save()
        except Exception:
            pass
        return MongoAPI.getNumberingSettings('project', org_id)

    @staticmethod
    def _format_project_date(value, current_user, org_id):
        if not value:
            return ''
        parsed = MongoAPI._parse_date_value(value)
        if parsed is None:
            return str(value)
        try:
            offset = MongoAPI.commontimeset(current_user, org_id)
            local_dt = parsed + timedelta(hours=offset)
            return local_dt.strftime(DATE_FORMAT1)
        except Exception:
            return parsed.strftime(DATE_FORMAT1)

    @staticmethod
    def _project_dict(project, current_user=None, org_id=None):
        org_id = org_id or project.org_id
        data = {
            '_id': str(project.id),
            'project_no': project.project_no or '',
            'name': project.name or '',
            'location': project.location or '',
            'area_locality': project.area_locality or '',
            'price_per_sqft': project.price_per_sqft or 0,
            'price_range_min': project.price_range_min or 0,
            'price_range_max': project.price_range_max or 0,
            'total_units': project.total_units or 0,
            'available_units': project.available_units or 0,
            'blocked_units': project.blocked_units or 0,
            'sold_units': project.sold_units or 0,
            'owner_site_units': getattr(project, 'owner_site_units', None) or 0,
            'rera_status': project.rera_status or 'pending',
            'rera_number': project.rera_number or '',
            'dtcp_status': project.dtcp_status or '',
            'dtcp_number': project.dtcp_number or '',
            'price_per_cent': project.price_per_cent or '',
            'highlights': list(project.highlights or []),
            'property_types': list(project.property_types or []),
            'budget_min': project.budget_min or 0,
            'budget_max': project.budget_max or 0,
            'status': project.status or 'active',
            'description': project.description or '',
            'create_by': str(project.create_by) if project.create_by else None,
            'branch_id': MongoAPI._serialize_user_branch_id(
                org_id, getattr(project, 'branch_id', None),
            ),
        }
        if current_user is not None:
            data['create_date'] = MongoAPI._format_project_date(
                project.create_date, current_user, org_id,
            )
            if project.modify_date:
                data['modify_date'] = MongoAPI._format_project_date(
                    project.modify_date, current_user, org_id,
                )
        elif project.create_date:
            data['create_date'] = project.create_date.isoformat()
        return data

    UNIT_STATUS_BUCKETS = frozenset({'available', 'blocked', 'booked', 'owner_site'})
    UNIT_STATUS_SLUG_TO_BUCKET = {
        'available': 'available',
        'hold': 'blocked',
        'on_hold': 'blocked',
        'booked': 'booked',
        'booking': 'booked',
        'registered': 'booked',
        'sold': 'booked',
        'owner_site': 'owner_site',
    }
    UNIT_STATUS_NAME_TO_BUCKET = {
        'available': 'available',
        'on hold': 'blocked',
        'hold': 'blocked',
        'booked': 'booked',
        'booking': 'booked',
        'registered': 'booked',
        'sold': 'booked',
        'owner site': 'owner_site',
    }

    @staticmethod
    def _normalize_status_name(name):
        return ' '.join(str(name or '').strip().lower().split())

    @staticmethod
    def _bucket_from_status_slug(slug):
        normalized = MongoAPI._normalize_status_name(slug).replace(' ', '_')
        return MongoAPI.UNIT_STATUS_SLUG_TO_BUCKET.get(
            normalized,
            MongoAPI.UNIT_STATUS_NAME_TO_BUCKET.get(
                MongoAPI._normalize_status_name(slug),
            ),
        )

    @staticmethod
    def _parse_setting_bucket_info(info):
        if not info:
            return None
        try:
            if isinstance(info, dict):
                bucket = info.get('bucket')
            else:
                parsed = json.loads(info) if isinstance(info, str) else None
                bucket = parsed.get('bucket') if isinstance(parsed, dict) else None
            if bucket in MongoAPI.UNIT_STATUS_BUCKETS:
                return bucket
        except Exception:
            pass
        return None

    @staticmethod
    def _unit_status_settings_index(org_id):
        by_id = {}
        by_slug = {}
        by_name = {}
        try:
            fields = Fields.objects.filter(
                type='unit_status', org_id=int(org_id),
            ).order_by('sort_order')
            for field in fields:
                if getattr(field, 'inactive', 0) == 1:
                    continue
                title = (field.title or '').strip().lower()
                bucket = MongoAPI._parse_setting_bucket_info(field.info)
                if not bucket:
                    bucket = MongoAPI._bucket_from_status_slug(title)
                if not bucket:
                    bucket = MongoAPI.UNIT_STATUS_NAME_TO_BUCKET.get(
                        MongoAPI._normalize_status_name(field.name),
                    )
                if bucket not in MongoAPI.UNIT_STATUS_BUCKETS:
                    bucket = 'available'
                entry = {
                    '_id': str(field.id),
                    'name': field.name or '',
                    'color': field.color or '',
                    'title': title,
                    'bucket': bucket,
                }
                by_id[str(field.id)] = entry
                if title:
                    by_slug[title] = entry
                normalized_name = MongoAPI._normalize_status_name(field.name)
                if normalized_name:
                    by_name[normalized_name] = entry
        except Exception:
            pass
        return {'by_id': by_id, 'by_slug': by_slug, 'by_name': by_name}

    @staticmethod
    def _resolve_unit_status_entry(status_value, settings_index):
        if status_value is None:
            return None

        by_id = settings_index['by_id']
        if isinstance(status_value, ObjectId):
            return by_id.get(str(status_value))

        value = str(status_value).strip()
        if not value:
            return None
        if value in by_id:
            return by_id[value]
        try:
            oid = ObjectId(value)
            entry = by_id.get(str(oid))
            if entry:
                return entry
        except InvalidId:
            pass

        slug = value.lower()
        if slug in settings_index['by_slug']:
            return settings_index['by_slug'][slug]

        normalized = MongoAPI._normalize_status_name(value)
        if normalized in settings_index['by_name']:
            return settings_index['by_name'][normalized]

        bucket = MongoAPI._bucket_from_status_slug(slug)
        if bucket:
            return {
                '_id': value,
                'name': value,
                'color': '',
                'title': slug.replace(' ', '_'),
                'bucket': bucket,
            }
        return None

    @staticmethod
    def _resolve_unit_status_object_id(org_id, status_value, settings_index=None):
        settings_index = settings_index or MongoAPI._unit_status_settings_index(org_id)
        entry = MongoAPI._resolve_unit_status_entry(status_value, settings_index)
        if entry and entry.get('_id'):
            try:
                return ObjectId(entry['_id'])
            except InvalidId:
                pass
        try:
            return ObjectId(status_value)
        except (InvalidId, TypeError):
            return None

    @staticmethod
    def _unit_status_object_id_for_slug(org_id, slug, settings_index=None):
        settings_index = settings_index or MongoAPI._unit_status_settings_index(org_id)
        normalized_slug = str(slug or '').strip().lower().replace(' ', '_')
        entry = settings_index['by_slug'].get(normalized_slug)
        if not entry:
            entry = settings_index['by_name'].get(
                MongoAPI._normalize_status_name(slug),
            )
        if entry:
            try:
                return ObjectId(entry['_id'])
            except InvalidId:
                pass
        return None

    @staticmethod
    def _unit_is_sold_status(unit, org_id, settings_index=None):
        settings_index = settings_index or MongoAPI._unit_status_settings_index(org_id)
        entry = MongoAPI._resolve_unit_status_entry(unit.status, settings_index)
        if not entry:
            return str(unit.status or '').lower() == 'sold'
        slug = (entry.get('title') or '').lower()
        name = MongoAPI._normalize_status_name(entry.get('name'))
        return slug == 'sold' or name == 'sold'

    @staticmethod
    def _serialize_unit_status(unit, org_id, settings_index=None):
        settings_index = settings_index or MongoAPI._unit_status_settings_index(org_id)
        entry = MongoAPI._resolve_unit_status_entry(unit.status, settings_index)
        if entry:
            return {
                '_id': entry['_id'],
                'name': entry['name'],
                'color': entry['color'],
                'title': entry.get('title', ''),
                'bucket': entry.get('bucket', 'available'),
            }
        if unit.status:
            return str(unit.status)
        default_entry = settings_index['by_slug'].get('available')
        if default_entry:
            return {
                '_id': default_entry['_id'],
                'name': default_entry['name'],
                'color': default_entry['color'],
                'title': default_entry.get('title', 'available'),
                'bucket': 'available',
            }
        return 'available'

    @staticmethod
    def _aggregate_project_unit_counts(org_id, project_id, settings_index=None):
        settings_index = settings_index or MongoAPI._unit_status_settings_index(org_id)
        counts = {'available': 0, 'blocked': 0, 'booked': 0, 'owner_site': 0}
        try:
            units = ProjectUnit.objects(
                org_id=int(org_id), project_id=ObjectId(project_id),
            ).only('status')
            for unit in units:
                entry = MongoAPI._resolve_unit_status_entry(unit.status, settings_index)
                bucket = entry.get('bucket', 'available') if entry else 'available'
                if bucket not in counts:
                    bucket = 'available'
                counts[bucket] += 1
        except Exception:
            pass
        return {
            'total_units': sum(counts.values()),
            'available_units': counts['available'],
            'blocked_units': counts['blocked'],
            'sold_units': counts['booked'],
            'owner_site_units': counts['owner_site'],
        }

    @staticmethod
    def _project_unit_dict(unit, linked_lead_name=None, org_id=None, settings_index=None):
        org_id = org_id or unit.org_id
        settings_index = settings_index or MongoAPI._unit_status_settings_index(org_id)
        data = {
            '_id': str(unit.id),
            'project_id': str(unit.project_id) if unit.project_id else None,
            'unit_no': unit.unit_no or '',
            'block': unit.block or '',
            'property_type': unit.property_type or '',
            'area_sqft': unit.area_sqft,
            'area_cents': unit.area_cents,
            'facing': unit.facing or '',
            'floor': unit.floor or '',
            'status': MongoAPI._serialize_unit_status(unit, org_id, settings_index),
            'price_per_sqft': unit.price_per_sqft or 0,
            'total_price': unit.total_price or 0,
            'linked_lead_id': str(unit.linked_lead_id) if unit.linked_lead_id else None,
        }
        if unit.hold_until:
            data['hold_until'] = unit.hold_until.isoformat()
        if linked_lead_name:
            data['linked_lead_name'] = linked_lead_name
        try:
            active_booking = Booking.objects(
                org_id=int(org_id),
                unit_id=unit.id,
                status='active',
            ).only('id').first()
            if active_booking:
                data['booking_id'] = str(active_booking.id)
        except Exception:
            pass
        return data

    @staticmethod
    def _project_site_visit_dict(visit, current_user, org_id):
        data = {
            '_id': str(visit.id),
            'project_id': str(visit.project_id),
            'lead_id': str(visit.lead_id) if visit.lead_id else None,
            'lead_name': visit.lead_name or '',
            'visit_date': MongoAPI._format_project_date(
                visit.visit_date, current_user, org_id,
            ),
            'visit_time': visit.visit_time or '',
            'agent_name': visit.agent_name or '',
            'attaching_person': visit.attaching_person or '',
            'family_attended': bool(visit.family_attended),
            'feedback': visit.feedback or '',
            'follow_up_scheduled': bool(visit.follow_up_scheduled),
            'status': visit.status or 'scheduled',
        }
        if visit.next_follow_up_date:
            data['next_follow_up_date'] = MongoAPI._format_project_date(
                visit.next_follow_up_date, current_user, org_id,
            )
        return data

    @staticmethod
    def _project_document_dict(doc, current_user, org_id):
        return {
            '_id': str(doc.id),
            'name': doc.name or '',
            'category': doc.category or 'other',
            'file_url': doc.file_url or '',
            'uploaded_at': MongoAPI._format_project_date(
                doc.create_date, current_user, org_id,
            ),
        }

    @staticmethod
    def _apply_project_list_filters(match_filter, filter_data, org_id=None):
        for data in filter_data or []:
            if 'field' not in data:
                continue
            filter_key = data['field']
            indicator = data.get('indictor', 'is')
            selected_values = data.get('selected_values') or []
            if not selected_values:
                continue

            if filter_key in ('branch_id', 'branch'):
                MongoAPI._apply_integer_list_filter(
                    match_filter, 'branch_id', selected_values, indicator, org_id,
                )
                continue

            if filter_key in ('property_type', 'property_types'):
                if indicator == 'is':
                    match_filter['property_types'] = {'$in': selected_values}
                else:
                    match_filter['property_types'] = {'$nin': selected_values}
                continue

            # Locality filter: UI uses area_locality; also accept legacy "location".
            if filter_key in ('area_locality', 'location'):
                db_field = 'area_locality' if filter_key == 'area_locality' else 'location'
                if indicator == 'is':
                    match_filter[db_field] = {'$in': selected_values}
                else:
                    match_filter[db_field] = {'$nin': selected_values}
                continue

            if filter_key in ('status', 'rera_status'):
                if indicator == 'is':
                    match_filter[filter_key] = {'$in': selected_values}
                else:
                    match_filter[filter_key] = {'$nin': selected_values}

    @staticmethod
    def project_submit(org_id, user_id, data1):
        try:
            data1 = dict(data1)
            data1['create_by'] = user_id
            data1.pop('create_date', None)
            data1.pop('_id', None)
            data1['org_id'] = org_id

            list_fields = ('highlights', 'property_types')
            for field in list_fields:
                if field in data1 and data1[field] is None:
                    data1[field] = []

            if 'price_per_cent' in data1 and data1['price_per_cent'] is not None:
                data1['price_per_cent'] = str(data1['price_per_cent'])

            numeric_fields = (
                'price_per_sqft', 'price_range_min', 'price_range_max',
                'budget_min', 'budget_max',
                'total_units', 'available_units', 'blocked_units', 'sold_units',
                'owner_site_units',
            )
            for field in numeric_fields:
                if field in data1 and data1[field] is not None:
                    try:
                        data1[field] = float(data1[field]) if 'price' in field or 'budget' in field else int(data1[field])
                    except (TypeError, ValueError):
                        data1[field] = 0

            project = Project.from_json(json.dumps(data1))
            project.save()
            return str(project.id)
        except (NotUniqueError, ValidationError):
            return '0'

    @staticmethod
    def project_count(org_id):
        try:
            return Project.objects(org_id=int(org_id)).count()
        except Exception:
            return 0

    @staticmethod
    def project_list(org_id, current_user, length, page, filter_data, order, sort, search_string):
        try:
            skip = 0
            if page:
                skip1 = page * length
                skip = skip1 - length

            match_filter = {'org_id': int(org_id)}
            MongoAPI._apply_project_list_filters(match_filter, filter_data, org_id)
            actor = MongoAPI.getUserDetails(org_id, current_user)
            if not MongoAPI._branch_ids_from_filter_data(filter_data):
                if not MongoAPI._apply_branch_scope_to_match_filter(
                    match_filter, actor, org_id=org_id,
                ):
                    return [], 0
            MongoAPI._apply_project_visibility_filter(match_filter, org_id, current_user)

            sort_field = sort or 'create_date'
            sort_order = order if order in (1, -1) else -1

            if search_string:
                search_regex = {'$regex': search_string, '$options': 'i'}
                match_filter['$or'] = [
                    {'name': search_regex},
                    {'location': search_regex},
                    {'area_locality': search_regex},
                    {'project_no': search_regex},
                ]

            search_count = Project.objects(__raw__=match_filter).count()
            sort_prefix = '-' if sort_order == -1 else ''
            projects = Project.objects(__raw__=match_filter).order_by(
                f'{sort_prefix}{sort_field}',
            ).skip(skip).limit(length)

            settings_index = MongoAPI._unit_status_settings_index(org_id)
            results = []
            for project in projects:
                data = MongoAPI._project_dict(project, current_user, org_id)
                counts = MongoAPI._aggregate_project_unit_counts(
                    org_id, project.id, settings_index,
                )
                data.update(counts)
                results.append(data)
            return results, search_count
        except Exception:
            return [], 0

    @staticmethod
    def project_metrics(org_id, current_user):
        empty = {
            'total_projects': 0,
            'active_projects': 0,
            'total_units': 0,
            'available_units': 0,
            'site_visits_this_week': 0,
            'bookings_this_month': 0,
        }
        try:
            org_id = int(org_id)
            actor = MongoAPI.getUserDetails(org_id, current_user)
            project_filter = {'org_id': org_id}
            if not MongoAPI._apply_branch_scope_to_match_filter(
                project_filter, actor, org_id=org_id,
            ):
                return empty

            projects = Project.objects(__raw__=project_filter)
            total_projects = projects.count()
            active_projects = projects.filter(status='active').count()

            project_ids = [project.id for project in projects.only('id')]
            unit_filter = {'org_id': org_id}
            if project_ids:
                unit_filter['project_id'] = {'$in': project_ids}
            unit_totals = ProjectUnit.objects(__raw__=unit_filter)
            total_units = unit_totals.count()
            settings_index = MongoAPI._unit_status_settings_index(org_id)
            available_units = 0
            for unit in unit_totals.only('status'):
                entry = MongoAPI._resolve_unit_status_entry(unit.status, settings_index)
                bucket = entry.get('bucket') if entry else None
                if bucket == 'available' or (
                    not entry and str(unit.status or '').lower() in ('', 'available')
                ):
                    available_units += 1

            today = datetime.datetime.now()
            week_start = today - timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            visit_filter = {
                'org_id': org_id,
                'create_date__gte': week_start,
            }
            if project_ids:
                visit_filter['project_id__in'] = project_ids
            site_visits_this_week = ProjectSiteVisit.objects(**visit_filter).count()

            first_day, last_day = MongoAPI._lead_metrics_month_range()
            booking_filter = {
                'org_id': org_id,
                'status': 'active',
                'booking_date__gte': first_day,
                'booking_date__lte': last_day,
            }
            if project_ids:
                booking_filter['project_id__in'] = project_ids
            bookings_this_month = Booking.objects(**booking_filter).count()

            return {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'total_units': total_units,
                'available_units': available_units,
                'site_visits_this_week': site_visits_this_week,
                'bookings_this_month': bookings_this_month,
            }
        except Exception:
            return empty

    @staticmethod
    def get_project_details(org_id, project_id, current_user):
        try:
            project = Project.objects.get(id=ObjectId(project_id), org_id=int(org_id))
        except (Project.DoesNotExist, InvalidId):
            return None

        data = MongoAPI._project_dict(project, current_user, org_id)
        counts = MongoAPI._recalculate_project_unit_counts(org_id, project_id)
        if counts:
            data.update(counts)
        data['units'] = MongoAPI.project_units_list(org_id, project_id, current_user)
        data['site_visits'] = MongoAPI.project_site_visits_list(
            org_id, project_id, current_user,
        )
        data['documents'] = MongoAPI.project_documents_list(
            org_id, project_id, current_user,
        )
        return data

    @staticmethod
    def project_update(org_id, current_user, data1, project_id):
        try:
            settings = {'modify_date': datetime.datetime.now(timezone('UTC'))}
            allowed_fields = set(Project._fields.keys())
            skip_fields = {
                '_id', 'create_date', 'create_by', 'modify_date', 'org_id',
                'units', 'site_visits', 'documents', 'project_no',
            }
            numeric_fields = {
                'price_per_sqft', 'price_range_min', 'price_range_max',
                'budget_min', 'budget_max',
                'total_units', 'available_units', 'blocked_units', 'sold_units',
                'owner_site_units',
            }

            for field, value in data1.items():
                if field in skip_fields or field not in allowed_fields:
                    continue
                if value is None:
                    continue
                if field in numeric_fields:
                    try:
                        settings[field] = float(value) if 'price' in field or 'budget' in field else int(value)
                    except (TypeError, ValueError):
                        continue
                elif field == 'price_per_cent':
                    settings[field] = str(value)
                else:
                    settings[field] = value

            updated = Project.objects(
                org_id=int(org_id), id=ObjectId(project_id),
            ).update_one(**settings)
            if updated == 0:
                return '0'
            return str(project_id)
        except (NotUniqueError, InvalidId, ValidationError):
            return '0'

    @staticmethod
    def _recalculate_project_unit_counts(org_id, project_id):
        try:
            counts = MongoAPI._aggregate_project_unit_counts(org_id, project_id)
            Project.objects(id=ObjectId(project_id), org_id=int(org_id)).update_one(
                total_units=counts['total_units'],
                available_units=counts['available_units'],
                blocked_units=counts['blocked_units'],
                sold_units=counts['sold_units'],
                owner_site_units=counts['owner_site_units'],
                modify_date=datetime.datetime.now(timezone('UTC')),
            )
            return counts
        except Exception:
            return None

    @staticmethod
    def project_units_list(org_id, project_id, current_user, status=None):
        try:
            settings_index = MongoAPI._unit_status_settings_index(org_id)
            query = {'org_id': int(org_id), 'project_id': ObjectId(project_id)}
            if status:
                status_id = MongoAPI._resolve_unit_status_object_id(
                    org_id, status, settings_index,
                )
                if status_id is None:
                    return []
                query['status'] = status_id
            units = ProjectUnit.objects(**query).order_by('unit_no')
            results = []
            for unit in units:
                linked_lead_name = None
                if unit.linked_lead_id:
                    try:
                        lead = Lead.objects.get(
                            id=unit.linked_lead_id, org_id=int(org_id),
                        )
                        linked_lead_name = lead.name
                    except Lead.DoesNotExist:
                        pass
                results.append(
                    MongoAPI._project_unit_dict(
                        unit, linked_lead_name, org_id, settings_index,
                    ),
                )
            return results
        except Exception:
            return []

    @staticmethod
    def _unit_is_booking_status(status_value, settings_index):
        """True when a unit status belongs on the bookings list (booked bucket)."""
        entry = MongoAPI._resolve_unit_status_entry(status_value, settings_index)
        if entry:
            slug = (entry.get('title') or '').lower()
            name = MongoAPI._normalize_status_name(entry.get('name'))
            if slug in MongoAPI.BOOKING_UNIT_STATUS_SLUGS:
                return True
            if name in MongoAPI.BOOKING_UNIT_STATUS_SLUGS:
                return True
            return entry.get('bucket') == 'booked'

        raw = str(status_value or '').strip().lower()
        if raw in MongoAPI.BOOKING_UNIT_STATUS_SLUGS:
            return True
        return MongoAPI._bucket_from_status_slug(raw) == 'booked'

    @staticmethod
    def project_booking_units_list(org_id, project_id, current_user):
        try:
            settings_index = MongoAPI._unit_status_settings_index(org_id)
            units = ProjectUnit.objects(
                org_id=int(org_id), project_id=ObjectId(project_id),
            ).order_by('unit_no')
            results = []
            for unit in units:
                if not MongoAPI._unit_is_booking_status(unit.status, settings_index):
                    continue
                linked_lead_name = None
                if unit.linked_lead_id:
                    try:
                        lead = Lead.objects.get(
                            id=unit.linked_lead_id, org_id=int(org_id),
                        )
                        linked_lead_name = lead.name
                    except Lead.DoesNotExist:
                        pass
                results.append(
                    MongoAPI._project_unit_dict(
                        unit, linked_lead_name, org_id, settings_index,
                    ),
                )
            return results
        except Exception:
            return []

    @staticmethod
    def project_unit_submit(org_id, user_id, data1):
        try:
            data1 = dict(data1)
            project_id = MongoAPI._extract_object_id(
                data1.get('project_id') or data1.get('_id'),
            )
            if project_id is None:
                return '0'

            data1['project_id'] = str(project_id)
            data1['org_id'] = int(org_id)
            data1['create_by'] = user_id
            data1.pop('create_date', None)
            data1.pop('_id', None)

            if 'linked_lead_id' in data1:
                lead_id = MongoAPI._extract_object_id(data1['linked_lead_id'])
                data1['linked_lead_id'] = str(lead_id) if lead_id else None

            if 'hold_until' in data1:
                parsed = MongoAPI._parse_date_value(data1['hold_until'])
                data1['hold_until'] = parsed.strftime('%Y-%m-%d') if parsed else None

            if 'status' in data1:
                settings_index = MongoAPI._unit_status_settings_index(org_id)
                status_id = MongoAPI._resolve_unit_status_object_id(
                    org_id, data1['status'], settings_index,
                )
                if status_id is not None:
                    data1['status'] = str(status_id)
                else:
                    data1.pop('status', None)

            unit = ProjectUnit.from_json(json.dumps(data1))
            unit.save()
            MongoAPI._recalculate_project_unit_counts(org_id, project_id)
            return str(unit.id)
        except (NotUniqueError, ValidationError, InvalidId):
            return '0'

    @staticmethod
    def project_unit_update(org_id, user_id, data1, unit_id):
        try:
            settings_index = MongoAPI._unit_status_settings_index(org_id)
            settings = {'modify_date': datetime.datetime.now(timezone('UTC'))}
            allowed_fields = set(ProjectUnit._fields.keys())
            skip_fields = {
                '_id', 'create_date', 'create_by', 'modify_date', 'org_id', 'project_id',
            }

            for field, value in data1.items():
                if field in skip_fields or field not in allowed_fields:
                    continue
                if value is None:
                    continue
                if field == 'linked_lead_id':
                    lead_id = MongoAPI._extract_object_id(value)
                    settings[field] = lead_id
                elif field == 'status':
                    status_id = MongoAPI._resolve_unit_status_object_id(
                        org_id, value, settings_index,
                    )
                    if status_id is not None:
                        settings[field] = status_id
                elif field == 'hold_until':
                    parsed = MongoAPI._parse_date_value(value)
                    if parsed is not None:
                        settings[field] = parsed
                else:
                    settings[field] = value

            unit = ProjectUnit.objects(
                org_id=int(org_id), id=ObjectId(unit_id),
            ).first()
            if not unit:
                return '0'

            ProjectUnit.objects(id=ObjectId(unit_id), org_id=int(org_id)).update_one(**settings)
            MongoAPI._recalculate_project_unit_counts(org_id, unit.project_id)
            return str(unit_id)
        except (NotUniqueError, InvalidId, ValidationError):
            return '0'

    BOOKING_PAYMENT_TYPES = frozenset({'cash', 'cheque', 'neft', 'rtgs', 'upi', 'card'})
    BOOKING_TRANSACTION_TYPES = frozenset({
        'token', 'booking', 'installment', 'registration', 'final',
    })
    UNIT_STATUS_FILTER_VALUES = frozenset({
        'available', 'hold', 'booked', 'registered', 'sold',
    })
    BOOKING_LIST_UNIT_STATUS_LABELS = frozenset({'booking'})
    BOOKING_UNIT_STATUS_SLUGS = frozenset({'booking', 'booked', 'registered', 'sold'})

    @staticmethod
    def _amount_in_words_inr(amount):
        ones = [
            '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
            'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
            'Seventeen', 'Eighteen', 'Nineteen',
        ]
        tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

        def two_digits(num):
            if num < 20:
                return ones[num]
            return f'{tens[num // 10]} {ones[num % 10]}'.strip()

        def three_digits(num):
            if num >= 100:
                return f'{ones[num // 100]} Hundred {two_digits(num % 100)}'.strip()
            return two_digits(num)

        try:
            value = int(round(float(amount or 0)))
        except (TypeError, ValueError):
            value = 0
        if value == 0:
            return 'Zero Rupees Only'
        if value < 0:
            return f'Minus {MongoAPI._amount_in_words_inr(abs(value))}'

        parts = []
        crore = value // 10000000
        value %= 10000000
        lakh = value // 100000
        value %= 100000
        thousand = value // 1000
        value %= 1000

        if crore:
            parts.append(f'{three_digits(crore)} Crore')
        if lakh:
            parts.append(f'{three_digits(lakh)} Lakh')
        if thousand:
            parts.append(f'{three_digits(thousand)} Thousand')
        if value:
            parts.append(three_digits(value))

        return f"{' '.join(parts)} Rupees Only"

    @staticmethod
    def _unit_status_for_transaction(transaction_type):
        if transaction_type in ('registration', 'final'):
            return 'registered'
        if transaction_type in ('token', 'booking'):
            return 'booked'
        return None

    @staticmethod
    def _ensure_booking_numbering(org_id):
        numbering = MongoAPI.getNumberingSettings('booking', org_id)
        if numbering:
            return numbering
        try:
            Numbering(
                org_id=int(org_id),
                module='booking',
                prefix='RCP',
                sequence=1,
            ).save()
        except Exception:
            pass
        return MongoAPI.getNumberingSettings('booking', org_id)

    @staticmethod
    def _booking_dict(booking, current_user=None, org_id=None):
        org_id = org_id or booking.org_id
        data = {
            '_id': str(booking.id),
            'project_id': str(booking.project_id),
            'project_name': booking.project_name or '',
            'unit_id': str(booking.unit_id),
            'unit_no': booking.unit_no or '',
            'lead_id': str(booking.lead_id) if booking.lead_id else None,
            'customer_name': booking.customer_name or '',
            'receipt_number': booking.receipt_number or '',
            'amount_paid': booking.amount_paid or 0,
            'amount_in_words': booking.amount_in_words or '',
            'payment_type': booking.payment_type or '',
            'transaction_type': booking.transaction_type or '',
            'status': booking.status or 'active',
            'notes': booking.notes or '',
            'branch_id': MongoAPI._serialize_user_branch_id(
                org_id, getattr(booking, 'branch_id', None),
            ),
        }
        if current_user is not None:
            data['booking_date'] = MongoAPI._format_project_date(
                booking.booking_date, current_user, org_id,
            )
            data['registration_date'] = MongoAPI._format_project_date(
                booking.registration_date, current_user, org_id,
            ) if booking.registration_date else None
        else:
            data['booking_date'] = (
                booking.booking_date.isoformat() if booking.booking_date else ''
            )
            data['registration_date'] = (
                booking.registration_date.isoformat() if booking.registration_date else None
            )
        return data

    @staticmethod
    def _apply_booking_visibility_filter(match_filter, org_id, current_user):
        """Apply booking visibility based on role view-scope permissions."""
        user_details = MongoAPI.getUserDetails(org_id, current_user)
        if not user_details:
            match_filter['create_by'] = ObjectId('000000000000000000000000')
            return

        role_details = MongoAPI.get_user_role_data(org_id, current_user)
        if is_super_admin_user(user_details, role_details):
            return

        booking_view_all = int(role_details.get('booking_view_all', 0) or 0)
        booking_view_team = int(role_details.get('booking_view_team', 0) or 0)
        booking_view_own = int(role_details.get('booking_view_own', 0) or 0)

        if booking_view_all == 1:
            return
        if booking_view_team == 1:
            team_ids = MongoAPI._team_member_user_ids(org_id, user_details)
            if team_ids:
                match_filter['create_by'] = {'$in': team_ids}
            else:
                match_filter['create_by'] = ObjectId('000000000000000000000000')
            return
        if booking_view_own == 1:
            actor_oid = MongoAPI._extract_object_id(current_user)
            if actor_oid is not None:
                match_filter['create_by'] = actor_oid
            else:
                match_filter['create_by'] = ObjectId('000000000000000000000000')
            return
        match_filter['create_by'] = ObjectId('000000000000000000000000')

    @staticmethod
    def _apply_project_visibility_filter(match_filter, org_id, current_user):
        """Apply project visibility based on role view-scope permissions."""
        user_details = MongoAPI.getUserDetails(org_id, current_user)
        if not user_details:
            match_filter['create_by'] = ObjectId('000000000000000000000000')
            return

        role_details = MongoAPI.get_user_role_data(org_id, current_user)
        if is_super_admin_user(user_details, role_details):
            return

        project_view_all = int(role_details.get('project_view_all', 0) or 0)
        project_view_team = int(role_details.get('project_view_team', 0) or 0)
        project_view_own = int(role_details.get('project_view_own', 0) or 0)

        if project_view_all == 1:
            return
        if project_view_team == 1:
            team_ids = MongoAPI._team_member_user_ids(org_id, user_details)
            if team_ids:
                match_filter['create_by'] = {'$in': team_ids}
            else:
                match_filter['create_by'] = ObjectId('000000000000000000000000')
            return
        if project_view_own == 1:
            actor_oid = MongoAPI._extract_object_id(current_user)
            if actor_oid is not None:
                match_filter['create_by'] = actor_oid
            else:
                match_filter['create_by'] = ObjectId('000000000000000000000000')
            return
        match_filter['create_by'] = ObjectId('000000000000000000000000')

    @staticmethod
    def _booking_unit_ids_for_status(org_id, project_id=None, unit_status=None):
        if not unit_status:
            return None
        unit_status = str(unit_status).lower()
        if unit_status not in MongoAPI.UNIT_STATUS_FILTER_VALUES:
            return None

        settings_index = MongoAPI._unit_status_settings_index(org_id)
        units_q = ProjectUnit.objects(org_id=int(org_id))
        if project_id:
            try:
                units_q = units_q.filter(project_id=ObjectId(project_id))
            except InvalidId:
                return []

        matched_ids = []
        for unit in units_q.only('id', 'status'):
            entry = MongoAPI._resolve_unit_status_entry(unit.status, settings_index)
            slug = (entry.get('title') or '').lower() if entry else str(unit.status or '').lower()
            bucket = entry.get('bucket') if entry else MongoAPI._bucket_from_status_slug(slug)
            matched = slug == unit_status or str(unit.status or '').lower() == unit_status
            if unit_status == 'hold':
                matched = matched or bucket == 'blocked'
            elif unit_status in ('booked', 'registered', 'sold'):
                matched = matched or (bucket == 'booked' and slug == unit_status)
            elif unit_status == 'available':
                matched = matched or bucket == 'available'
            if matched:
                matched_ids.append(unit.id)
        return matched_ids

    @staticmethod
    def _recalculate_unit_status_from_bookings(org_id, unit_id, project_id):
        try:
            settings_index = MongoAPI._unit_status_settings_index(org_id)
            active_bookings = Booking.objects(
                org_id=int(org_id),
                unit_id=ObjectId(unit_id),
                status='active',
            ).only('transaction_type')
            transaction_types = [b.transaction_type for b in active_bookings]
            if not transaction_types:
                status_slug = 'available'
            elif any(t in ('registration', 'final') for t in transaction_types):
                status_slug = 'registered'
            elif any(t in ('token', 'booking') for t in transaction_types):
                status_slug = 'booked'
            else:
                status_slug = 'booked'

            new_status = MongoAPI._unit_status_object_id_for_slug(
                org_id, status_slug, settings_index,
            )
            if new_status is None:
                new_status = status_slug

            ProjectUnit.objects(
                org_id=int(org_id), id=ObjectId(unit_id),
            ).update_one(
                status=new_status,
                modify_date=datetime.datetime.now(timezone('UTC')),
            )
            MongoAPI._recalculate_project_unit_counts(org_id, project_id)
        except Exception:
            pass

    @staticmethod
    def booking_metrics(org_id, current_user):
        empty = {
            'total_bookings': 0,
            'bookings_this_month': 0,
            'total_amount_paid': 0,
            'registered_this_month': 0,
        }
        try:
            org_id = int(org_id)
            base = {'org_id': org_id, 'status': 'active'}
            MongoAPI._apply_booking_visibility_filter(base, org_id, current_user)

            total_bookings = Booking.objects(__raw__=base).count()
            total_amount_paid = sum(
                b.amount_paid or 0
                for b in Booking.objects(__raw__=base).only('amount_paid')
            )

            first_day, last_day = MongoAPI._lead_metrics_month_range()
            month_filter = dict(base)
            month_filter['booking_date'] = {'$gte': first_day, '$lte': last_day}
            bookings_this_month = Booking.objects(__raw__=month_filter).count()

            reg_filter = dict(base)
            reg_filter['registration_date'] = {'$gte': first_day, '$lte': last_day}
            registered_this_month = Booking.objects(__raw__=reg_filter).count()

            return {
                'total_bookings': total_bookings,
                'bookings_this_month': bookings_this_month,
                'total_amount_paid': total_amount_paid,
                'registered_this_month': registered_this_month,
            }
        except Exception:
            return empty

    @staticmethod
    def booking_list(org_id, current_user, length, page, filter_data,
                     order, sort, search_string, project_id=None, unit_id=None, status=None):
        empty_summary = {
            'total_count': 0,
            'total_amount_paid': 0,
            'total_amount_in_words': 'Zero Rupees Only',
        }
        try:
            skip = 0
            if page:
                skip = page * length - length

            match_filter = {'org_id': int(org_id), 'status': 'active'}
            MongoAPI._apply_booking_visibility_filter(match_filter, org_id, current_user)
            actor = MongoAPI.getUserDetails(org_id, current_user)
            if not MongoAPI._apply_branch_scope_to_match_filter(
                match_filter, actor, filter_data=filter_data, org_id=org_id,
            ):
                return {'rows': [], 'search_count': 0, 'summary': empty_summary}

            if project_id:
                match_filter['project_id'] = ObjectId(project_id)
            if unit_id:
                match_filter['unit_id'] = ObjectId(unit_id)

            if status and status in MongoAPI.UNIT_STATUS_FILTER_VALUES:
                unit_ids = MongoAPI._booking_unit_ids_for_status(
                    org_id, project_id, status,
                )
                if unit_ids is not None:
                    if not unit_ids:
                        return {'rows': [], 'search_count': 0, 'summary': empty_summary}
                    if unit_id:
                        if ObjectId(unit_id) not in unit_ids:
                            return {'rows': [], 'search_count': 0, 'summary': empty_summary}
                    else:
                        match_filter['unit_id'] = {'$in': unit_ids}

            if search_string:
                search_regex = {'$regex': search_string, '$options': 'i'}
                match_filter['$or'] = [
                    {'customer_name': search_regex},
                    {'receipt_number': search_regex},
                    {'unit_no': search_regex},
                    {'project_name': search_regex},
                ]

            sort_field = sort or 'booking_date'
            sort_order = order if order in (1, -1) else -1
            search_count = Booking.objects(__raw__=match_filter).count()

            sort_prefix = '-' if sort_order == -1 else ''
            bookings = Booking.objects(__raw__=match_filter).order_by(
                f'{sort_prefix}{sort_field}',
            ).skip(skip).limit(length)

            rows = [
                MongoAPI._booking_dict(booking, current_user, org_id)
                for booking in bookings
            ]

            total_amount = sum(
                b.amount_paid or 0
                for b in Booking.objects(__raw__=match_filter).only('amount_paid')
            )
            summary = {
                'total_count': search_count,
                'total_amount_paid': total_amount,
                'total_amount_in_words': MongoAPI._amount_in_words_inr(total_amount),
            }
            return {'rows': rows, 'search_count': search_count, 'summary': summary}
        except Exception:
            return {'rows': [], 'search_count': 0, 'summary': empty_summary}

    @staticmethod
    def get_booking_details(org_id, booking_id, current_user):
        try:
            booking = Booking.objects.get(
                id=ObjectId(booking_id),
                org_id=int(org_id),
                status='active',
            )
            return MongoAPI._booking_dict(booking, current_user, org_id)
        except (Booking.DoesNotExist, InvalidId):
            return None

    @staticmethod
    def booking_submit(org_id, user_id, data1):
        try:
            data1 = dict(data1)
            project_id = MongoAPI._extract_object_id(data1.get('project_id'))
            unit_id = MongoAPI._extract_object_id(data1.get('unit_id'))
            if project_id is None or unit_id is None:
                return '0'

            project = Project.objects.get(id=project_id, org_id=int(org_id))
            unit = ProjectUnit.objects.get(
                id=unit_id, org_id=int(org_id), project_id=project_id,
            )
            if MongoAPI._unit_is_sold_status(unit, org_id):
                return 'unit_sold'

            lead_id = MongoAPI._extract_object_id(data1.get('lead_id'))
            customer_name = str(data1.get('customer_name') or '').strip()
            if lead_id and not customer_name:
                try:
                    lead = Lead.objects.get(id=lead_id, org_id=int(org_id))
                    customer_name = lead.name or ''
                except Lead.DoesNotExist:
                    lead_id = None

            existing_unit_booking = Booking.objects(
                org_id=int(org_id),
                unit_id=unit_id,
                status='active',
            ).order_by('-booking_date').first()

            if not lead_id and existing_unit_booking and existing_unit_booking.lead_id:
                lead_id = existing_unit_booking.lead_id
            if not customer_name and existing_unit_booking:
                customer_name = str(existing_unit_booking.customer_name or '').strip()

            if not customer_name:
                return '0'

            try:
                amount_paid = float(data1.get('amount_paid', 0))
            except (TypeError, ValueError):
                return '0'
            if amount_paid <= 0:
                return '0'

            payment_type = str(data1.get('payment_type') or '').lower()
            transaction_type = str(data1.get('transaction_type') or '').lower()
            if payment_type not in MongoAPI.BOOKING_PAYMENT_TYPES:
                return '0'
            if transaction_type not in MongoAPI.BOOKING_TRANSACTION_TYPES:
                return '0'

            booking_date = MongoAPI._parse_date_value(data1.get('booking_date'))
            if booking_date is None:
                return '0'

            registration_date = MongoAPI._parse_date_value(data1.get('registration_date'))
            if registration_date and registration_date < booking_date:
                return '0'

            receipt_number = str(data1.get('receipt_number') or '').strip()
            if not receipt_number:
                numbering = MongoAPI._ensure_booking_numbering(org_id)
                if not numbering:
                    return '0'
                year = datetime.datetime.now().year
                receipt_number = (
                    f"{numbering['prefix']}-{year}-{int(numbering['sequence']):04d}"
                )
            elif Booking.objects(
                org_id=int(org_id), receipt_number=receipt_number,
            ).first():
                return 'duplicate_receipt'

            create_by = MongoAPI._extract_object_id(user_id) or ObjectId(user_id)

            booking_branch_id = MongoAPI.branch_ref_to_int(
                org_id, data1.get('branch_id'),
            )
            if booking_branch_id is None:
                booking_branch_id = getattr(project, 'branch_id', None)

            booking = Booking(
                org_id=int(org_id),
                branch_id=booking_branch_id,
                project_id=project_id,
                project_name=project.name or '',
                unit_id=unit_id,
                unit_no=unit.unit_no or '',
                lead_id=lead_id,
                customer_name=customer_name,
                receipt_number=receipt_number,
                booking_date=booking_date,
                registration_date=registration_date,
                amount_paid=amount_paid,
                amount_in_words=MongoAPI._amount_in_words_inr(amount_paid),
                payment_type=payment_type,
                transaction_type=transaction_type,
                notes=str(data1.get('notes') or ''),
                create_by=create_by,
            )
            booking.save()

            new_status_slug = MongoAPI._unit_status_for_transaction(transaction_type)
            unit_updates = {'modify_date': datetime.datetime.now(timezone('UTC'))}
            if new_status_slug:
                status_id = None
                for slug_candidate in (new_status_slug, 'booking', 'booked'):
                    status_id = MongoAPI._unit_status_object_id_for_slug(
                        org_id, slug_candidate,
                    )
                    if status_id is not None:
                        break
                if status_id is not None:
                    unit_updates['status'] = status_id
            if lead_id:
                unit_updates['linked_lead_id'] = lead_id
            try:
                ProjectUnit.objects(id=unit_id, org_id=int(org_id)).update_one(**unit_updates)
            except Exception:
                pass
            MongoAPI._recalculate_project_unit_counts(org_id, project_id)

            return str(booking.id)
        except NotUniqueError:
            return 'duplicate_receipt'
        except (ValidationError, InvalidId, Project.DoesNotExist, ProjectUnit.DoesNotExist):
            return '0'

    @staticmethod
    def _booking_date_only(value):
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        parsed = MongoAPI._parse_date_value(value)
        return parsed.date() if parsed is not None else None

    @staticmethod
    def booking_update(org_id, current_user, data1, booking_id):
        try:
            booking = Booking.objects(
                org_id=int(org_id), id=ObjectId(booking_id),
            ).first()
            if not booking:
                return 'booking_not_found'

            settings = {'modify_date': datetime.datetime.now(timezone('UTC'))}
            allowed_fields = {
                'booking_date', 'registration_date', 'amount_paid',
                'payment_type', 'transaction_type', 'notes', 'status',
                'customer_name',
            }

            for field, value in data1.items():
                if field not in allowed_fields or value is None:
                    continue
                if field in ('booking_date', 'registration_date'):
                    parsed = MongoAPI._parse_date_value(value)
                    if parsed is not None:
                        settings[field] = parsed
                elif field == 'amount_paid':
                    try:
                        amount_paid = float(value)
                    except (TypeError, ValueError):
                        return 'invalid_amount'
                    if amount_paid <= 0:
                        return 'invalid_amount'
                    settings[field] = amount_paid
                    settings['amount_in_words'] = MongoAPI._amount_in_words_inr(amount_paid)
                elif field == 'payment_type':
                    payment_type = str(value).lower()
                    if payment_type not in MongoAPI.BOOKING_PAYMENT_TYPES:
                        return 'invalid_payment_type'
                    settings[field] = payment_type
                elif field == 'transaction_type':
                    transaction_type = str(value).lower()
                    if transaction_type not in MongoAPI.BOOKING_TRANSACTION_TYPES:
                        return 'invalid_transaction_type'
                    settings[field] = transaction_type
                elif field == 'status':
                    status = str(value).lower()
                    if status not in ('active', 'cancelled', 'refunded'):
                        return 'invalid_status'
                    settings[field] = status
                else:
                    settings[field] = value

            booking_date = settings.get('booking_date', booking.booking_date)
            registration_date = settings.get('registration_date', booking.registration_date)
            booking_day = MongoAPI._booking_date_only(booking_date)
            registration_day = MongoAPI._booking_date_only(registration_date)
            if registration_day and booking_day and registration_day < booking_day:
                return 'invalid_dates'

            update_result = Booking.objects(
                org_id=int(org_id), id=ObjectId(booking_id),
            ).update_one(**settings, full_result=True)
            if update_result.matched_count == 0:
                return 'booking_not_found'

            new_status_value = settings.get('status')
            new_transaction_type = settings.get('transaction_type', booking.transaction_type)
            try:
                if new_status_value in ('cancelled', 'refunded'):
                    MongoAPI._recalculate_unit_status_from_bookings(
                        org_id, booking.unit_id, booking.project_id,
                    )
                elif 'transaction_type' in settings:
                    unit_status_slug = MongoAPI._unit_status_for_transaction(
                        new_transaction_type,
                    )
                    if unit_status_slug:
                        status_id = None
                        for slug_candidate in (unit_status_slug, 'booking', 'booked'):
                            status_id = MongoAPI._unit_status_object_id_for_slug(
                                org_id, slug_candidate,
                            )
                            if status_id is not None:
                                break
                        if status_id is not None:
                            ProjectUnit.objects(
                                org_id=int(org_id), id=booking.unit_id,
                            ).update_one(
                                status=status_id,
                                modify_date=datetime.datetime.now(timezone('UTC')),
                            )
                            MongoAPI._recalculate_project_unit_counts(
                                org_id, booking.project_id,
                            )
            except Exception:
                pass

            return str(booking_id)
        except InvalidId:
            return 'booking_not_found'
        except (NotUniqueError, ValidationError):
            return '0'

    @staticmethod
    def booking_delete(org_id, current_user, booking_id):
        try:
            booking = Booking.objects(
                org_id=int(org_id), id=ObjectId(booking_id),
            ).first()
            if not booking:
                return 'booking_not_found'

            return MongoAPI._delete_booking_record(org_id, booking)
        except InvalidId:
            return 'booking_not_found'
        except Exception:
            return '0'

    @staticmethod
    def booking_delete_by_unit(org_id, current_user, project_id, unit_id):
        try:
            project_oid = MongoAPI._extract_object_id(project_id)
            unit_oid = MongoAPI._extract_object_id(unit_id)
            if project_oid is None or unit_oid is None:
                return 'invalid_params'

            bookings = list(Booking.objects(
                org_id=int(org_id),
                project_id=project_oid,
                unit_id=unit_oid,
                status='active',
            ))
            if not bookings:
                return 'booking_not_found'

            deleted_ids = [str(booking.id) for booking in bookings]
            lead_ids = {booking.lead_id for booking in bookings if booking.lead_id}

            Booking.objects(
                org_id=int(org_id),
                project_id=project_oid,
                unit_id=unit_oid,
                status='active',
            ).delete()

            try:
                MongoAPI._recalculate_unit_status_from_bookings(
                    org_id, unit_oid, project_oid,
                )
                MongoAPI._recalculate_project_unit_counts(org_id, project_oid)

                for lead_id in lead_ids:
                    has_lead_booking = Booking.objects(
                        org_id=int(org_id),
                        unit_id=unit_oid,
                        status='active',
                        lead_id=lead_id,
                    ).count() > 0
                    if not has_lead_booking:
                        unit = ProjectUnit.objects(
                            org_id=int(org_id), id=unit_oid,
                        ).only('linked_lead_id').first()
                        if unit and unit.linked_lead_id == lead_id:
                            ProjectUnit.objects(
                                org_id=int(org_id), id=unit_oid,
                            ).update_one(
                                unset__linked_lead_id=1,
                                modify_date=datetime.datetime.now(timezone('UTC')),
                            )
            except Exception:
                pass

            return deleted_ids if len(deleted_ids) > 1 else deleted_ids[0]
        except Exception:
            return '0'

    @staticmethod
    def _delete_booking_record(org_id, booking):
        unit_id = booking.unit_id
        project_id = booking.project_id
        lead_id = booking.lead_id
        booking_id = str(booking.id)

        booking.delete()

        try:
            MongoAPI._recalculate_unit_status_from_bookings(
                org_id, unit_id, project_id,
            )
            MongoAPI._recalculate_project_unit_counts(org_id, project_id)

            if lead_id:
                has_lead_booking = Booking.objects(
                    org_id=int(org_id),
                    unit_id=unit_id,
                    status='active',
                    lead_id=lead_id,
                ).count() > 0
                if not has_lead_booking:
                    unit = ProjectUnit.objects(
                        org_id=int(org_id), id=unit_id,
                    ).only('linked_lead_id').first()
                    if unit and unit.linked_lead_id == lead_id:
                        ProjectUnit.objects(
                            org_id=int(org_id), id=unit_id,
                        ).update_one(
                            unset__linked_lead_id=1,
                            modify_date=datetime.datetime.now(timezone('UTC')),
                        )
        except Exception:
            pass

        return booking_id

    @staticmethod
    def project_site_visits_list(org_id, project_id, current_user):
        try:
            visits = ProjectSiteVisit.objects(
                org_id=int(org_id), project_id=ObjectId(project_id),
            ).order_by('-visit_date')
            return [
                MongoAPI._project_site_visit_dict(visit, current_user, org_id)
                for visit in visits
            ]
        except Exception:
            return []

    @staticmethod
    def project_site_visit_submit(org_id, user_id, data1):
        try:
            data1 = dict(data1)
            project_id = MongoAPI._extract_object_id(data1.get('project_id'))
            if project_id is None:
                return '0'

            data1['project_id'] = str(project_id)
            data1['org_id'] = int(org_id)
            data1['create_by'] = user_id
            data1.pop('create_date', None)
            data1.pop('_id', None)

            if 'lead_id' in data1:
                lead_id = MongoAPI._extract_object_id(data1['lead_id'])
                data1['lead_id'] = str(lead_id) if lead_id else None

            for date_field in ('visit_date', 'next_follow_up_date'):
                if date_field in data1:
                    parsed = MongoAPI._parse_date_value(data1[date_field])
                    data1[date_field] = parsed.strftime('%Y-%m-%d') if parsed else None

            visit = ProjectSiteVisit.from_json(json.dumps(data1))
            visit.save()
            return str(visit.id)
        except (NotUniqueError, ValidationError, InvalidId):
            return '0'

    @staticmethod
    def project_documents_list(org_id, project_id, current_user):
        try:
            docs = ProjectDocument.objects(
                org_id=int(org_id), project_id=ObjectId(project_id),
            ).order_by('-create_date')
            return [
                MongoAPI._project_document_dict(doc, current_user, org_id)
                for doc in docs
            ]
        except Exception:
            return []

    @staticmethod
    def project_document_submit(org_id, user_id, project_id, name, category, file_url):
        try:
            doc = ProjectDocument(
                org_id=int(org_id),
                project_id=ObjectId(project_id),
                name=name or '',
                category=category or 'other',
                file_url=file_url or '',
                create_by=user_id,
            )
            doc.save()
            return str(doc.id)
        except (NotUniqueError, ValidationError, InvalidId):
            return '0'

    @staticmethod
    def _parse_budget_value(budget_str):
        if not budget_str:
            return None
        text = str(budget_str).lower().replace(',', '').strip()
        nums = re.findall(r'[\d.]+', text)
        if not nums:
            return None
        value = float(nums[0])
        if 'cr' in text or 'crore' in text:
            value *= 10000000
        elif re.search(r'\bl\b|\blac\b|\blakh\b', text):
            value *= 100000
        elif 'k' in text:
            value *= 1000
        return value

    @staticmethod
    def project_match_leads(org_id, project_id, current_user):
        try:
            project = Project.objects.get(id=ObjectId(project_id), org_id=int(org_id))
        except (Project.DoesNotExist, InvalidId):
            return []

        leads = Lead.objects(org_id=int(org_id), status='active')
        matched = []

        for lead in leads:
            score = 0
            reasons = []

            lead_location = (lead.location or lead.current_staying or '').strip()
            project_locations = ' '.join(filter(None, [
                project.location, project.area_locality,
            ])).lower()
            if lead_location and project_locations:
                if lead_location.lower() in project_locations or any(
                    part in lead_location.lower()
                    for part in project_locations.split()
                    if len(part) > 2
                ):
                    score += 40
                    reasons.append('Location match')

            lead_budget = MongoAPI._parse_budget_value(lead.budget)
            budget_min = project.budget_min or project.price_range_min or 0
            budget_max = project.budget_max or project.price_range_max or 0
            if lead_budget is not None and budget_max > 0:
                if budget_min <= lead_budget <= budget_max:
                    score += 30
                    reasons.append('Budget match')
                elif lead_budget >= budget_min * 0.8 and lead_budget <= budget_max * 1.2:
                    score += 15
                    reasons.append('Budget near match')

            if project.property_types:
                requirement_names = []
                requirement_ids = MongoAPI._extract_object_id_list(lead.customer_requirement)
                if requirement_ids:
                    req_fields = Fields.objects(
                        id__in=requirement_ids, org_id=int(org_id),
                    )
                    requirement_names = [f.name.lower() for f in req_fields if f.name]

                lead_type = (lead.lead_type or '').lower()
                for prop_type in project.property_types:
                    prop_label = prop_type.replace('_', ' ').lower()
                    if prop_type.lower() in lead_type or prop_label in lead_type:
                        score += 30
                        reasons.append(f'Property type: {prop_type}')
                        break
                    if any(prop_type.lower() in name or prop_label in name for name in requirement_names):
                        score += 30
                        reasons.append(f'Property type: {prop_type}')
                        break

            if score > 0:
                matched.append({
                    '_id': str(lead.id),
                    'name': lead.name or '',
                    'phone': lead.phone or '',
                    'budget': lead.budget or '',
                    'location': lead_location,
                    'property_type': lead.lead_type or '',
                    'match_score': min(score, 100),
                    'match_reasons': reasons,
                })

        matched.sort(key=lambda item: item['match_score'], reverse=True)
        return matched


    def bulk_delete(org_id,current_user,id,associate_to):

        if associate_to=='lead':
            try:
                obj = Lead.objects(id=id)
                obj.delete()
                return '1'
            except NotUniqueError as e: 
                return '0'



#v1 modified
        # elif associate_to=='opportunity':
        #     try:
        #         obj = Opportunity.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        elif associate_to == 'contact':
            try:
                obj = Contact.objects(id=id, org_id=org_id)
                if not obj:
                    return '0'
                obj.delete()
                return '1'
            except NotUniqueError:
                return '0'

        elif associate_to == 'project':
            try:
                project = Project.objects(id=id, org_id=org_id).first()
                if not project:
                    return '0'
                ProjectUnit.objects(org_id=org_id, project_id=id).delete()
                ProjectSiteVisit.objects(org_id=org_id, project_id=id).delete()
                ProjectDocument.objects(org_id=org_id, project_id=id).delete()
                project.delete()
                return '1'
            except NotUniqueError:
                return '0'


        # elif associate_to=='product':
        #     try:
        #         obj = Product.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='quote':
        #     try:
        #         obj = Quote.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        elif associate_to == 'companyattachment':
            try:
                obj = Document.objects(id=id, org_id=org_id).first()
                if not obj:
                    return '0'
                obj.delete()
                return '1'
            except NotUniqueError:
                return '0'

        # elif associate_to=='opportunityattachment':
        #     try:
        #         obj = Document.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='companycustomfields':
        #     try:
        #         obj = Customfields_builder.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='taskcustomfields':
        #     try:
        #         obj = Customfields_builder.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='dealcustomfields':
        #     try:
        #         obj = Customfields_builder.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='contactcustomfields':
        #     try:
        #         obj = Customfields_builder.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='folder':
        #     try:
        #         folderdetail=MongoAPI.folderdetail(id)
        #         old_folder_path = folderdetail
        #         path_validation = os.path.isdir(old_folder_path)
        #         if path_validation==True:
        #             shutil.rmtree(old_folder_path)
        #         obj = Folder.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='file':
        #     try:
        #         folderdetail=MongoAPI.documentfilefolderdetail(id)
        #         # print(folderdetail)
        #         if folderdetail:
        #             folder_id=folderdetail['folder']
        #             document=folderdetail['document']
        #             folderdetail=MongoAPI.folderdetail(folder_id)
        #             folder_path = folderdetail
        #             file_path =folder_path+'/'+document
        #             # print('-----')
        #             # print(file_path)
        #             os.remove(file_path)
        #         obj = Document.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='sales_process':
        #     try:
        #         obj = Sales_process_builder.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        # elif associate_to=='sale_order':
        #     try:
        #         obj = Sale_order.objects(id=id)
        #         obj.delete()
        #         return '1'
        #     except NotUniqueError as e:
        #         return '0'

        else:
            return '0'        


    @staticmethod
    def noteSubmit(org_id,user_id,data1):
        try:
            # print(data1,"kumar1111")
            shopping_list = []
            settings = defaultdict(list)

            data1['create_by'] = user_id
            data1['org_id'] = org_id
            data1['note_id'] = Uid.generateUUID()
            data1.pop('create_date', None)

            # Extract location data if available
            location = data1.get('location', None)

            for data in data1:
                # shopping_list.append(data:data1[data])
                settings[data] = data1[data]
            # print(data1,"hhghghghg")
            u2 = Note.from_json(json.dumps(data1))
            u2.create_date = datetime.datetime.now(timezone("UTC"))

            u2.save()
            response = u2
            output1 = str(response.id)
            return output1
        except NotUniqueError as e:
            return '0'    


    @staticmethod
    def task_details(org_id,id,current_user):
        try:

            filter = {}
            filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)

            # print(filter,'gdgdgdgdgdgdgdg')

            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            pipeline = [
                            {'$match': match},
                            {'$lookup': app_config.user_lookup},
                            {'$lookup': app_config.assigned_by_lookup},
                            {'$lookup': app_config.watchers_lookup},
                            {'$lookup': app_config.shared_list_lookup},
                            {'$lookup': app_config.task_status_lookup},
                            {'$lookup': app_config.task_priority_lookup},
                            {'$lookup': app_config.team_name_lookup},
                            {'$lookup': app_config.settingsLookup},
                        ]

            settings = defaultdict(list)

            role = Task.objects.aggregate(*pipeline)
            settings6=[]
            # print(pipeline)
            item4 = role

            for item in role:
                # print(item,'////')
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    # if item1=='due_date':
                    #     due_date = item[item1]

                    #     # print(target_date)
                    #     create_date = datetime.datetime.strptime(str(due_date), DATE_FORMAT3).strftime(DATE_FORMAT1)
                    #     # create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                    #     # create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                    #     settings['due_date'] = create_date

                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']

                    if item1=='due_date':
                        due_date = item[item1]

                        # print(target_date)
                        end_date1 = due_date + timedelta()
                        create_date = datetime.datetime.strptime(str(due_date), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['due_date'] = create_date
                        settings['due_time'] = end_time
                        settings['due_date_time'] = f"{create_date} {end_time}"

                    if item1=='start_date':
                        start_date = item[item1]

                        # print(target_date)
                        start_date1 = start_date + timedelta()
                        create_date = datetime.datetime.strptime(str(start_date), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(start_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                        settings['start_date'] = create_date
                        settings['start_time'] = create_time
                        settings['start_date_time'] = f"{create_date} {create_time}"

                    # if item1=='due_date':
                    #     end_date1 = item[item1]

                    #     offset=MongoAPI.commontimeset(current_user,org_id)


                    #     utc_date= datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT4)
                    #     settings['create_date_utc'] = utc_date

                    #     # print(utc_date+'kkk')
                    #     end_date1 = end_date1 + timedelta(hours=offset)


                    #     plan_end_date = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                    #     end_date2 = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                    #     end_time = datetime.datetime.strptime(str(end_date1), DATE_FORMAT3).strftime(DATE_FORMAT2)
                    #     settings['due_date'] = plan_end_date
                    #     settings['due_time'] = end_time

                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=MongoAPI.commontimeset(current_user,org_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = calculate_age(create_date2)


                    if item1=='assigned':
                        assigned = item[item1]
                        # print (assigned)
                        assigned_to = []

                        for item2 in assigned:
                            a_data={
                                "name":item2['name'],
                                 "_id":str(item2['_id']),
                                   "f_name":item2['name'][0]
                            }
                            assigned_to.append(a_data)

                        settings['assigned_to_data'] = assigned_to
                        print( settings['assigned_to_data'],"opopo")

                        # print (settings)
                    if item1=='assigned_to':
                        assigned = item[item1]
                        # print (assigned)
                        assigned_to = []

                        for item2 in assigned:
                            assigned_to.append(str(item2))
                        settings['assigned_to'] = assigned_to


                    if item1=='shared_lists_data':
                        assigned = item[item1]
                        # print (assigned)
                        assigned_to = []

                        for item2 in assigned:
                            a_data={
                                "name":item2['name'],
                                 "_id":str(item2['_id']),
                                   "f_name":item2['name'][0]
                            }
                            assigned_to.append(a_data)

                        settings['shared_lists_data'] = assigned_to


                    if item1=='team_name':
                        assigned = item[item1]
                        assigned_to = []
                        for item2 in assigned:
                            a_data={
                                "name":item2['team_name'],
                                 "_id":str(item2['_id']),
                                #    "f_name":item2['team_name'][0]
                                "f_name": item2['team_name'][:2]
                            }
                            assigned_to.append(a_data)
                        settings['team_name'] = assigned_to


                    if item1=='assigned_by_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['assigned_by_name'] = item2['name']
                            settings['assigned_by_f_name'] = item2['name'][:2]

                    if item1=='watchers_list':
                        watchers_list = item[item1]
                        # print (watchers_list,"$$$$$$$$$$$$$$$$$$$$$")
                        watchers = []

                        # print(watchers,"f////////////////////////////////////////////")
                        for item2 in watchers_list:
                            c_data={
                                "name":item2['name'],
                                 "_id":str(item2['_id']),
                                   "c_name":item2['name'][0]

                            }

                            watchers.append(c_data)

                        settings['watchers_list_data'] = watchers

                        # print (settings,"#########555555555555")

                    if item1=='watchers':
                        watchers_to = item[item1]
                        # print (watchers_to)
                        watchers = []

                        for item2 in watchers_to:
                            watchers.append(str(item2))
                        settings['watchers'] = watchers


                    if item1=='status_name':
                        assigned = item[item1]
                        # print (assigned,'aaaaaaaaaaaaaaaaaaaaaaaaaa')
                        for item2 in assigned:
                            settings[item1] = item2['name']
                            settings['status_color'] = item2['color']
                            # print (settings)

                    if item1 == 'priority_to':
                        assigned = item[item1]
                        # print(assigned,"xbcvcvxnbxnv")
                        for item2 in assigned:
                            # print(item2)
                            settings[item1] = item2['name']
                            settings['priority_to_color'] = item2['color']

                    if item1=='teams':
                        assigned = item[item1]
                        # print (assigned)
                        teams = []

                        for item2 in assigned:
                            teams.append(str(item2))
                        settings['teams'] = teams

                    # if item1=='teams':
                    #     teams = item[item1]
                    #     teams= [str(data) for data in teams]
                    #     settings['teams']=teams

                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=MongoAPI.commontimeset(current_user,org_id)


                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date

                    if item1=='target_date':
                        target_date = item[item1]


                        # print(target_date)
                        create_date = datetime.datetime.strptime(str(target_date), DATE_FORMAT3).strftime(DATE_FORMAT1)

                        settings['target_date'] = create_date

                    # if item1=='list_id':
                    #     assigned = item[item1]
                    #     list_details=MongoAPI.get_list_Details(org_id,id,current_user)
                    #     print(list_details,'pppppppppppp')
                    #     list_details=Uid.fix_array3(list_details)
                    #     settings['list_details'] = list_details
                    #     # settings['template_name'] = list_details['template_name']


            settings2 = json.loads(json_util.dumps(settings))
            # print(settings2,"kkk")
            return settings2
        except NotUniqueError as e:
            return '0'    


    @staticmethod
    def task_notifications(org_id,user_id,data1):
        try:
            data1['create_by'] = user_id
            data1.pop('create_date', None)
            data1['org_id'] = org_id
            print(data1)
            u2 = notifications.from_json(json.dumps(data1))
            u2.create_date = datetime.datetime.now(timezone("UTC"))
            u2.save()

            output1 = str(u2.id)

            return output1
        except NotUniqueError as e:
            return '0'




    def lead_update(org_id,current_user,data1,id):
        try:
            settings = {}
            settings['modify_date'] = datetime.datetime.now(timezone("UTC"))
            allowed_fields = set(Lead._fields.keys())

            if 'stages' in data1 and 'stage' not in data1:
                data1['stage'] = data1['stages']

            if 'date_of_birth' in data1 and 'dob' not in data1:
                data1['dob'] = data1['date_of_birth']
            if 'source_of_deal' in data1 and 'sod' not in data1:
                data1['sod'] = data1['source_of_deal']
            MongoAPI._map_lead_payment_input(data1)

            skip_fields = {
                '_id', 'create_date', 'create_date_utc', 'create_time', 'create_by',
                'modify_date', 'modify_time', 'date_aging',
                'lead_status_name', 'lead_status_color',
                'customer_type_name', 'customer_type_color',
                'customer_requirement_name', 'customer_requirement_color',
                'source_name', 'source_name_color',
                'payment_terms_name', 'payment_terms_color',
                'lead_industry_name', 'lead_industry_color',
                'industry_name', 'application_name',
                'lead_application_id', 'lead_application_name', 'lead_application_color',
                'assigned', 'createBy', 'next_followup_dates',
                'not_qualified_time', 'mail_signature', 'team_name',
                'stages',
            }
            date_fields = {'target_date', 'converted_date', 'not_qualified_date', 'dob'}
            string_fields = {
                'phone', 'pincode', 'alternate_phone', 'whatsapp_no', 'stage',
                'purpose', 'referred_mobile_no', 'sod',
            }
            object_id_fields = {
                'lead_status', 'assigned_to', 'source', 'industry', 'application',
                'customer_type', 'payment_terms',
            }

            for string_field in string_fields:
                if string_field in data1:
                    data1[string_field] = str(data1[string_field] or '')

            if 'pincode' in data1 and data1['pincode'] and not str(data1['pincode']).isdigit():
                return '0'

            if 'teams' in data1 and isinstance(data1['teams'], list):
                teams = []
                for team_id in data1['teams']:
                    object_id = MongoAPI._extract_object_id(team_id)
                    if object_id is not None:
                        teams.append(object_id)
                if teams:
                    settings['teams'] = teams

            if 'suggested_projects' in data1:
                settings['suggested_projects'] = MongoAPI._extract_object_id_list(
                    data1.get('suggested_projects', []),
                )

            if 'customer_requirement' in data1:
                customer_requirements = MongoAPI._extract_object_id_list(
                    data1['customer_requirement'],
                )
                settings['customer_requirement'] = customer_requirements
                data1['customer_requirement'] = [
                    str(object_id) for object_id in customer_requirements
                ]

            for field, value in data1.items():
                if field in skip_fields or field not in allowed_fields:
                    continue
                if field in ('teams', 'customer_requirement', 'suggested_projects'):
                    continue
                if field in object_id_fields:
                    object_id = MongoAPI._extract_object_id(value)
                    if object_id is None:
                        continue
                    settings[field] = object_id
                    continue
                if field in date_fields:
                    parsed_date = MongoAPI._parse_date_value(value)
                    if parsed_date is not None:
                        settings[field] = parsed_date
                    continue
                if value is not None:
                    settings[field] = value

            if 'branch_id' in data1:
                resolved_branch = MongoAPI.branch_ref_to_int(org_id, data1.get('branch_id'))
                if resolved_branch is not None:
                    settings['branch_id'] = resolved_branch
            elif 'assigned_to' in settings or 'assigned_to' in data1:
                branch_id = MongoAPI._resolve_lead_branch_id(org_id, data1, current_user)
                if branch_id is not None:
                    settings['branch_id'] = branch_id

            Lead.objects(org_id=org_id, id=ObjectId(id)).update_one(**settings)
            return str(id)
        except (NotUniqueError, InvalidId, ValidationError):
            return '0'

    @staticmethod
    def get_lead_suggested_projects(org_id, lead_id):
        try:
            lead = Lead.objects.get(org_id=int(org_id), id=ObjectId(lead_id))
            projects = getattr(lead, 'suggested_projects', None) or []
            return [str(project_id) for project_id in projects]
        except (Lead.DoesNotExist, InvalidId, TypeError, ValueError):
            return []

    @staticmethod
    def update_lead_suggested_projects(org_id, lead_id, project_ids):
        try:
            object_ids = MongoAPI._extract_object_id_list(project_ids)
            Lead.objects(org_id=int(org_id), id=ObjectId(lead_id)).update(
                set__suggested_projects=object_ids,
                set__modify_date=datetime.datetime.now(timezone("UTC")),
            )
            return str(lead_id)
        except (NotUniqueError, InvalidId, ValidationError, TypeError, ValueError):
            return '0'






    def get_lead_Details(org_id,id,current_user):
        try:

            filter = {}
            filter['org_id'] = org_id
            filter['_id'] = ObjectId(id)

            key = []
            val = []

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            pipeline = [
                            {'$lookup' : app_config.lead_status_lookup},
                            {'$lookup' : app_config.lead_customer_type_lookup},
                            {'$lookup' : app_config.lead_customer_requirement_lookup},
                            {'$lookup' : app_config.lead_source_type_lookup},
                            {'$lookup' : app_config.lead_payment_terms_lookup},
                            {'$lookup' : app_config.industry_lookup},
                            {'$lookup' : app_config.application_lookup},
                            {'$lookup' : app_config.ownerLookup},
                            {'$lookup': app_config.user_lookup},
                            {'$match': match},

                            { '$project': app_config.lead_project}
                        ]

            settings = defaultdict(list)

            # print(pipeline,"pipeline_data")

            role = Lead.objects.aggregate(*pipeline)

            # print(role,"role_data")
            settings6=[]

            item4 = role

            for item in role:
                # print(item,"Lead_item11")
                settings = defaultdict(list)
                for item1 in item:
                    # print(item1,"Lead_item1")
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    # print(item4,"item4_letter")
                    if item1=='create_date':
                        create_date1 = item[item1]

                        offset=MongoAPI.commontimeset(current_user,org_id)


                        utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = calculate_age(create_date2)

                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=MongoAPI.commontimeset(current_user,org_id)


                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                        settings['modify_time'] = create_time

                    if item1=='not_qualified_date':
                        not_qualified_date = item[item1]

                        offset=MongoAPI.commontimeset(current_user,org_id)


                        utc_date= datetime.datetime.strptime(str(not_qualified_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        not_qualified_date = not_qualified_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(not_qualified_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(not_qualified_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(not_qualified_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['not_qualified_date'] = create_date
                        settings['not_qualified_time'] = create_time

                    if item1=='target_date' and item[item1]:
                        target_date = item[item1]
                        offset = MongoAPI.commontimeset(current_user, org_id)
                        target_date = target_date + timedelta(hours=offset)
                        settings['target_date'] = datetime.datetime.strptime(str(target_date), DATE_FORMAT3).strftime(DATE_FORMAT1)

                    if item1=='converted_date' and item[item1]:
                        converted_date = item[item1]
                        offset = MongoAPI.commontimeset(current_user, org_id)
                        converted_date = converted_date + timedelta(hours=offset)
                        settings['converted_date'] = datetime.datetime.strptime(str(converted_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        settings['converted_time'] = datetime.datetime.strptime(str(converted_date), DATE_FORMAT).strftime(DATE_FORMAT2)

                    if item1 == 'dob' and item[item1]:
                        settings['dob'] = MongoAPI._format_display_date(item[item1])
                    elif item1 == 'date_of_birth' and item[item1] and not item.get('dob'):
                        settings['dob'] = MongoAPI._format_display_date(item[item1])

                    if item1 == 'sod' and item[item1] is not None:
                        settings['sod'] = item[item1]
                    elif item1 == 'source_of_deal' and item[item1] and not item.get('sod'):
                        settings['sod'] = item[item1]

                    if item1=='assigned':
                        assigned = item[item1]
                        # print(assigned,'item2_mailstone')
                        for item2 in assigned:
                            # print(item2,"item2_mailstone")
                            settings[item1] = item2['name']
                            settings['mail_signature'] = item2.get('mail_signature', '')



                    if item1=='lead_status_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['lead_status_name'] = item2['name']
                            settings['lead_status_color'] = item2['color']

                    if item1=='customer_type_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['customer_type_name'] = item2['name']
                            settings['customer_type_color'] = item2['color']

                    if item1 == 'customer_requirement':
                        settings['customer_requirement'] = MongoAPI._format_object_id_list(
                            item[item1],
                        )

                    if item1=='customer_requirement_name':
                        assigned = item[item1]
                        settings['customer_requirement_name'] = [
                            item2['name'] for item2 in assigned
                        ]
                        settings['customer_requirement_color'] = [
                            item2['color'] for item2 in assigned
                        ]

                    if item1=='source_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['source_name'] = item2['name']
                            settings['source_name_color'] = item2['color']

                    if item1=='payment_terms_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['payment_terms_name'] = item2['name']
                            settings['payment_terms_color'] = item2['color']

                    if item1=='industry_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['lead_industry_name'] = item2['name']
                            settings['lead_industry_color'] = item2['color']

                    if item1=='application_name':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings['lead_application_id'] = str(item2['_id'])
                            settings['lead_application_name'] = item2['name']
                            settings['lead_application_color'] = item2['color']

                    if item1=='teams':
                        teams = item[item1]
                        teams= [str(data) for data in teams]
                        settings['teams']=teams

                    if item1=='suggested_projects':
                        suggested_projects = item[item1]
                        settings['suggested_projects'] = [str(data) for data in suggested_projects]

                    #v1 modified start
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']

                    if item1 == '_id':
                        assigned = item[item1]
                        lead_details = MongoAPI.get_all_crm_tasks_detail(org_id, assigned, current_user)
                        lead_details = Uid.fix_array(lead_details)

                        # Extract _id and date for next follow-ups
                        # settings['next_followup_dates'] = [{'id': lead.get('_id', ''), 'date': lead.get('date', '')} for lead in lead_details]
                        # If there's only one follow-up date and you want to display it directly
                        settings['next_followup_dates'] = lead_details[0].get('date', '') if lead_details else ''


                        # print(settings['next_followup_dates'], 'ppppppppppp')  # This will print both _id and date
            #v1 modified end

                # print(settings,"lead_settings")
            MongoAPI._apply_lead_payment_output(settings)
            settings2 = json.loads(json_util.dumps(settings))

            return settings2
        except NotUniqueError as e:
            return '0'



    def notesedit(org_id,note,id):
        try:
            # status='converted'
            s=Note.objects(id=ObjectId(id),org_id=org_id).update(note=note)
            output = 'Yes'
            output1 = s
            print(output1,'kjkkk')
            return output1
        except Fields.DoesNotExist:
            return ''

    def getNotes(org_id,user_id,id,associate_to,sort,order):
        try:
            # user=MongoAPI.authorizationCheck(user_id)
            print(org_id,user_id,id,associate_to)
            # print('-----------------------')
            filter = {}
            key = []
            val = []
            filter['org_id'] = org_id

            if id :
                filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                            {'$lookup': app_config.note_lookup},
                            {'$sort'   : {sort_by : order_dict}},
                            {'$match': match},
                            { '$project': app_config.note_Project}
                        ]
            role = Note.objects.aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='create_date':
                        create_date1 = item[item1]
                        # print('kkkkkkkkkkkkkkk')

                        settings['create_date_timestamp'] = create_date1

                        # print(create_date1)
####################
                        offset=MongoAPI.commontimeset(user_id,org_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)
####################

                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=MongoAPI.commontimeset(user_id,org_id)


                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''
                settings['type']='note'
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            # settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'





    def getEmail(org_id, user_id, id, associate_to, sort, order):
        try:
            filter = {}
            key = []
            val = []
            filter['org_id'] = org_id
            if id:
                filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                {'$lookup': app_config.ownerLookup},
                {'$match': match},
                {'$sort': {sort_by: order_dict}},
                {'$project': app_config.email_Project},
            ]

            role = Email.objects.aggregate(*pipeline)
            settings6 = []
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1: item4}
                    if item1 == 'createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1 == 'create_date':
                        create_date1 = item[item1]
                        settings['create_date_timestamp'] = create_date1
                        offset = MongoAPI.commontimeset(user_id, org_id)

                        utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date
                        create_date1 = create_date1 + timedelta(hours=offset)

                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    if item1 == 'modify_date':
                        modify_date = item[item1]
                        offset = MongoAPI.commontimeset(user_id, org_id)

                        utc_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        modify_date = modify_date + timedelta(hours=offset)

                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                    if item1 == 'date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        settings['date'] = create_date
                    else:
                        data = {item1: item4}
                    if not settings['createBy']:
                        settings['createBy'] = ''

                settings['type'] = 'email'
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'




    @staticmethod
    def _prepare_crm_task_payload(data1):
        payload = dict(data1)
        payload.pop('create_date', None)
        payload.pop('_id', None)

        associate_id = MongoAPI._extract_object_id(payload.get('associate_id'))
        assigned_to = MongoAPI._extract_object_id(payload.get('assigned_to'))
        create_by = MongoAPI._extract_object_id(payload.get('create_by'))
        if associate_id is None or assigned_to is None:
            return None

        payload['associate_id'] = associate_id
        payload['assigned_to'] = assigned_to
        if create_by is not None:
            payload['create_by'] = create_by

        parsed_date = MongoAPI._parse_date_value(payload.get('date'))
        if parsed_date is None:
            return None
        payload['date'] = parsed_date

        for optional_field in (
            'company_id', 'ticket_id', 'visit_purpose', 'note_id', 'task_type',
        ):
            object_id = MongoAPI._extract_object_id(payload.get(optional_field))
            if object_id is not None:
                payload[optional_field] = object_id
            else:
                payload.pop(optional_field, None)

        payload.setdefault('status', 'Open')
        payload.setdefault('remainder_status', '0')
        return payload

    @staticmethod
    def _format_crm_task_record(item, current_user, org_id):
        settings = defaultdict(list)
        if '_id' in item:
            settings['_id'] = str(item['_id'])

        for item1, value in item.items():
            settings[item1] = value

            if item1 == 'date':
                settings['date'] = MongoAPI._format_display_date(value)
            if item1 == 'create_date':
                offset = MongoAPI.commontimeset(current_user, org_id)
                utc_date = datetime.datetime.strptime(str(value), DATE_FORMAT).strftime(DATE_FORMAT4)
                settings['create_date_utc'] = utc_date

                adjusted_date = value + timedelta(hours=offset)
                settings['create_date'] = datetime.datetime.strptime(
                    str(adjusted_date), DATE_FORMAT,
                ).strftime(DATE_FORMAT1)
                settings['create_time'] = datetime.datetime.strptime(
                    str(adjusted_date), DATE_FORMAT,
                ).strftime(DATE_FORMAT2)
                settings['date_aging'] = calculate_age(settings['create_date'])

        return settings

    @staticmethod
    def crm_tasks_Submit(org_id, user_id, data1):
        try:
            payload = MongoAPI._prepare_crm_task_payload(data1)
            if payload is None:
                return '0'

            payload['org_id'] = int(org_id)
            payload['create_by'] = MongoAPI._extract_object_id(user_id)
            if payload['create_by'] is None:
                return '0'

            crm_task = Crm_tasks.from_json(json.dumps(payload, default=json_util.default))
            crm_task.create_date = datetime.datetime.now(timezone('UTC'))
            crm_task.save()
            return str(crm_task.id)
        except (NotUniqueError, InvalidId, ValidationError, ValueError, TypeError):
            return '0'

    @staticmethod
    def crm_tasks_update(org_id, current_user, data1, task_id):
        try:
            payload = MongoAPI._prepare_crm_task_payload(data1)
            if payload is None:
                return '0'

            settings = {'modify_date': datetime.datetime.now(timezone('UTC'))}
            skip_fields = {'_id', 'create_date', 'create_by', 'org_id'}
            for field, value in payload.items():
                if field in skip_fields:
                    continue
                settings[field] = value

            updated = Crm_tasks.objects(
                org_id=int(org_id),
                id=ObjectId(task_id),
            ).update_one(**settings)
            if updated == 0:
                return '0'
            return str(task_id)
        except (NotUniqueError, InvalidId, ValidationError, ValueError, TypeError):
            return '0'

    @staticmethod
    def crm_tasks_status_update(org_id, status, task_id, in_time='', out_time=''):
        try:
            settings = {
                'status': status,
                'completed_on': datetime.datetime.now(timezone('UTC')),
                'modify_date': datetime.datetime.now(timezone('UTC')),
            }
            if in_time:
                settings['in_time'] = in_time
            if out_time:
                settings['out_time'] = out_time

            updated = Crm_tasks.objects(
                org_id=int(org_id),
                id=ObjectId(task_id),
            ).update_one(**settings)
            return 1 if updated else 0
        except (NotUniqueError, InvalidId, ValidationError, ValueError, TypeError):
            return 0

    @staticmethod
    def crm_tasks_note_id_update(org_id, task_id, note_id):
        try:
            note_object_id = MongoAPI._extract_object_id(note_id)
            if note_object_id is None:
                return 0

            updated = Crm_tasks.objects(
                org_id=int(org_id),
                id=ObjectId(task_id),
            ).update_one(
                note_id=note_object_id,
                modify_date=datetime.datetime.now(timezone('UTC')),
            )
            return 1 if updated else 0
        except (NotUniqueError, InvalidId, ValidationError, ValueError, TypeError):
            return 0

    @staticmethod
    def crm_tasks_detail(org_id, current_user, task_id):
        try:
            filter_data = {'org_id': int(org_id), '_id': ObjectId(task_id)}
            pipeline = [{'$match': filter_data}]
            settings = defaultdict(list)

            for item in Crm_tasks.objects.aggregate(*pipeline):
                settings = MongoAPI._format_crm_task_record(item, current_user, org_id)

            if not settings:
                return {}
            return json.loads(json_util.dumps(settings))
        except (NotUniqueError, InvalidId):
            return {}

    def get_all_crm_tasks_detail(org_id, id, current_user):
        try:
            filter = {'org_id': org_id, 'associate_id': ObjectId(id), 'status': 'Open'}
            pipeline = [{'$match': filter}]
            role = Crm_tasks.objects.aggregate(*pipeline)

            settings6 = []
            all_dates = []  # Store all 'date' values

            for item in role:
                settings = defaultdict(list)

                # Include _id field
                if '_id' in item:
                    settings['_id'] = str(item['_id'])  # Convert ObjectId to string

                for item1, value in item.items():
                    settings[item1] = value

                    if item1 == 'date':
                        formatted_date = datetime.datetime.strptime(str(value), DATE_FORMAT3).strftime(DATE_FORMAT1)
                        settings['date'] = formatted_date
                        all_dates.append(datetime.datetime.strptime(formatted_date, DATE_FORMAT1))  # Collect all dates
                        # print(all_dates,'allllllll')
                    if item1 == 'create_date':
                        offset = MongoAPI.commontimeset(current_user, org_id)
                        utc_date = datetime.datetime.strptime(str(value), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        adjusted_date = value + timedelta(hours=offset)
                        settings['create_date'] = datetime.datetime.strptime(str(adjusted_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        settings['create_time'] = datetime.datetime.strptime(str(adjusted_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['date_aging'] = calculate_age(settings['create_date'])

                settings6.append(settings)
            return json.loads(json_util.dumps(settings6))

            # # Find the latest date
            # if all_dates:
            #     last_date = max(all_dates)
            #     # print(last_date,'laaaaaaaaaaaa')
            # else:
            #     return json.loads(json_util.dumps(settings6))  # Return original if no dates exist

            # # Filter nextfollowup leads dates
            # current_date = datetime.datetime.now()
            # # overdue_leads = [lead for lead in settings6 if datetime.datetime.strptime(lead['date'], DATE_FORMAT1) > current_date]
            # overdue_leads = [
            #     lead for lead in settings6
            #     if datetime.datetime.strptime(lead['date'], DATE_FORMAT1).date() >= current_date.date()
            # ]

            # return json.loads(json_util.dumps(overdue_leads))

        except NotUniqueError as e:
            return '0'

    @staticmethod
    def _parse_calendar_date_range(date_from, date_to):
        search_time = None
        nextday = None
        if date_from:
            parsed_from = datetime.datetime.strptime(date_from, '%d/%m/%Y')
            search_time = datetime.datetime(
                parsed_from.year, parsed_from.month, parsed_from.day, 0, 0,
            )
        if date_to:
            parsed_to = datetime.datetime.strptime(date_to, '%d/%m/%Y')
            nextday = datetime.datetime(
                parsed_to.year, parsed_to.month, parsed_to.day, 23, 59,
            )
        return search_time, nextday

    @staticmethod
    def _format_task_calendar_record(item, current_user, org_id):
        settings = defaultdict(list)
        if '_id' in item:
            settings['_id'] = str(item['_id'])

        for field_name, field_value in item.items():
            settings[field_name] = field_value

            if field_name == 'due_date' and field_value:
                due_date = field_value + timedelta()
                create_date = datetime.datetime.strptime(
                    str(due_date), DATE_FORMAT3,
                ).strftime(DATE_FORMAT1)
                end_time = datetime.datetime.strptime(
                    str(due_date), DATE_FORMAT3,
                ).strftime(DATE_FORMAT2)
                settings['date'] = create_date
                settings['due_date'] = create_date
                settings['due_time'] = end_time
                settings['time'] = end_time
            elif field_name == 'start_date' and field_value and not settings.get('date'):
                start_date = field_value + timedelta()
                create_date = datetime.datetime.strptime(
                    str(start_date), DATE_FORMAT3,
                ).strftime(DATE_FORMAT1)
                create_time = datetime.datetime.strptime(
                    str(start_date), DATE_FORMAT3,
                ).strftime(DATE_FORMAT2)
                settings['date'] = create_date
                settings['start_date'] = create_date
                settings['start_time'] = create_time
                settings['time'] = create_time
            elif field_name == 'assigned':
                assigned_to = []
                for lookup_item in field_value or []:
                    assigned_to.append({
                        'name': lookup_item.get('name', ''),
                        '_id': str(lookup_item.get('_id', '')),
                        'f_name': (lookup_item.get('name') or 'U')[0],
                    })
                settings['assigned_to_data'] = assigned_to
            elif field_name == 'assigned_to' and field_value:
                settings['assigned_to'] = [str(value) for value in field_value]
            elif field_name == 'status_name' and field_value:
                for lookup_item in field_value:
                    settings['status_name'] = lookup_item.get('name', '')
                    settings['status_color'] = lookup_item.get('color', '')
            elif field_name == 'create_date' and field_value:
                offset = MongoAPI.commontimeset(current_user, org_id)
                utc_date = datetime.datetime.strptime(
                    str(field_value), DATE_FORMAT,
                ).strftime(DATE_FORMAT4)
                settings['create_date_utc'] = utc_date
                adjusted_date = field_value + timedelta(hours=offset)
                settings['create_date'] = datetime.datetime.strptime(
                    str(adjusted_date), DATE_FORMAT,
                ).strftime(DATE_FORMAT1)
                settings['create_time'] = datetime.datetime.strptime(
                    str(adjusted_date), DATE_FORMAT,
                ).strftime(DATE_FORMAT2)

        settings['associate_to'] = 'task'
        if settings.get('status') == 'active':
            settings['status'] = 'Open'
        elif settings.get('status') in ('closed', 'completed', 'Completed'):
            settings['status'] = 'Completed'
        return settings

    @staticmethod
    def task_calender(org_id, current_user, length, page, date_from, date_to):
        try:
            current_user_id = ObjectId(current_user)
            match_filter = {
                'org_id': int(org_id),
                'status': 'active',
                '$and': [
                    {
                        '$or': [
                            {'assigned_to': current_user_id},
                            {'watchers': current_user_id},
                            {'create_by': current_user_id},
                        ],
                    },
                ],
            }

            search_time, nextday = MongoAPI._parse_calendar_date_range(date_from, date_to)
            if search_time and nextday:
                match_filter['$and'].append({
                    '$or': [
                        {'due_date': {'$gte': search_time, '$lte': nextday}},
                        {'start_date': {'$gte': search_time, '$lte': nextday}},
                    ],
                })

            pipeline = [
                {'$match': match_filter},
                {'$lookup': app_config.user_lookup},
                {'$lookup': app_config.assigned_by_lookup},
                {'$lookup': app_config.task_status_lookup},
                {'$lookup': app_config.task_priority_lookup},
                {'$sort': {'due_date': 1, 'start_date': 1}},
            ]

            if page and length:
                skip_count = int(length) * (int(page) - 1)
                pipeline.extend([
                    {'$skip': skip_count},
                    {'$limit': int(length)},
                ])

            settings6 = []
            for item in Task.objects.aggregate(*pipeline):
                settings6.append(
                    MongoAPI._format_task_calendar_record(item, current_user, org_id),
                )
            return json.loads(json_util.dumps(settings6))
        except (NotUniqueError, InvalidId, ValueError, TypeError):
            return []

    @staticmethod
    def subtask_calender(org_id, current_user, date_from, date_to):
        return []

    @staticmethod
    def all_crm_tasks_calender(org_id, current_user, date_from, date_to, owner=None, status=None):
        try:
            match_filter = {'org_id': int(org_id)}
            current_user_id = ObjectId(current_user)

            if owner:
                match_filter['assigned_to'] = ObjectId(owner)
            else:
                match_filter['$or'] = [
                    {'assigned_to': current_user_id},
                    {'create_by': current_user_id},
                ]

            if status:
                match_filter['status'] = status

            search_time, nextday = MongoAPI._parse_calendar_date_range(date_from, date_to)
            if search_time and nextday:
                match_filter['date'] = {'$gte': search_time, '$lte': nextday}

            pipeline = [
                {'$match': match_filter},
                {'$sort': {'date': 1}},
            ]

            settings6 = []
            for item in Crm_tasks.objects.aggregate(*pipeline):
                settings = MongoAPI._format_crm_task_record(item, current_user, org_id)
                settings['task_name'] = settings.get('description') or 'Untitled task'
                if settings.get('associate_id'):
                    settings['associate_id'] = str(settings['associate_id'])
                if settings.get('company_id'):
                    settings['company_id'] = str(settings['company_id'])
                settings6.append(settings)

            return json.loads(json_util.dumps(settings6))
        except (NotUniqueError, InvalidId, ValueError, TypeError):
            return []

    @staticmethod
    def gettask_count(org_id):
        try:
            return Task.objects(org_id=int(org_id), status='active').count()
        except NotUniqueError:
            return 0

    @staticmethod
    def _format_contact_dates(settings, item, current_user, org_id):
        if 'create_date' in item and item['create_date']:
            create_date1 = item['create_date']
            offset = MongoAPI.commontimeset(current_user, org_id)
            utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
            settings['create_date_utc'] = utc_date
            create_date1 = create_date1 + timedelta(hours=offset)
            settings['create_date'] = datetime.datetime.strptime(
                str(create_date1), DATE_FORMAT,
            ).strftime(DATE_FORMAT1)
            settings['create_time'] = datetime.datetime.strptime(
                str(create_date1), DATE_FORMAT,
            ).strftime(DATE_FORMAT2)
            settings['date_aging'] = calculate_age(settings['create_date'])

        if 'modify_date' in item and item['modify_date']:
            modify_date = item['modify_date']
            offset = MongoAPI.commontimeset(current_user, org_id)
            modify_date = modify_date + timedelta(hours=offset)
            settings['modify_date'] = datetime.datetime.strptime(
                str(modify_date), DATE_FORMAT,
            ).strftime(DATE_FORMAT1)

        if item.get('dob'):
            settings['dob'] = MongoAPI._format_display_date(item['dob'])
        elif item.get('date_of_birth'):
            settings['dob'] = MongoAPI._format_display_date(item['date_of_birth'])

    @staticmethod
    def contactSubmit(org_id, user_id, data1):
        try:
            create_by = MongoAPI._extract_object_id(user_id)
            if create_by is None:
                return '0'
            data1['create_by'] = create_by
            data1['org_id'] = int(org_id)
            data1['phone'] = str(data1.get('phone') or '')
            data1['alt_phone'] = str(data1.get('alt_phone') or '')

            if 'date_of_birth' in data1 and 'dob' not in data1:
                data1['dob'] = data1['date_of_birth']
            data1.pop('date_of_birth', None)
            parsed_dob = MongoAPI._parse_date_value(data1.get('dob'))
            if parsed_dob is not None:
                data1['dob'] = parsed_dob.strftime(DATE_FORMAT4)
            elif 'dob' in data1:
                data1.pop('dob', None)

            company_id = MongoAPI._extract_object_id(data1.get('company_id'))
            if company_id is None:
                return '0'
            data1['company_id'] = company_id

            assigned_to = MongoAPI._extract_object_id(data1.get('assigned_to'))
            if assigned_to is not None:
                data1['assigned_to'] = assigned_to
            elif 'assigned_to' in data1:
                data1.pop('assigned_to', None)

            data1.pop('create_date', None)
            data1['create_date'] = datetime.datetime.now(timezone('UTC'))
            contact = Contact.from_json(json.dumps(data1, default=json_util.default))
            contact.save()
            return str(contact.id)
        except (NotUniqueError, InvalidId, ValidationError):
            return '0'

    @staticmethod
    def get_contact_Details(org_id, contact_id, current_user):
        try:
            pipeline = [
                {'$match': {'_id': ObjectId(contact_id), 'org_id': int(org_id)}},
            ]
            settings = defaultdict(list)
            for item in Contact.objects.aggregate(*pipeline):
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                MongoAPI._format_contact_dates(settings, item, current_user, org_id)
            if not settings:
                return {}
            return json.loads(json_util.dumps(settings))
        except (NotUniqueError, InvalidId):
            return {}

    @staticmethod
    def contact_update(org_id, current_user, data1, contact_id):
        try:
            settings = {'modify_date': datetime.datetime.now(timezone('UTC'))}
            data1['phone'] = str(data1.get('phone') or '')
            data1['alt_phone'] = str(data1.get('alt_phone') or '')

            if 'date_of_birth' in data1 and 'dob' not in data1:
                data1['dob'] = data1['date_of_birth']
            data1.pop('date_of_birth', None)
            parsed_dob = MongoAPI._parse_date_value(data1.get('dob'))
            if parsed_dob is not None:
                data1['dob'] = parsed_dob
            elif 'dob' in data1:
                data1.pop('dob', None)

            company_id = MongoAPI._extract_object_id(data1.get('company_id'))
            if company_id is None:
                return '0'
            data1['company_id'] = company_id

            assigned_to = MongoAPI._extract_object_id(data1.get('assigned_to'))
            if assigned_to is not None:
                data1['assigned_to'] = assigned_to

            skip_fields = {'_id', 'create_date', 'create_by', 'org_id'}
            for field, value in data1.items():
                if field in skip_fields:
                    continue
                settings[field] = value

            updated = Contact.objects(
                org_id=int(org_id),
                id=ObjectId(contact_id),
            ).update_one(**settings)
            if updated == 0:
                return '0'
            return str(contact_id)
        except (NotUniqueError, InvalidId, ValidationError):
            return '0'

    @staticmethod
    def associate_contactList(org_id, company_id, current_user):
        try:
            match = {
                'org_id': int(org_id),
                'company_id': ObjectId(company_id),
            }
            pipeline = [
                {'$match': match},
                {'$sort': {'_id': -1}},
            ]
            settings6 = []
            for item in Contact.objects.aggregate(*pipeline):
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                MongoAPI._format_contact_dates(settings, item, current_user, org_id)
                settings6.append(settings)
            return json.loads(json_util.dumps(settings6))
        except (NotUniqueError, InvalidId):
            return []

    @staticmethod
    def get_teams_list(org_id):
        try:
            teams = []
            for team in Team.objects(org_id=int(org_id)).order_by('-_id'):
                team_data = team.to_mongo().to_dict()
                team_data['_id'] = str(team.id)
                teams.append(json.loads(json_util.dumps(team_data)))
            return teams
        except Exception:
            return []

    @staticmethod
    def sales_lead_associates(org_id, lead_id, current_user):
        contact = MongoAPI.associate_contactList(org_id, lead_id, current_user)
        contact = Uid.fix_array(contact) if contact else []
        actor = MongoAPI.getUserDetails(org_id, current_user)
        users = MongoAPI.active_users_list(org_id, actor=actor)
        task = MongoAPI.get_all_crm_tasks_detail(org_id, lead_id, current_user)
        task = Uid.fix_array(task) if task and task != '0' else []
        teams = MongoAPI.get_teams_list(org_id)
        return {
            'custom_fields': [],
            'user': users,
            'task': task,
            'teams': teams,
            'contact': contact,
        }


    def getDocument(org_id,user_id,id,associate_to,sort,order):
        try:
            filter = {}
            key = []
            val = []
            filter['org_id'] = org_id

            if id :
                filter['associate_id'] = id
            if associate_to:
                filter['associate_to'] = associate_to
            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                            {'$lookup': app_config.note_lookup},
                            {'$match': match},
                            {'$sort'   : {sort_by : order_dict}},
                            { '$project': app_config.document_Project}
                        ]
            role = Document.objects.aggregate(*pipeline)
            print("llooo",pipeline,"--------")
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}
                    if item1=='createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1=='document':
                        attachment2 = str(app_config.BASE_URL)+str(app_config.UPLOAD_OPEN_DOCUMENT_FOLDER)+str(item[item1])
                        settings['document'] = attachment2
                    if item1=='create_date':
                        create_date1 = item[item1]
                        settings['create_date_timestamp'] = create_date1
                        offset=MongoAPI.commontimeset(user_id,org_id)


                        utc_date= datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        create_date1 = create_date1 + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        # settings['date_aging'] = TokenRefresh.calculate_age(create_date2)
                    if item1=='modify_date':
                        modify_date = item[item1]

                        offset=MongoAPI.commontimeset(user_id,org_id)


                        utc_date= datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        # settings['modify_date_utc'] = utc_date

                        # print(utc_date+'kkk')
                        modify_date = modify_date + timedelta(hours=offset)


                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_date2 = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date

                    else:
                        data = {item1:item4}
                    if not settings['createBy']:
                        settings['createBy']=''
                settings['type']='document'
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            settings2 = Uid.fix_array(settings2)
            return settings2
        except NotUniqueError as e:
            return '0'

    def getTimeline(org_id, user_id, id, associate_to, sort, order):
        try:
            filter = {}
            key = []
            val = []
            filter['org_id'] = org_id

            if id:
                filter['associate_id'] = ObjectId(id)
            if associate_to:
                filter['associate_to'] = associate_to

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter

            sort_by = 'create_date'
            order_dict1 = app_config.order_dict
            order_dict = order_dict1['desc']

            pipeline = [
                {'$sort': {sort_by: order_dict}},
                {'$lookup': app_config.timelineLookup_new},
                {'$match': match},
                {'$project': app_config.activity_Project_new},
            ]

            role = UserActivity.objects.aggregate(*pipeline)
            settings6 = []
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1: item4}
                    if item1 == 'createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    if item1 == 'create_date':
                        create_date1 = item[item1]
                        settings['create_date_timestamp'] = create_date1
                        offset = MongoAPI.commontimeset(user_id, org_id)

                        utc_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT4)
                        settings['create_date_utc'] = utc_date
                        create_date1 = create_date1 + timedelta(hours=offset)

                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    if item1 == 'modify_date':
                        modify_date = item[item1]
                        offset = MongoAPI.commontimeset(user_id, org_id)

                        utc_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT4)
                        modify_date = modify_date + timedelta(hours=offset)

                        create_date = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(modify_date), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['modify_date'] = create_date
                    else:
                        data = {item1: item4}
                    if not settings['createBy']:
                        settings['createBy'] = ''
                settings['type'] = 'timeline'
                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'

    LEAD_SETTINGS_TYPES = (
        'lead_status', 'customer_type', 'customer_requirement', 'source', 'payment',
        'payment_terms',
    )

    PROJECT_SETTINGS_TYPES = (
        'rera_status', 'project_status', 'unit_status',
    )

    @staticmethod
    def _resolve_settings_field_id(org_id, id, field_type=None):
        try:
            oid = ObjectId(id)
            if Fields.objects(id=oid, org_id=int(org_id)).first():
                return oid
        except (InvalidId, TypeError):
            pass

        try:
            numeric_id = int(id)
        except (TypeError, ValueError):
            return None

        query = {'org_id': int(org_id)}
        if field_type:
            query['type'] = field_type

        field = Fields.objects(**query, sort_order=numeric_id).first()
        if field:
            return field.id

        field = Fields.objects(**query, php_id=numeric_id).first()
        if field:
            return field.id

        return None

    @staticmethod
    def checkSettings(type, name, org_id):
        try:
            field = Fields.objects.get(type=type, name=name, org_id=int(org_id))
            return 'Yes' if field.name else 'No'
        except Fields.DoesNotExist:
            return 'No'

    @staticmethod
    def fieldsSettingsCount(type, org_id):
        try:
            return Fields.objects.filter(type=type, org_id=int(org_id)).count()
        except Exception:
            return 0

    @staticmethod
    def addleadsettings(type, name, info, org_id, count, default=0, color='', weightage=''):
        try:
            sort_order = int(count) + 1
            create_date = MongoAPI._utc_now()

            if int(default) == 1:
                Fields.objects(type=type, org_id=int(org_id)).update(default=0)

            is_first = sort_order == 1
            field = Fields(
                type=type,
                name=name,
                org_id=int(org_id),
                sort_order=sort_order,
                default=1 if is_first else int(default or 0),
                info=MongoAPI._normalize_lead_settings_info(info),
                color=color or '',
                weightage=int(weightage) if weightage not in (None, '') else 0,
                create_date=create_date,
            )
            field.save()
            return {'field_id': str(field.id), 'id': str(field.id)}
        except Exception:
            return ''

    @staticmethod
    def _normalize_settings_list(items):
        normalized = Uid.fix_array(items)
        for item in normalized:
            if item.get('_id') and not item.get('id'):
                item['id'] = str(item['_id'])
        return normalized

    @staticmethod
    def settingsData(type, org_id):
        try:
            fields = Fields.objects.filter(
                type=type,
                org_id=int(org_id),
            ).order_by('sort_order')

            settings6 = []
            for field in fields:
                item = field.to_mongo().to_dict()
                settings = defaultdict(list)
                for item1, item_value in item.items():
                    settings[item1] = item_value
                    if item1 == 'create_date' and item_value:
                        create_date1 = item_value
                        if isinstance(create_date1, datetime.datetime):
                            create_date = create_date1.strftime(DATE_FORMAT1)
                            create_time = create_date1.strftime(DATE_FORMAT2)
                        else:
                            create_date = datetime.datetime.strptime(
                                str(create_date1).replace('Z', ''), DATE_FORMAT,
                            ).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(
                                str(create_date1).replace('Z', ''), DATE_FORMAT,
                            ).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                settings6.append(dict(settings))

            settings2 = json.loads(json_util.dumps(settings6))
            return MongoAPI._normalize_settings_list(settings2)
        except Exception:
            return []

    @staticmethod
    def leadsettings_detail(id, org_id, field_type=None):
        try:
            field_id = MongoAPI._resolve_settings_field_id(org_id, id, field_type)
            if field_id is None:
                return {}
            field = Fields.objects.get(id=field_id, org_id=int(org_id))
            settings = defaultdict(list)
            item = field.to_mongo().to_dict()
            for item1, item_value in item.items():
                settings[item1] = item_value
                if item1 == 'create_date' and item_value:
                    create_date1 = item_value
                    if isinstance(create_date1, datetime.datetime):
                        create_date = create_date1.strftime(DATE_FORMAT1)
                        create_time = create_date1.strftime(DATE_FORMAT2)
                    else:
                        create_date = datetime.datetime.strptime(
                            str(create_date1).replace('Z', ''), DATE_FORMAT,
                        ).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(
                            str(create_date1).replace('Z', ''), DATE_FORMAT,
                        ).strftime(DATE_FORMAT2)
                    settings['create_date'] = create_date
                    settings['create_time'] = create_time
            return json.loads(json_util.dumps(dict(settings)))
        except (Fields.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def updateleadsettings(org_id, name, id, type, default, info, color, weightage='', title=None):
        try:
            field_id = MongoAPI._resolve_settings_field_id(org_id, id, type)
            if field_id is None:
                return ''

            modify_date = MongoAPI._utc_now()
            field = Fields.objects.get(id=field_id, org_id=int(org_id))

            if int(default) == 1:
                Fields.objects(type=type, org_id=int(org_id)).update(default=0)

            merged_info = MongoAPI._merge_lead_settings_info(field.info, info)

            update_data = {
                'name': (name or '').strip(),
                'modify_date': modify_date,
                'default': int(default or 0),
                'info': merged_info,
                'color': color or '',
            }
            if weightage not in (None, ''):
                update_data['weightage'] = int(weightage)
            if title is not None:
                update_data['title'] = title

            Fields.objects(id=field_id, org_id=int(org_id)).update_one(**update_data)
            return {'id': str(field_id)}
        except (Fields.DoesNotExist, InvalidId):
            return ''

    @staticmethod
    def lead_settingsDefault(type, org_id, id):
        try:
            field_id = MongoAPI._resolve_settings_field_id(org_id, id, type)
            if field_id is None:
                return '0'
            Fields.objects(org_id=int(org_id), type=type).update(default=0)
            Fields.objects(id=field_id, org_id=int(org_id)).update_one(default=1)
            return str(field_id)
        except (Fields.DoesNotExist, InvalidId):
            return '0'

    @staticmethod
    def deleteleadSettings(id, org_id, field_type=None):
        try:
            field_id = MongoAPI._resolve_settings_field_id(org_id, id, field_type)
            if field_id is None:
                return 'No'
            field = Fields.objects(id=field_id, org_id=int(org_id)).first()
            if not field:
                return 'No'
            field.delete()
            return 'Yes'
        except (Fields.DoesNotExist, InvalidId):
            return 'No'

    @staticmethod
    def addprojectsettings(type, name, info, org_id, count, default=0, color='', weightage='', title=''):
        response = MongoAPI.addleadsettings(
            type, name, info, org_id, count, default, color, weightage,
        )
        if response and title:
            Fields.objects(
                id=ObjectId(response['field_id']), org_id=int(org_id),
            ).update_one(title=title)
        return response

    @staticmethod
    def updateprojectsettings(org_id, name, id, type, default, info, color, weightage='', title=None):
        return MongoAPI.updateleadsettings(
            org_id, name, id, type, default, info, color, weightage, title,
        )

    @staticmethod
    def Column_customize_Check(org_id, user_id):
        try:
            count = Column_customize.objects(
                org_id=int(org_id),
                user_id=ObjectId(user_id),
            ).count()
            return 'Yes' if count > 0 else 'No'
        except Exception:
            return 'No'

    @staticmethod
    def Column_customize_Submit(org_id, user_id, data1):
        try:
            doc = Column_customize(
                org_id=int(org_id),
                user_id=ObjectId(user_id),
                create_date=MongoAPI._utc_now(),
            )
            for field_name, field_value in data1.items():
                if field_name == '_id':
                    continue
                if field_name in Column_customize._fields:
                    setattr(doc, field_name, field_value)
            doc.save()
            return json.loads(json_util.dumps(doc.to_mongo().to_dict()))
        except Exception:
            return ''

    @staticmethod
    def Column_customize_update(org_id, current_user, data1, record_id):
        try:
            update_data = {'modify_date': MongoAPI._utc_now()}
            for field_name, field_value in data1.items():
                if field_name == '_id':
                    continue
                if field_name in Column_customize._fields:
                    update_data[field_name] = field_value

            mongo_updates = {
                f'set__{field_name}': field_value
                for field_name, field_value in update_data.items()
            }
            Column_customize.objects(
                id=ObjectId(record_id),
                org_id=int(org_id),
                user_id=ObjectId(current_user),
            ).update_one(**mongo_updates)

            doc = Column_customize.objects(
                id=ObjectId(record_id),
                org_id=int(org_id),
                user_id=ObjectId(current_user),
            ).first()
            if not doc:
                return ''
            return json.loads(json_util.dumps(doc.to_mongo().to_dict()))
        except Exception:
            return ''

    @staticmethod
    def Column_customize_detail_user(org_id, user_id):
        try:
            doc = Column_customize.objects(
                org_id=int(org_id),
                user_id=ObjectId(user_id),
            ).first()
            if not doc:
                return {}
            return json.loads(json_util.dumps(doc.to_mongo().to_dict()))
        except Exception:
            return {}

    @staticmethod
    def get_countries():
        try:
            countries = Countries.objects().order_by('name')
            return [{'name': country.name} for country in countries if country.name]
        except Exception:
            return []

    @staticmethod
    def get_states_by_country(country_name):
        try:
            if not country_name:
                return []
            states = States.objects(country=country_name).order_by('name')
            return [{'name': state.name} for state in states if state.name]
        except Exception:
            return []

    @staticmethod
    def seedLeadDefaultSettings(org_id):
        defaults = {
            'lead_status': [
                {'name': 'Active', 'color': '#87909e', 'active': 1},
                {'name': 'In Active', 'color': '#f8ae00', 'inactive': 1},
            ],
            'customer_type': [
                {'name': 'Enterprise', 'color': '#4466ff'},
                {'name': 'SMB', 'color': '#5f55ee'},
            ],
            'customer_requirement': [
                {'name': 'Product Demo', 'color': '#5f55ee'},
                {'name': 'Training', 'color': '#87909e'},
                {'name': 'Support', 'color': '#f8ae00'},
            ],
            'source': [
                {'name': 'Website', 'color': '#4466ff'},
                {'name': 'Referral', 'color': '#5f55ee'},
                {'name': 'Social Media', 'color': '#87909e'},
            ],
            'payment': [
                {'name': 'Advance', 'color': '#4466ff'},
                {'name': 'On Delivery', 'color': '#5f55ee'},
                {'name': 'Credit', 'color': '#87909e'},
            ],
            'payment_terms': [
                {'name': 'Net 30', 'color': '#4466ff'},
                {'name': 'Net 60', 'color': '#5f55ee'},
                {'name': 'Immediate', 'color': '#87909e'},
            ],
        }

        for field_type, options in defaults.items():
            if Fields.objects.filter(type=field_type, org_id=int(org_id)).count() > 0:
                continue
            for index, option in enumerate(options, start=1):
                field = Fields(
                    type=field_type,
                    name=option['name'],
                    org_id=int(org_id),
                    sort_order=index,
                    default=1 if index == 1 else 0,
                    color=option.get('color', ''),
                    info='',
                    create_date=MongoAPI._utc_now(),
                )
                for flag in ('active', 'inactive', 'won', 'lost', 'not_qualified', 'closed'):
                    if flag in option:
                        setattr(field, flag, option[flag])
                field.save()
        return True

    @staticmethod
    def seedProjectDefaultSettings(org_id):
        defaults = {
            'rera_status': [
                {'name': 'RERA Approved', 'color': '#059669'},
                {'name': 'RERA Pending', 'color': '#f8ae00'},
                {'name': 'Not Applicable', 'color': '#87909e'},
            ],
            'project_status': [
                {'name': 'Active', 'color': '#059669'},
                {'name': 'Upcoming', 'color': '#4466ff'},
                {'name': 'Sold Out', 'color': '#dc2626'},
                {'name': 'On Hold', 'color': '#f8ae00'},
            ],
            'unit_status': [
                {'name': 'Available', 'color': '#10B981', 'title': 'available'},
                {'name': 'On Hold', 'color': '#f8ae00', 'title': 'hold'},
                {'name': 'Booked', 'color': '#4466ff', 'title': 'booked'},
                {'name': 'Registered', 'color': '#7c3aed', 'title': 'registered'},
                {'name': 'Sold', 'color': '#dc2626', 'title': 'sold'},
                {'name': 'Owner Site', 'color': '#0ea5e9', 'title': 'owner_site'},
            ],
        }

        for field_type, options in defaults.items():
            if Fields.objects.filter(type=field_type, org_id=int(org_id)).count() > 0:
                continue
            for index, option in enumerate(options, start=1):
                field = Fields(
                    type=field_type,
                    name=option['name'],
                    org_id=int(org_id),
                    sort_order=index,
                    default=1 if index == 1 else 0,
                    color=option.get('color', ''),
                    title=option.get('title', ''),
                    info='',
                    create_date=MongoAPI._utc_now(),
                )
                field.save()
        return True

    @staticmethod
    def checkEmailTemplate(name, org_id):
        try:
            Email_template.objects.get(name=name, org_id=int(org_id))
            return 'Yes'
        except Email_template.DoesNotExist:
            return 'No'

    @staticmethod
    def emailTemplateCount(org_id):
        try:
            return Email_template.objects.filter(org_id=int(org_id)).count()
        except Exception:
            return 0

    @staticmethod
    def addEmailTemplate(name, template, subject, org_id, count, default=0):
        try:
            sort_order = int(count) + 1
            create_date = MongoAPI._utc_now()

            if int(default or 0) == 1:
                Email_template.objects(org_id=int(org_id)).update(default=0)

            is_first = sort_order == 1
            email_template = Email_template(
                name=name,
                template=template,
                subject=subject,
                org_id=int(org_id),
                sort_order=sort_order,
                default=1 if is_first else int(default or 0),
                create_date=create_date,
            )
            email_template.save()
            return {'template_id': str(email_template.id)}
        except Exception:
            return ''

    @staticmethod
    def _format_email_template_item(item):
        settings = defaultdict(list)
        for item1, item_value in item.items():
            settings[item1] = item_value
            if item1 == 'create_date' and item_value:
                create_date1 = item_value
                if isinstance(create_date1, datetime.datetime):
                    create_date = create_date1.strftime(DATE_FORMAT1)
                    create_time = create_date1.strftime(DATE_FORMAT2)
                else:
                    create_date = datetime.datetime.strptime(
                        str(create_date1).replace('Z', ''), DATE_FORMAT,
                    ).strftime(DATE_FORMAT1)
                    create_time = datetime.datetime.strptime(
                        str(create_date1).replace('Z', ''), DATE_FORMAT,
                    ).strftime(DATE_FORMAT2)
                settings['create_date'] = create_date
                settings['create_time'] = create_time
            if item1 == 'modify_date' and item_value:
                modify_date1 = item_value
                if isinstance(modify_date1, datetime.datetime):
                    settings['modify_date'] = modify_date1.strftime(DATE_FORMAT1)
                else:
                    settings['modify_date'] = datetime.datetime.strptime(
                        str(modify_date1).replace('Z', ''), DATE_FORMAT,
                    ).strftime(DATE_FORMAT1)
        return dict(settings)

    @staticmethod
    def getEmailTemplates(org_id):
        try:
            templates = Email_template.objects.filter(
                org_id=int(org_id),
            ).order_by('sort_order')

            settings6 = []
            for template in templates:
                item = template.to_mongo().to_dict()
                settings6.append(MongoAPI._format_email_template_item(item))

            settings2 = json.loads(json_util.dumps(settings6))
            return Uid.fix_array(settings2)
        except Exception:
            return []

    @staticmethod
    def getEmailTemplateDetails(org_id, template_id):
        try:
            template = Email_template.objects.get(
                id=ObjectId(template_id),
                org_id=int(org_id),
            )
            item = template.to_mongo().to_dict()
            return json.loads(json_util.dumps(MongoAPI._format_email_template_item(item)))
        except (Email_template.DoesNotExist, InvalidId):
            return {}

    @staticmethod
    def updateEmailTemplate(template_id, name, template, subject, org_id, default=0):
        try:
            modify_date = MongoAPI._utc_now()
            if int(default or 0) == 1:
                Email_template.objects(org_id=int(org_id)).update(default=0)

            Email_template.objects(
                id=ObjectId(template_id),
                org_id=int(org_id),
            ).update_one(
                name=name,
                template=template,
                subject=subject,
                default=int(default or 0),
                modify_date=modify_date,
            )
            return {'id': str(template_id)}
        except (Email_template.DoesNotExist, InvalidId):
            return ''

    @staticmethod
    def deleteEmailTemplate(template_id):
        try:
            Email_template.objects(id=ObjectId(template_id)).delete()
            return {'id': str(template_id)}
        except (Email_template.DoesNotExist, InvalidId):
            return ''

    @staticmethod
    def emailTemplateDefault(org_id, template_id):
        try:
            Email_template.objects(org_id=int(org_id)).update(default=0)
            Email_template.objects(
                id=ObjectId(template_id),
                org_id=int(org_id),
            ).update_one(default=1)
            return {'id': str(template_id)}
        except (Email_template.DoesNotExist, InvalidId):
            return ''

    @staticmethod
    def gethistory(org_id, user_id, associate_to, sort, order):
        try:
            filter_data = {
                'org_id': int(org_id),
                'associate_to': associate_to,
            }
            if user_id:
                filter_data['user_id'] = ObjectId(user_id)

            sort_field = sort or 'create_date'
            order_value = int(order) if order in (-1, 1) else -1

            history_items = Email_template_history.objects(
                **filter_data,
            ).order_by(f'{"-" if order_value == -1 else ""}{sort_field}')

            settings6 = []
            for history in history_items:
                item = history.to_mongo().to_dict()
                settings = defaultdict(list)
                for item1, item_value in item.items():
                    settings[item1] = item_value
                    if item1 == 'create_date' and item_value:
                        create_date1 = item_value
                        if isinstance(create_date1, datetime.datetime):
                            create_date = create_date1.strftime(DATE_FORMAT1)
                            create_time = create_date1.strftime(DATE_FORMAT2)
                        else:
                            create_date = datetime.datetime.strptime(
                                str(create_date1).replace('Z', ''), DATE_FORMAT,
                            ).strftime(DATE_FORMAT1)
                            create_time = datetime.datetime.strptime(
                                str(create_date1).replace('Z', ''), DATE_FORMAT,
                            ).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                settings6.append(dict(settings))

            settings2 = json.loads(json_util.dumps(settings6))
            return Uid.fix_array(settings2)
        except Exception:
            return []

    def users_gmaillist(ordId,current_user):
        try:

            filter = {}
            filter1 = {}
            key = []
            val = []
            filter['org_id'] = ordId
            filter['user_id'] = ObjectId(current_user)

            for item1 in filter:
                key.append(item1)
                val.append(filter[item1])
            match = filter
            pipeline = [

                            {'$match'  : match},

                        ]

            settings = defaultdict(list)

            role = Gmail_tokens.objects(**filter1).aggregate(*pipeline)
            settings6=[]
            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    data = {item1:item4}


                settings6.append(settings)

            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError as e:
            return '0'

    def getmail_signature(org_id):
        try:

            filter = {}
            filter['org_id'] = org_id
            filter['status'] = 'active'
            match = filter
            pipeline = [
                            {'$match': match},
                        ]

            settings = defaultdict(list)

            # print (pipeline)

            role = User.objects.aggregate(*pipeline)
            settings6=[]

            item4 = role

            for item in role:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])
                    if item1=='default':
                        assigned = int(item[item1])
                    elif item1=='create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                    else:
                        data = {item1:item4}

                settings6.append(settings)
            settings2 = json.loads(json_util.dumps(settings6))
            # print (json.loads(settings2))
            return settings2
        except NotUniqueError as e:
            return '0'


    def getfolderlist(ordId, length, page, search, sort, order, folder_id=None):
        try:
            length1 = int(page) - 1
            sData1 = int(length) * int(length1)
            match = {'org_id': ordId}

            if folder_id:
                match['_id'] = ObjectId(folder_id)

            pipeline = [
                {'$lookup': app_config.ownerLookup},
                {'$lookup': app_config.documentfile_lookup},
                {'$match': match},
            ]

            if search:
                pipeline.append({
                    '$match': {
                        'folder_name': {'$regex': search, '$options': 'i'},
                    },
                })

            pipeline.extend([
                {'$sort': {sort: order}},
                {'$skip': sData1},
                {'$limit': int(length)},
            ])

            department = Folder.objects.aggregate(*pipeline)

            settings6 = []
            for item in department:
                settings = defaultdict(list)
                for item1 in item:
                    settings[item1] = item[item1]
                    item4 = str(item[item1])

                    if item1 == 'createBy':
                        assigned = item[item1]
                        for item2 in assigned:
                            settings[item1] = item2['name']
                    elif item1 == 'files':
                        files_list = []
                        for item2 in item[item1]:
                            files_list.append({
                                '_id': str(item2.get('_id', '')),
                                'document': item2.get('document', ''),
                                'user_file_name': item2.get('user_file_name', ''),
                                'associate_to': item2.get('associate_to', ''),
                                'associate_id': str(item2.get('associate_id', '')),
                            })
                        settings['files'] = files_list
                    elif item1 == 'create_date':
                        create_date1 = item[item1]
                        create_date = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT1)
                        create_time = datetime.datetime.strptime(str(create_date1), DATE_FORMAT).strftime(DATE_FORMAT2)
                        settings['create_date'] = create_date
                        settings['create_time'] = create_time
                        settings['date_aging'] = TokenRefresh.calculate_age(create_date)
                    else:
                        data = {item1: item4}
                    if not settings.get('createBy'):
                        settings['createBy'] = ''
                settings6.append(settings)

            settings2 = json.loads(json_util.dumps(settings6))
            return settings2
        except NotUniqueError:
            return '0'
        except Exception:
            return []




    def documentSubmit(org_id,user_id,id,associate_to,document,user_file_name):
        try:
            data1 = {
                'associate_id': id,
                'associate_to': associate_to,
                'user_id': user_id,
                'org_id': int(org_id),
                'document_id': Uid.generateUUID(),
                'document': document,
                'create_by': user_id,
                'user_file_name': user_file_name,
            }

            u2 = Document.from_json(json.dumps(data1, default=json_util.default))
            u2.create_date = datetime.datetime.now(timezone("UTC"))
            u2.save()
            return str(u2.id)
        except (NotUniqueError, ValidationError):
            return '0'

class TokenRefresh:
    @staticmethod
    def calculate_age(born):
        return calculate_age(born)

    @staticmethod
    def idData():
        return datetime.datetime.now().microsecond

    @staticmethod
    def days_between(d1, d2):
        d1 = datetime.datetime.strptime(d1, "%Y-%m-%d")
        d2 = datetime.datetime.strptime(d2, "%Y-%m-%d")
        return abs((d2 - d1).days)

    @staticmethod
    def calculate_remaining(end_date_str):
        end_date = datetime.datetime.strptime(end_date_str, DATE_FORMAT1).date()
        days = (end_date - datetime.date.today()).days
        if days < 0:
            return f'{abs(days)} Days Overdue'
        if days == 0:
            return 'Today'
        if days == 1:
            return '1 Day'
        return f'{days} Days'

