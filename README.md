# MAP Backend — REST API

Flask backend for MAP (authentication, CRM, and related APIs).

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

API: `http://localhost:5000`  
MongoDB: configure via `MONGO_URI` in `.env`

## Health check

- `GET /` or `GET /health` — returns `{"status": "ok", "service": "map-backend"}`

## Auth endpoints

- `POST /login`
- `POST /signup`
- `POST /otp_verify_match`
- `POST /resend_otp`
- `POST /login_resend_otp`
- `POST /forgot_password_check`
- `POST /creat_new_password`
- `POST /logout` — revoke current access token

## JWT usage

Send the access token on protected routes:

```
Authorization: Bearer <access_token>
```

Tokens include claims: `org_id`, `email`, `role`, `name`.

## Environment

| Variable | Purpose |
|----------|---------|
| `BASE_URL` | Public URL of this API (file/attachment links) |
| `CLIENT_APP_URL` | Optional separate client app URL for email deep links |
| `MONGO_URI` | MongoDB connection string |
| `JWT_SECRET_KEY` | JWT signing secret |

## Production

```bash
gunicorn -w 4 -b 0.0.0.0:5000 "app:app"
```

