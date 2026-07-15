"""Permission keys for role-based access control.

Permission keys are stored as 0/1 integers on Role documents.
"""

MODULE_KEYS = [
    'lead',
    'booking',
    'project',
    'agent',
    'settings',
    'company',
    'quote',
    'reports',
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
    'view_lead_documents',
    'add_lead_document',
    'download_lead_document',
    'delete_lead_document',
    # Booking module
    'add_booking',
    'edit_booking',
    'delete_booking',
    'booking_view_all',
    'booking_view_own',
    'booking_view_team',
    # Project module
    'add_project',
    'edit_project',
    'delete_project',
    'project_view_all',
    'project_view_own',
    'project_view_team',
    # Agent module
    'add_agent',
    'edit_agent',
    'delete_agent',
    'agent_view_all',
    'agent_view_own',
    'agent_view_team',
    # Notes
    'add_note',
    'edit_note',
    'delete_note',
    # Lead settings
    'manage_lead_settings',
    # Organization-level RBAC
    'manage_branches',
    'manage_admins',
    'manage_branch_users',
]

ORG_LEVEL_PERMISSIONS = frozenset({
    'manage_branches',
    'manage_admins',
    'manage_branch_users',
})

ALL_ROLE_KEYS = MODULE_KEYS + PERMISSION_KEYS

VIEW_SCOPE_GROUPS = (
    ('lead_view_all', 'lead_view_team', 'lead_view_own'),
    ('booking_view_all', 'booking_view_team', 'booking_view_own'),
    ('project_view_all', 'project_view_team', 'project_view_own'),
    ('agent_view_all', 'agent_view_team', 'agent_view_own'),
)

SYSTEM_ROLE_NAMES = frozenset({'Super Admin'})

DEFAULT_ADMIN_PERMISSIONS = {key: 1 for key in ALL_ROLE_KEYS}

DEFAULT_ROLE_PERMISSIONS = {key: 0 for key in ALL_ROLE_KEYS}
DEFAULT_ROLE_PERMISSIONS.update({
    'lead': 1,
    'lead_view_own': 1,
})

SYSTEM_ROLE_DEFAULTS = {
    'Super Admin': DEFAULT_ADMIN_PERMISSIONS,
}

DEFAULT_PLAN_DATA = {key: 1 for key in MODULE_KEYS}

ROLE_RESERVED_FIELDS = {
    'id', '_id', 'org_id', 'role_name', 'create_by', 'create_date',
    'is_system_role', 'is_system', 'permissions', 'user_count',
}


def _func(perm_id, name, description=''):
    return {'id': perm_id, 'name': name, 'description': description}


PERMISSION_CATALOG = {
    'modules': [
        {
            'id': 'organization',
            'name': 'ORGANIZATION',
            'color': '#6366f1',
            'functions': [
                _func('manage_branches', 'Manage Branches', 'Create and manage branches'),
                _func('manage_admins', 'Manage Admins', 'Manage admin-tier users'),
                _func('manage_branch_users', 'Manage Branch Users', 'Manage branch-level users'),
            ],
        },
        {
            'id': 'settings',
            'name': 'SETTINGS',
            'color': '#8b5cf6',
            'functions': [
                _func('settings', 'Settings Module', 'Access settings module'),
                _func('manage_settings', 'Manage Settings', 'Configure organization settings'),
                _func('manage_users', 'Manage Users', 'Add and edit users'),
                _func('manage_roles', 'Manage Roles', 'Create and edit permission roles'),
                _func('manage_lead_settings', 'Manage Lead Settings', 'Configure lead fields and statuses'),
            ],
        },
        {
            'id': 'lead',
            'name': 'LEAD',
            'color': '#22c55e',
            'functions': [
                _func('lead', 'Lead Module', 'Access lead module'),
                _func('add_lead', 'Add Lead', 'Create new leads'),
                _func('edit_lead', 'Edit Lead', 'Edit existing leads'),
                # _func('delete_lead', 'Delete Lead', 'Delete leads'),
                _func('lead_view_all', 'View All Leads', 'See all leads in the organization (within branch scope)'),
                _func('lead_view_team', 'View Team Leads', 'See leads assigned to users in your branch'),
                _func('lead_view_own', 'View Own Leads', 'See only leads assigned to you'),
                _func('view_lead_documents', 'View Lead Documents', 'View documents attached to leads'),
                _func('add_lead_document', 'Add Lead Document', 'Upload documents to leads'),
                _func('download_lead_document', 'Download Lead Document', 'Download lead documents'),
                _func('delete_lead_document', 'Delete Lead Document', 'Delete lead documents'),
            ],
        },
        {
            'id': 'booking',
            'name': 'BOOKING',
            'color': '#f59e0b',
            'functions': [
                _func('booking', 'Booking Module', 'Access booking module'),
                _func('add_booking', 'Add Booking', 'Create bookings'),
                _func('edit_booking', 'Edit Booking', 'Edit bookings'),
                _func('delete_booking', 'Delete Booking', 'Delete bookings'),
                _func('booking_view_all', 'View All Bookings', 'See all bookings'),
                _func('booking_view_team', 'View Team Bookings', 'See team bookings'),
                _func('booking_view_own', 'View Own Bookings', 'See own bookings'),
            ],
        },
        {
            'id': 'project',
            'name': 'PROJECT',
            'color': '#3b82f6',
            'functions': [
                _func('project', 'Project Module', 'Access project module'),
                _func('add_project', 'Add Project', 'Create new projects'),
                _func('edit_project', 'Edit Project', 'Edit existing projects'),
                _func('delete_project', 'Delete Project', 'Delete projects'),
                _func('project_view_all', 'View All Projects', 'See all projects in the organization'),
                _func('project_view_team', 'View Team Projects', 'See projects assigned to team members'),
                _func('project_view_own', 'View Own Projects', 'See only own assigned projects'),
            ],
        },
        {
            'id': 'agents',
            'name': 'AGENTS',
            'color': '#6366f1',
            'functions': [
                _func('agent', 'Agent Module', 'Access agent module'),
                _func('add_agent', 'Add Agent', 'Create new agents'),
                _func('edit_agent', 'Edit Agent', 'Edit existing agents'),
                _func('delete_agent', 'Delete Agent', 'Delete agents'),
                _func('agent_view_all', 'View All Agents', 'See all agents in the organization'),
                _func('agent_view_team', 'View Team Agents', 'See agents assigned to team members'),
                _func('agent_view_own', 'View Own Agents', 'See only own assigned agents'),
            ],
        },
        {
            'id': 'notes',
            'name': 'NOTES',
            'color': '#64748b',
            'functions': [
                _func('add_note', 'Add Note', 'Add notes to records'),
                _func('edit_note', 'Edit Note', 'Edit notes'),
                _func('delete_note', 'Delete Note', 'Delete notes'),
            ],
        },
        {
            'id': 'reports',
            'name': 'REPORTS',
            'color': '#14b8a6',
            'functions': [
                _func('reports', 'Reports Module', 'Access reports module'),
            ],
        },
    ],
}


def flatten_role_permission_payload(data):
    """Extract permission key updates from a role create/update payload."""
    if not isinstance(data, dict):
        return {}
    merged = {}
    permissions = data.get('permissions')
    if isinstance(permissions, dict):
        merged.update(permissions)
    for key, value in data.items():
        if key in ALL_ROLE_KEYS:
            merged[key] = value
    return merged


def apply_view_scope_exclusivity(permission_updates):
    """When enabling a view scope, disable others in the same group."""
    normalized = dict(permission_updates)
    for group in VIEW_SCOPE_GROUPS:
        enabled = None
        for key in group:
            if int(normalized.get(key, 0) or 0) == 1:
                enabled = key
                break
        if enabled:
            for key in group:
                if key != enabled:
                    normalized[key] = 0
    return normalized
