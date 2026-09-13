# Security controls

Implemented controls include:

- PBKDF2 password hashing with per-password salts.
- JWT access tokens and one-use, hashed refresh-token rotation.
- Generic authentication failures and in-process login throttling.
- Backend RBAC and organization-scoped vehicle, device, GPS, incident,
  notification, analytics, and report access.
- Fernet encryption for device secrets at rest.
- HMAC device attestation, timestamp freshness, nonce replay protection, and
  device revocation.
- FastAPI request validation, CORS allow-list configuration, request IDs,
  `nosniff`, clickjacking, and referrer protections.
- Append-only audit records for authentication and safety operations.
- No raw biometric data is collected by the demonstrator.

## Required production controls

Set a strong `JWT_SECRET` and persistent `DEVICE_ENCRYPTION_KEY` through a
secret manager. Use HTTPS, managed PostgreSQL, a shared rate-limit store,
centralized logs, key rotation, MFA/SSO, dependency scanning, database
migrations, backups, retention controls, and independent penetration testing.
Do not connect this web service directly to a vehicle relay without certified
hardware, secure boot, signed firmware, a separate vehicle gateway, watchdogs,
manual recovery, and jurisdictional approval.

