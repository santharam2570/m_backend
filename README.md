# MAP Backend — Authentication API

Auth-only Flask backend for MAP (login, signup, OTP, password reset).

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

API: `http://localhost:5001`  
MongoDB: `localhost:27017` / database `map_backend`

## Endpoints

- `POST /login`
- `POST /signup`
- `POST /otp_verify_match`
- `POST /resend_otp`
- `POST /login_resend_otp`
- `POST /forgot_password_check`
- `POST /creat_new_password`
- `POST /refresh` — refresh access token (requires refresh token in `Authorization: Bearer <token>`)
- `POST /logout` — revoke current access token
- `GET /me` — current user profile (requires access token)
- `POST /add_lead` — create lead (requires access token)

## JWT usage

Send the access token on protected routes:

```
Authorization: Bearer <access_token>
```

For `/refresh`, send the refresh token instead. Tokens include claims: `org_id`, `email`, `role`, `name`.
