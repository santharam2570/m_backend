"""Role tier, branch scope, and permission helpers for MAP RBAC."""

from permissions_config import ORG_LEVEL_PERMISSIONS

ROLE_TIERS = ('super_admin', 'admin', 'branch_manager', 'branch_user')

TIER_RANK = {
    'super_admin': 4,
    'admin': 3,
    'branch_manager': 2,
    'branch_user': 1,
}


def normalize_tier(tier):
    if tier in TIER_RANK:
        return tier
    return 'branch_user'


def effective_tier(user, role_data=None):
    role_name = (role_data or {}).get('role_name') or (user or {}).get('role_name')
    if role_name == 'Administrator':
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
        return {'admin', 'branch_manager', 'branch_user'}
    if actor_tier == 'admin':
        return {'branch_manager', 'branch_user'}
    if actor_tier == 'branch_manager':
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
    tier = effective_tier(user)
    if tier in ('super_admin', 'admin'):
        return 'all'
    branch_id = (user or {}).get('branch_id')
    if branch_id:
        return [branch_id]
    return []


def can_manage_target_user(actor, target, role_data=None):
    actor_id = str((actor or {}).get('id') or (actor or {}).get('_id') or '')
    target_id = str((target or {}).get('id') or (target or {}).get('_id') or '')
    actor_tier = effective_tier(actor)
    target_tier = effective_tier(target, role_data)

    if actor_id and target_id and actor_id == target_id:
        return actor_tier == 'super_admin'

    if target_tier == 'super_admin' and actor_tier != 'super_admin':
        return False
    if tier_rank(actor_tier) <= tier_rank(target_tier):
        return False

    if actor_tier == 'branch_manager':
        actor_branch = (actor or {}).get('branch_id')
        target_branch = (target or {}).get('branch_id')
        if not actor_branch or actor_branch != target_branch:
            return False
    return True


def user_has_module_permission(user, role_data, permission_key):
    if effective_tier(user, role_data) == 'super_admin':
        return True
    if not role_data:
        return False
    if role_data.get('role_name') == 'Administrator':
        return True
    return int(role_data.get(permission_key, 0) or 0) == 1


def can_manage_users(actor, role_data):
    tier = effective_tier(actor, role_data)
    if tier in ('super_admin', 'admin', 'branch_manager'):
        return True
    return user_has_module_permission(actor, role_data, 'manage_users')


def validate_permission_grant(actor, actor_role_data, permission_key, value):
    if effective_tier(actor) == 'super_admin':
        return True, None

    if permission_key in ORG_LEVEL_PERMISSIONS and int(value) == 1:
        return False, 'Only super admin can grant organization-level permissions'

    if int(value) == 1:
        if not user_has_module_permission(actor, actor_role_data, permission_key):
            return False, 'Cannot grant permission you do not have'
    return True, None


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

    if role_tier in ('branch_manager', 'branch_user'):
        if not branch_id:
            return False, 'branch_id is required for branch_manager and branch_user'
        if not branch_exists_fn(branch_id):
            return False, 'Invalid branch_id for this organization'
    elif branch_id:
        return False, 'branch_id must be empty for super_admin and admin'

    actor_tier = effective_tier(actor, actor_role_data)
    if actor_tier == 'branch_manager':
        if role_tier != 'branch_user':
            return False, 'Branch managers can only assign branch_user tier'
        if branch_id != actor.get('branch_id'):
            return False, 'Branch managers can only assign users to their own branch'
    elif (
        actor_tier == 'branch_user'
        and user_has_module_permission(actor, actor_role_data, 'manage_users')
    ):
        if role_tier != 'branch_user':
            return False, 'You cannot assign this role tier'
        if branch_id != actor.get('branch_id'):
            return False, 'You can only assign users to your own branch'

    if existing_target is not None:
        if 'role_tier' in payload and not can_assign_tier(actor, role_tier, actor_role_data):
            return False, 'You cannot assign this role tier'
        merged_target = {**existing_target, 'role_tier': role_tier, 'branch_id': branch_id}
        if not can_manage_target_user(actor, merged_target):
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
    return branch_id in accessible
