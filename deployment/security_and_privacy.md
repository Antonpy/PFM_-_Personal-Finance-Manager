# Security & Privacy Deployment Guide (Stage G)

## 1) Authentication

- User accounts are stored in `models/users.json`.
- Passwords are **not** stored in plain text.
- Password hashing:
  - Algorithm: `PBKDF2-HMAC-SHA256`
  - Iterations: `310000`
  - Salt: per-user random 16 bytes
- Authentication flow implemented in `auth.py`.

## 2) Encryption at Rest (AES)

- User transactions are stored encrypted in `models/user_data/<user_id>.transactions.enc.json`.
- Encryption algorithm: **AES-256-GCM** (authenticated encryption).
- Nonce: random 12 bytes per encryption operation.
- Encryption key is derived per user from password + per-user encryption salt (PBKDF2).
- Implemented in `secure_store.py`.

This satisfies the requirement to avoid plain storage of banking transaction amounts on server-side.

## 3) TLS in Transit

The Streamlit app must be published only behind HTTPS/TLS.

Recommended production pattern:
- Streamlit runs in private network.
- Reverse proxy (Nginx/Caddy/Traefik) terminates TLS.
- HTTP is redirected to HTTPS.
- Use modern TLS config (TLS 1.2+, strong ciphers).

> Important: this repository configures in-app warnings and secure storage logic, but TLS termination is infrastructure-level and must be configured in deployment environment.

## 4) PII / Banking Data Warnings & Consent

- UI shows explicit warning that user works with banking/PII data.
- UI includes consent checkbox for storing PII/banking data.
- If consent is disabled, encrypted server-side save is blocked in app flow.

## 5) Data Deletion Policy (GDPR/local requirements)

Implemented user-driven full deletion flow in UI:
- Deletes encrypted transaction payload.
- Deletes per-user rule files and anomaly feedback files.
- Deletes user account.

Deletion is irreversible and confirmed by explicit typed confirmation (`DELETE`).

## 6) Russia-specific operational notes

For production handling of personal/banking data, account for:
- 152-FZ and internal local data governance requirements.
- Data localization obligations (where applicable to your legal setup).
- Data retention limits and access control/audit practices.

This project already includes user notification and full deletion capability; legal compliance still requires organization-level legal review and infrastructure controls.

## 7) Operational hardening checklist

Before production release:
- [ ] Ensure `cryptography` package is installed in runtime.
- [ ] Enforce HTTPS-only access at reverse proxy/LB.
- [ ] Restrict file-system access permissions for `models/` directory.
- [ ] Add secrets management for platform-level credentials.
- [ ] Enable server logs with sensitive data redaction.
- [ ] Add periodic backup/restore policy with encrypted backups.
