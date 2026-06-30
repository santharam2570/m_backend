"""Permission keys for role-based access control.

Permission keys are stored
as 0/1 integers on Role documents.
"""

MODULE_KEYS = [
    'lead',
    'booking',
    'settings',
    'company',
    'quote',
]

PERMISSION_KEYS = [
  # Settings
    'manage_settings',
    'manage_users',
    'manage_roles',
  # Lead module
    'add_lead',
    'edit_lead',
    'delete_lead',
    'export_lead',
    'import_lead',
    'lead_view_all',
    'lead_view_own',
    'lead_view_team',
  # Booking module
    'add_booking',
    'edit_booking',
    'delete_booking',
    'booking_view_all',
    'booking_view_own',
    'booking_view_team',
  # Notes
    'add_note',
    'edit_note',
    'delete_note',
  # Lead settings
    'manage_lead_settings',
  # Organization-level RBAC
    'manage_branches',
    'manage_admins',
    'manage_branch_managers',
    'manage_branch_users',
]

ORG_LEVEL_PERMISSIONS = frozenset({
    'manage_branches',
    'manage_admins',
    'manage_branch_managers',
    'manage_branch_users',
})

ALL_ROLE_KEYS = MODULE_KEYS + PERMISSION_KEYS

DEFAULT_ADMIN_PERMISSIONS = {key: 1 for key in ALL_ROLE_KEYS}

DEFAULT_ROLE_PERMISSIONS = {key: 0 for key in ALL_ROLE_KEYS}
DEFAULT_ROLE_PERMISSIONS.update({
    'lead': 1,
    'lead_view_own': 1,
})

DEFAULT_PLAN_DATA = {key: 1 for key in MODULE_KEYS}

ROLE_RESERVED_FIELDS = {'id', '_id', 'org_id', 'role_name', 'create_by', 'create_date'}
