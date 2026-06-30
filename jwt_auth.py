"""JWT authentication setup and helpers for MAP backend."""

import datetime

from flask import jsonify
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    current_user,
    decode_token,
    get_csrf_token,
    get_current_user,
    get_jti,
    get_jwt,
    get_jwt_header,
    get_jwt_identity,
    get_jwt_request_location,
    get_unverified_jwt_headers,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    unset_access_cookies,
    unset_jwt_cookies,
    unset_refresh_cookies,
    verify_jwt_in_request,
)

from mongodb import MongoAPI

# v3-compatible aliases
get_raw_jwt = get_jwt
get_raw_jwt_header = get_jwt_header

TOKEN_EXPIRY = datetime.timedelta(days=365)


def get_jwt_claims():
    """Return custom claims embedded in the current JWT (v3-compatible alias)."""
    claims = get_jwt()
    reserved = {'sub', 'iat', 'nbf', 'jti', 'exp', 'type', 'fresh', 'csrf'}
    return {key: value for key, value in claims.items() if key not in reserved}


def create_user_tokens(user_id):
    identity = str(user_id)
    access_token = create_access_token(identity=identity, expires_delta=TOKEN_EXPIRY)
    refresh_token = create_refresh_token(identity=identity, expires_delta=TOKEN_EXPIRY)
    return access_token, refresh_token


def init_jwt(app):
    app.config.setdefault('JWT_TOKEN_LOCATION', ['headers'])
    app.config.setdefault('JWT_HEADER_NAME', 'Authorization')
    app.config.setdefault('JWT_HEADER_TYPE', 'Bearer')
    app.config.setdefault('JWT_ACCESS_TOKEN_EXPIRES', TOKEN_EXPIRY)
    app.config.setdefault('JWT_REFRESH_TOKEN_EXPIRES', TOKEN_EXPIRY)
    app.config.setdefault('JWT_BLOCKLIST_ENABLED', True)
    app.config.setdefault('JWT_BLOCKLIST_TOKEN_CHECKS', ['access', 'refresh'])

    jwt = JWTManager(app)

    @jwt.user_lookup_loader
    def load_user(_jwt_header, jwt_payload):
        user_id = jwt_payload.get('sub')
        if not user_id:
            return None
        user = MongoAPI.authorizationCheck(user_id)
        return user or None

    @jwt.additional_claims_loader
    def add_claims(identity):
        user = MongoAPI.authorizationCheck(identity)
        if not user:
            return {}
        return {
            'org_id': user.get('org_id'),
            'email': user.get('email'),
            'role': user.get('role'),
            'role_id': user.get('role'),
            'role_tier': user.get('role_tier'),
            'branch_id': user.get('branch_id'),
            'name': user.get('name'),
        }

    @jwt.token_in_blocklist_loader
    def check_revoked(_jwt_header, jwt_payload):
        jti = jwt_payload.get('jti')
        if not jti:
            return False
        return MongoAPI.is_token_revoked(jti)

    @jwt.expired_token_loader
    def expired_token_callback(_jwt_header, _jwt_payload):
        return jsonify({'msg': 'Token has expired', 'code': 401}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(_error):
        return jsonify({'msg': 'Invalid token', 'code': 401}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(_error):
        return jsonify({'msg': 'Authorization token is missing', 'code': 401}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(_jwt_header, _jwt_payload):
        return jsonify({'msg': 'Token has been revoked', 'code': 401}), 401

    return jwt


def revoke_current_token():
    claims = get_jwt()
    jti = claims.get('jti')
    user_id = claims.get('sub')
    if jti:
        MongoAPI.revoke_token(jti, user_id)
    return jti


def revoke_token_string(token):
    try:
        claims = decode_token(token)
        jti = claims.get('jti')
        user_id = claims.get('sub')
        if jti:
            MongoAPI.revoke_token(jti, user_id)
        return jti
    except Exception:
        return None
