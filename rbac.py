"""Role tier, branch scope, and permission helpers for MAP RBAC."""

from permissions_config import ORG_LEVEL_PERMISSIONS, SYSTEM_ROLE_NAMES

ROLE_TIERS = ('super_admin', 'admin', 'branch_user')

SUPER_ADMIN_IDENTITY_ERROR = 'Super Admin role and tier cannot be modified'

TIER_RANK = {
    'super_admin': 3,
    'admin': 2,
    'branch_user': 1,
}


def normalize_tier(tier):
    if tier == 'branch_manager':
        return 'branch_user'
    if tier in TIER_RANK:
        return tier
    return 'branch_user'


def is_super_admin_role_name(role_name):
    return role_name in SYSTEM_ROLE_NAMES or role_name == 'Administrator'


def is_super_admin_user(user, role_data=None):
    if effective_tier(user, role_data) == 'super_admin':
        return True
    role_name = (role_data or {}).get('role_name') or (user or {}).get('role_name')
    return is_super_admin_role_name(role_name)


def validate_super_admin_identity_protected(existing_user, payload, role_data=None):
    """Block role/tier changes for users with Super Admin identity."""
    if not is_super_admin_user(existing_user, role_data):
        return True, None
    if not isinstance(payload, dict):
        return True, None

    existing_role_id = str((existing_user or {}).get('role') or '')
    existing_tier = normalize_tier((existing_user or {}).get('role_tier'))

    if 'role' in payload or payload.get('role'):
        new_role_id = str(payload.get('role') or existing_role_id)
        if new_role_id and existing_role_id and new_role_id != existing_role_id:
            return False, SUPER_ADMIN_IDENTITY_ERROR

    if 'role_tier' in payload:
        new_tier = normalize_tier(payload.get('role_tier'))
        if new_tier != existing_tier:
            return False, SUPER_ADMIN_IDENTITY_ERROR

    return True, None


def effective_tier(user, role_data=None):
    role_name = (role_data or {}).get('role_name') or (user or {}).get('role_name')
    if is_super_admin_role_name(role_name):
        return 'super_admin'
    tier = (user or {}).get('role_tier')
    if tier:
        return normalize_tier(tier)
    return 'branch_user'


def tier_rank(tier):
    return TIER_RANK.get(normalize_tier(tier), 1)


def tiers_actor_can_assign(actor_tier):
    actor_tier = normalize_tier(actor_tier)
    if actor_tier == 'super_admin':
        return {'admin', 'branch_user'}
    if actor_tier == 'admin':
        return {'branch_user'}
    return set()


def can_assign_tier(actor, target_tier, role_data=None):
    actor_tier = effective_tier(actor, role_data)
    target = normalize_tier(target_tier)
    if target in tiers_actor_can_assign(actor_tier):
        return True
    if (
        actor_tier == 'branch_user'
        and user_has_module_permission(actor, role_data, 'manage_users')
        and target == 'branch_user'
    ):
        return True
    return False


def get_accessible_branch_ids(user):
    """Return branch ObjectId strings the user may access, or 'all' for org-wide access."""
    branch_id = (user or {}).get('branch_id')
    if branch_id not in (None, ''):
        return [str(branch_id)]

    tier = effective_tier(user)
    if tier == 'admin':
        return 'all'
    if tier == 'super_admin':
        # Org-scoped super admins resolve assigned branches in MongoAPI.
        return 'all'
    return []


def can_manage_target_user(actor, target, role_data=None):
    actor_id = str((actor or {}).get('id') or (actor or {}).get('_id') or '')
    target_id = str((target or {}).get('id') or (target or {}).get('_id') or '')
    actor_tier = effective_tier(actor)
    target_tier = effective_tier(target, role_data)

    if actor_id and target_id and actor_id == target_id:
        return True

    if target_tier == 'super_admin' and actor_tier != 'super_admin':
        return False
    if tier_rank(actor_tier) <= tier_rank(target_tier):
        return False

    return True


def user_has_module_permission(user, role_data, permission_key):
    if effective_tier(user, role_data) == 'super_admin':
        return True
    if not role_data:
        return False
    if is_super_admin_role_name(role_data.get('role_name')):
        return True
    return int(role_data.get(permission_key, 0) or 0) == 1


def can_manage_users(actor, role_data):
    tier = effective_tier(actor, role_data)
    if tier in ('super_admin', 'admin'):
        return True
    return user_has_module_permission(actor, role_data, 'manage_users')


def validate_permission_grant(actor, actor_role_data, permission_key, value):
    if effective_tier(actor) == 'super_admin':
        return True, None

    if permission_key == 'manage_admins' and int(value) == 1:
        return False, 'Only super admin can grant manage_admins permission'

    if permission_key in ORG_LEVEL_PERMISSIONS and int(value) == 1:
        return False, 'Only super admin can grant organization-level permissions'

    if int(value) == 1:
        if not user_has_module_permission(actor, actor_role_data, permission_key):
            return False, 'Cannot grant permission you do not have'
    return True, None


def can_manage_roles(actor, role_data=None):
    tier = effective_tier(actor, role_data)
    if tier in ('super_admin', 'admin'):
        return True
    return user_has_module_permission(actor, role_data, 'manage_roles')


def validate_user_tier_branch(
    actor, payload, branch_exists_fn, existing_target=None, actor_role_data=None,
):
    """Validate role_tier and branch_id for user create/update. Returns (ok, error_msg)."""
    if existing_target is not None:
        role_tier = normalize_tier(
            payload.get('role_tier') if 'role_tier' in payload else existing_target.get('role_tier')
        )
        branch_id = payload.get('branch_id') if 'branch_id' in payload else existing_target.get('branch_id')
    else:
        role_tier = normalize_tier(payload.get('role_tier') or 'branch_user')
        branch_id = payload.get('branch_id')

    if existing_target is None:
        if not can_assign_tier(actor, role_tier, actor_role_data):
            return False, 'You cannot assign this role tier'

    if role_tier == 'branch_user':
        if not branch_id:
            return False, 'branch_id is required for branch_user'
        if not branch_exists_fn(branch_id):
            return False, 'Invalid branch_id for this organization'
    elif branch_id:
        return False, 'branch_id must be empty for super_admin and admin'

    actor_tier = effective_tier(actor, actor_role_data)
    if (
        actor_tier == 'branch_user'
        and user_has_module_permission(actor, actor_role_data, 'manage_users')
    ):
        if role_tier != 'branch_user':
            return False, 'You cannot assign this role tier'
        if str(branch_id) != str(actor.get('branch_id')):
            return False, 'You can only assign users to your own branch'

    if existing_target is not None:
        target_role_data = (
            {'role_name': existing_target.get('role_name')}
            if existing_target.get('role_name')
            else None
        )
        ok, identity_error = validate_super_admin_identity_protected(
            existing_target, payload, target_role_data,
        )
        if not ok:
            return False, identity_error

        existing_tier = normalize_tier(existing_target.get('role_tier'))
        if 'role_tier' in payload:
            if role_tier != existing_tier and not can_assign_tier(actor, role_tier, actor_role_data):
                return False, 'You cannot assign this role tier'
        merged_target = {**existing_target, 'role_tier': role_tier, 'branch_id': branch_id}
        # Pass target role data — actor_role_data would wrongly elevate the target to Super Admin.
        if not can_manage_target_user(actor, merged_target, target_role_data):
            return False, 'You cannot manage this user'

    return True, None


def resolve_record_branch_id(user, requested_branch_id=None):
    """Pick branch_id for new records based on caller tier."""
    tier = effective_tier(user)
    if tier in ('super_admin', 'admin'):
        return requested_branch_id or user.get('branch_id')
    return user.get('branch_id') or requested_branch_id


def branch_allowed_for_user(user, branch_id):
    if not branch_id:
        return False
    accessible = get_accessible_branch_ids(user)
    if accessible == 'all':
        return True
    branch_id = str(branch_id)
    return branch_id in [str(item) for item in accessible]
