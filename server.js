const path = require('node:path');
const crypto = require('node:crypto');
const fs = require('node:fs');
const express = require('express');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const bcrypt = require('bcryptjs');
const initSqlJs = require('sql.js');
const { z } = require('zod');

const PORT = Number(process.env.PORT || 3000);
// Vercel's deployment filesystem is read-only except for /tmp. The SQLite
// database remains suitable for the single-instance demo deployment only;
// production scale requires PostgreSQL/Redis via services/api.
const DB_PATH = process.env.DB_PATH
  || (process.env.VERCEL ? path.join('/tmp', 'tensorhub.db') : path.join(__dirname, 'data', 'tensorhub.db'));
const SESSION_SECRET = process.env.SESSION_SECRET || crypto.randomBytes(32).toString('hex');
const TECHNICAL_TEAM_EMAIL = process.env.TECHNICAL_TEAM_EMAIL;
const TECHNICAL_TEAM_PASSWORD = process.env.TECHNICAL_TEAM_PASSWORD;
const APP_ORIGIN = process.env.APP_ORIGIN;
const INTERLOCK_ATTESTATION_SECRET = process.env.INTERLOCK_ATTESTATION_SECRET;
const configuredAttestationAge = Number(process.env.ATTESTATION_MAX_AGE_MS);
const ATTESTATION_MAX_AGE_MS = Number.isFinite(configuredAttestationAge) && configuredAttestationAge > 0 ? configuredAttestationAge : 300000;
const configuredThreshold = Number(process.env.ALCOHOL_THRESHOLD);
const ALCOHOL_THRESHOLD = Number.isFinite(configuredThreshold) && configuredThreshold >= 0 ? configuredThreshold : 0.02;
fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
async function main() {
const SQL = await initSqlJs({ locateFile: (file) => path.join(__dirname, 'node_modules', 'sql.js', 'dist', file) });
const db = new SQL.Database(fs.existsSync(DB_PATH) ? new Uint8Array(fs.readFileSync(DB_PATH)) : undefined);
const sql = (statement) => {
  const prepared = db.prepare(statement.replace(/@([A-Za-z_][A-Za-z0-9_]*)/g, '$$$1'));
  const bindValues = (values) => { if (!values.length) return; const value = values.length === 1 && values[0] && typeof values[0] === 'object' && !Array.isArray(values[0]) ? Object.fromEntries(Object.entries(values[0]).map(([key, item]) => [`$${key}`, item])) : values; prepared.bind(value); };
  return {
    run: (...values) => { bindValues(values); while (prepared.step()) {} const changes = db.getRowsModified(); const lastInsertRowid = db.exec('SELECT last_insert_rowid() AS id')[0]?.values[0]?.[0]; prepared.free(); persist(); return { changes, lastInsertRowid }; },
    get: (...values) => { bindValues(values); const value = prepared.step() ? prepared.getAsObject() : undefined; prepared.free(); return value; },
    all: (...values) => { bindValues(values); const rows = []; while (prepared.step()) rows.push(prepared.getAsObject()); prepared.free(); return rows; }
  };
};
const persist = () => fs.writeFileSync(DB_PATH, Buffer.from(db.export()));
db.run(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'MEMBER',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS sessions (
    id_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS sessions_expires_idx ON sessions(expires_at);
  CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL, starts_at TEXT NOT NULL, ends_at TEXT,
    location TEXT NOT NULL, registration_url TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS events_listing_idx ON events(published, starts_at);
  CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
    language TEXT NOT NULL, starter_code TEXT NOT NULL DEFAULT '', created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    user_id INTEGER NOT NULL REFERENCES users(id), source_code TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'QUEUED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS submissions_user_idx ON submissions(user_id, created_at);
  CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT, metadata TEXT NOT NULL DEFAULT '{}',
    ip TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS audit_logs_created_idx ON audit_logs(created_at);
  CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'OPEN',
    resolution TEXT, resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT
  );
  CREATE INDEX IF NOT EXISTS reports_status_idx ON reports(status, created_at);
  CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, read_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications(user_id, read_at, created_at);
  CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS interlock_vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    vin TEXT NOT NULL UNIQUE, make TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'LOCKED' CHECK (state IN ('LOCKED','UNLOCKED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS interlock_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL UNIQUE,
    vehicle_id INTEGER REFERENCES interlock_vehicles(id) ON DELETE SET NULL,
    secret_ciphertext TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS interlock_nonces (
    device_id TEXT NOT NULL, nonce TEXT NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id, nonce)
  );
  CREATE TABLE IF NOT EXISTS interlock_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER, device_id TEXT, decision TEXT NOT NULL,
    reason TEXT NOT NULL, reading REAL, attested INTEGER NOT NULL DEFAULT 0,
    nonce TEXT, measured_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
`);

const app = express();
app.set('trust proxy', Number(process.env.TRUST_PROXY || 0));
app.use(helmet({ crossOriginResourcePolicy: { policy: 'cross-origin' } }));
app.use(express.json({ limit: '100kb' }));
app.use(express.urlencoded({ extended: false, limit: '20kb' }));
app.use(rateLimit({ windowMs: 60 * 1000, limit: 120, standardHeaders: 'draft-7', legacyHeaders: false }));
app.use(express.static(path.join(__dirname, 'public'), { maxAge: '1h' }));

const emailSchema = z.string().trim().email().max(254).transform((v) => v.toLowerCase());
const passwordSchema = z.string().min(12).max(128);
const eventSchema = z.object({
  title: z.string().trim().min(3).max(160),
  description: z.string().trim().min(10).max(10000),
  startsAt: z.string().datetime({ offset: true }),
  endsAt: z.string().datetime({ offset: true }).optional().nullable(),
  location: z.string().trim().min(2).max(200),
  registrationUrl: z.string().url().refine((v) => ['http:', 'https:'].includes(new URL(v).protocol), 'HTTPS or HTTP URL required'),
  published: z.boolean().optional().default(true)
});
const slugify = (value) => `${value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}-${crypto.randomBytes(3).toString('hex')}`;
const hashToken = (token) => crypto.createHmac('sha256', SESSION_SECRET).update(token).digest('hex');
const encryptionKey = crypto.createHash('sha256').update(SESSION_SECRET).digest();
const encryptSecret = (secret) => {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', encryptionKey, iv);
  const value = Buffer.concat([cipher.update(secret, 'utf8'), cipher.final()]);
  return `${iv.toString('base64url')}.${cipher.getAuthTag().toString('base64url')}.${value.toString('base64url')}`;
};
const decryptSecret = (encoded) => {
  const [iv, tag, value] = encoded.split('.'); const decipher = crypto.createDecipheriv('aes-256-gcm', encryptionKey, Buffer.from(iv, 'base64url'));
  decipher.setAuthTag(Buffer.from(tag, 'base64url')); return Buffer.concat([decipher.update(Buffer.from(value, 'base64url')), decipher.final()]).toString('utf8');
};
const publicUser = (user) => ({ id: user.id, name: user.name, email: user.email, role: user.role });
const issue = (res, status, message, details) => res.status(status).json({ error: message, ...(details ? { details } : {}) });
const audit = (req, action, entityType, entityId, metadata = {}) => sql(
  'INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,metadata,ip) VALUES (?,?,?,?,?,?)'
).run(req.user?.id || null, action, entityType, entityId == null ? null : String(entityId), JSON.stringify(metadata), req.ip || null);
const notify = (userId, type, title, message) => sql(
  'INSERT INTO notifications (user_id,type,title,message) VALUES (?,?,?,?)'
).run(userId, type, title, message);
if (TECHNICAL_TEAM_EMAIL && TECHNICAL_TEAM_PASSWORD) {
  const email = emailSchema.parse(TECHNICAL_TEAM_EMAIL);
  passwordSchema.parse(TECHNICAL_TEAM_PASSWORD);
  const existing = sql('SELECT id FROM users WHERE email=?').get(email);
  if (existing) sql('UPDATE users SET role=? WHERE id=?').run('TECHNICAL_TEAM', existing.id);
  else sql('INSERT INTO users (name,email,password_hash,role) VALUES (?,?,?,?)').run(
    'TensorHub Technical Team', email, bcrypt.hashSync(TECHNICAL_TEAM_PASSWORD, 12), 'TECHNICAL_TEAM'
  );
}

function setSession(res, userId) {
  const token = crypto.randomBytes(32).toString('base64url');
  sql('INSERT INTO sessions (id_hash, user_id, expires_at) VALUES (?, ?, datetime("now", "+7 days"))').run(hashToken(token), userId);
  res.cookie('tensorhub_session', token, {
    httpOnly: true, secure: process.env.NODE_ENV === 'production', sameSite: 'lax', maxAge: 7 * 86400000, path: '/'
  });
}
function clearSession(req, res) {
  const token = req.headers.cookie?.match(/(?:^|;\s*)tensorhub_session=([^;]+)/)?.[1];
  if (token) sql('DELETE FROM sessions WHERE id_hash = ?').run(hashToken(token));
  res.clearCookie('tensorhub_session', { httpOnly: true, secure: process.env.NODE_ENV === 'production', sameSite: 'lax', path: '/' });
}
function loadUser(req) {
  const token = req.headers.cookie?.match(/(?:^|;\s*)tensorhub_session=([^;]+)/)?.[1];
  if (!token) return null;
  return sql(`SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
    WHERE s.id_hash=? AND s.expires_at > datetime('now')`).get(hashToken(token)) || null;
}
function requireAuth(req, res, next) {
  req.user = loadUser(req);
  if (!req.user) return issue(res, 401, 'Authentication required');
  next();
}
function requireTechnicalTeam(req, res, next) {
  if (!['TECHNICAL_TEAM', 'ADMIN'].includes(req.user.role)) return issue(res, 403, 'Technical Team role required');
  next();
}
function requireAdmin(req, res, next) {
  if (req.user.role !== 'ADMIN') return issue(res, 403, 'Administrator role required');
  next();
}
function parseBody(schema, req, res) {
  const parsed = schema.safeParse(req.body);
  if (!parsed.success) { issue(res, 400, 'Invalid request', parsed.error.flatten().fieldErrors); return null; }
  return parsed.data;
}
function requireSameOrigin(req, res, next) {
  if (!['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method)) return next();
  const source = req.get('origin') || req.get('referer');
  if (!source) return issue(res, 403, 'Origin header required');
  try {
    const expected = APP_ORIGIN ? new URL(APP_ORIGIN).origin : `${req.protocol}://${req.get('host')}`;
    if (new URL(source).origin !== expected) return issue(res, 403, 'Cross-origin request blocked');
  } catch { return issue(res, 403, 'Invalid request origin'); }
  next();
}
app.use('/api', requireSameOrigin);

app.get('/api/health', (_req, res) => res.json({ ok: true, service: 'tensorhub' }));
app.post('/api/auth/register', rateLimit({ windowMs: 15 * 60 * 1000, limit: 10 }), (req, res) => {
  const parsed = z.object({ name: z.string().trim().min(2).max(100), email: emailSchema, password: passwordSchema }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Name, valid email, and password of at least 12 characters are required');
  const { name, email, password } = parsed.data;
  try {
    const result = sql('INSERT INTO users (name,email,password_hash) VALUES (?,?,?)').run(name, email, bcrypt.hashSync(password, 12));
    const user = sql('SELECT * FROM users WHERE id=?').get(result.lastInsertRowid);
    audit(req, 'REGISTER', 'USER', user.id);
    setSession(res, user.id);
    res.status(201).json({ user: publicUser(user) });
  } catch (error) {
    if (error.code === 'SQLITE_CONSTRAINT_UNIQUE') return issue(res, 409, 'An account with that email already exists');
    throw error;
  }
});
app.post('/api/auth/login', rateLimit({ windowMs: 15 * 60 * 1000, limit: 10 }), (req, res) => {
  const parsed = z.object({ email: emailSchema, password: z.string().min(1).max(128) }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Email and password are required');
  const user = sql('SELECT * FROM users WHERE email=?').get(parsed.data.email);
  if (!user || !bcrypt.compareSync(parsed.data.password, user.password_hash)) return issue(res, 401, 'Invalid email or password');
  setSession(res, user.id);
  audit(req, 'LOGIN', 'USER', user.id);
  res.json({ user: publicUser(user) });
});
app.post('/api/auth/logout', (req, res) => { clearSession(req, res); res.status(204).end(); });
app.get('/api/auth/me', (req, res) => { const user = loadUser(req); res.json({ user: user ? publicUser(user) : null }); });
app.post('/api/auth/password-reset/request', rateLimit({ windowMs: 15 * 60 * 1000, limit: 5 }), (req, res) => {
  const parsed = z.object({ email: emailSchema }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Valid email is required');
  const user = sql('SELECT id FROM users WHERE email=?').get(parsed.data.email);
  if (user) {
    const token = crypto.randomBytes(32).toString('base64url');
    sql("DELETE FROM password_reset_tokens WHERE user_id=?").run(user.id);
    sql("INSERT INTO password_reset_tokens (token_hash,user_id,expires_at) VALUES (?,?,datetime('now','+30 minutes'))").run(hashToken(token), user.id);
    audit(req, 'PASSWORD_RESET_REQUESTED', 'USER', user.id);
    if (process.env.NODE_ENV !== 'production') return res.json({ ok: true, developmentToken: token });
  }
  res.json({ ok: true, message: 'If that account exists, reset instructions will be sent.' });
});
app.post('/api/auth/password-reset/complete', (req, res) => {
  const parsed = z.object({ token: z.string().min(20).max(200), password: passwordSchema }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Valid reset token and password of at least 12 characters are required');
  const token = sql("SELECT user_id FROM password_reset_tokens WHERE token_hash=? AND used_at IS NULL AND expires_at > datetime('now')").get(hashToken(parsed.data.token));
  if (!token) return issue(res, 400, 'Reset token is invalid or expired');
  sql('UPDATE users SET password_hash=? WHERE id=?').run(bcrypt.hashSync(parsed.data.password, 12), token.user_id);
  sql("UPDATE password_reset_tokens SET used_at=datetime('now') WHERE token_hash=?").run(hashToken(parsed.data.token));
  sql('DELETE FROM sessions WHERE user_id=?').run(token.user_id);
  audit(req, 'PASSWORD_RESET_COMPLETED', 'USER', token.user_id);
  res.json({ ok: true });
});

// Versioned vehicle interlock demonstrator API. A decision is fail-secure: any
// missing, stale, replayed, or unverifiable device report keeps the vehicle locked.
const interlockDeviceSchema = z.object({
  deviceId: z.string().trim().min(3).max(100),
  vehicleId: z.coerce.number().int().positive(),
  nonce: z.string().trim().min(16).max(200),
  timestamp: z.string().datetime({ offset: true }),
  signature: z.string().trim().min(16).max(256),
  reading: z.coerce.number().finite().min(0).max(10)
});
const decisionFor = (reading, valid) => {
  if (!valid) return { decision: 'LOCKED', reason: 'ATTESTATION_INVALID' };
  return reading < ALCOHOL_THRESHOLD
    ? { decision: 'UNLOCKED', reason: 'ALCOHOL_BELOW_THRESHOLD' }
    : { decision: 'LOCKED', reason: 'ALCOHOL_THRESHOLD_EXCEEDED' };
};
function verifyInterlockReport(data) {
  const device = sql('SELECT * FROM interlock_devices WHERE device_id=? AND active=1').get(data.deviceId);
  if (!device || Number(device.vehicle_id) !== data.vehicleId) return { valid: false, device };
  const measured = Date.parse(data.timestamp);
  if (!Number.isFinite(measured) || Math.abs(Date.now() - measured) > ATTESTATION_MAX_AGE_MS) return { valid: false, device };
  try {
    const message = `${data.deviceId}.${data.vehicleId}.${data.nonce}.${data.timestamp}.${data.reading}`;
    const expected = crypto.createHmac('sha256', decryptSecret(device.secret_ciphertext)).update(message).digest('hex');
    const supplied = data.signature.replace(/^sha256=/, '').toLowerCase();
    if (supplied.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))) return { valid: false, device };
    try { sql('INSERT INTO interlock_nonces (device_id,nonce) VALUES (?,?)').run(data.deviceId, data.nonce); } catch { return { valid: false, device, replay: true }; }
    return { valid: true, device };
  } catch { return { valid: false, device }; }
}
function recordInterlockDecision(data, result, valid) {
  sql(`INSERT INTO interlock_decisions
    (vehicle_id,device_id,decision,reason,reading,attested,nonce,measured_at)
    VALUES (?,?,?,?,?,?,?,?)`).run(data.vehicleId, data.deviceId, result.decision, result.reason,
    data.reading, valid ? 1 : 0, data.nonce || null, data.timestamp || null);
  sql('UPDATE interlock_vehicles SET state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?').run(result.decision, data.vehicleId);
  sql(`INSERT INTO audit_logs (actor_id,action,entity_type,entity_id,metadata,ip)
    VALUES (NULL,?,?,?,?,NULL)`).run('INTERLOCK_DECISION', 'INTERLOCK_VEHICLE', String(data.vehicleId),
    JSON.stringify({ deviceId: data.deviceId || null, decision: result.decision, reason: result.reason, attested: valid }));
}
app.use('/api/v1/interlock', (req, res, next) => {
  if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return requireSameOrigin(req, res, next);
  next();
});
app.post('/api/v1/interlock/devices', requireAuth, requireTechnicalTeam, (req, res) => {
  const parsed = z.object({ deviceId: z.string().trim().min(3).max(100), vehicleId: z.coerce.number().int().positive(), secret: z.string().min(16).max(256).optional() }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'deviceId, vehicleId, and a secret of at least 16 characters are required');
  if (!sql('SELECT id FROM interlock_vehicles WHERE id=?').get(parsed.data.vehicleId)) return issue(res, 404, 'Vehicle not found');
  const secret = parsed.data.secret || INTERLOCK_ATTESTATION_SECRET || crypto.randomBytes(32).toString('hex');
  try {
    const result = sql('INSERT INTO interlock_devices (device_id,vehicle_id,secret_ciphertext) VALUES (?,?,?)').run(parsed.data.deviceId, parsed.data.vehicleId, encryptSecret(secret));
    audit(req, 'REGISTER', 'INTERLOCK_DEVICE', result.lastInsertRowid, { deviceId: parsed.data.deviceId });
    res.status(201).json({ deviceId: parsed.data.deviceId, vehicleId: parsed.data.vehicleId, secret });
  } catch (error) { if (error.message?.includes('UNIQUE')) return issue(res, 409, 'Device already exists'); throw error; }
});
app.post('/api/v1/interlock/vehicles', requireAuth, (req, res) => {
  const parsed = z.object({ vin: z.string().trim().regex(/^[A-Za-z0-9-]{6,32}$/), make: z.string().trim().max(80).default(''), model: z.string().trim().max(80).default('') }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'A valid vehicle identification number is required');
  try {
    const result = sql('INSERT INTO interlock_vehicles (user_id,vin,make,model) VALUES (?,?,?,?)').run(req.user.id, parsed.data.vin, parsed.data.make, parsed.data.model);
    audit(req, 'CREATE', 'INTERLOCK_VEHICLE', result.lastInsertRowid);
    res.status(201).json({ vehicle: sql('SELECT id,vin,make,model,state,created_at createdAt FROM interlock_vehicles WHERE id=?').get(result.lastInsertRowid) });
  } catch (error) { if (error.message?.includes('UNIQUE')) return issue(res, 409, 'Vehicle already exists'); throw error; }
});
app.get('/api/v1/interlock/vehicles', requireAuth, (req, res) => res.json({ vehicles: sql('SELECT id,vin,make,model,state,created_at createdAt,updated_at updatedAt FROM interlock_vehicles WHERE user_id=? ORDER BY id DESC').all(req.user.id) }));
app.get('/api/v1/interlock/operations/vehicles', requireAuth, requireTechnicalTeam, (_req, res) => res.json({
  vehicles: sql(`SELECT v.id,v.vin,v.make,v.model,v.state,v.user_id userId,
    u.name ownerName,u.email ownerEmail,d.device_id deviceId,d.active deviceActive
    FROM interlock_vehicles v LEFT JOIN users u ON u.id=v.user_id
    LEFT JOIN interlock_devices d ON d.vehicle_id=v.id ORDER BY v.id DESC LIMIT 500`).all()
}));
app.get('/api/v1/interlock/operations/devices', requireAuth, requireTechnicalTeam, (_req, res) => res.json({
  devices: sql(`SELECT d.device_id deviceId,d.vehicle_id vehicleId,d.active,d.created_at createdAt,
    v.vin,v.make,v.model FROM interlock_devices d LEFT JOIN interlock_vehicles v ON v.id=d.vehicle_id
    ORDER BY d.created_at DESC LIMIT 500`).all()
}));
app.post(['/api/v1/interlock/attest', '/api/v1/interlock/decision', '/api/v1/interlock/decisions', '/api/v1/interlock/simulator/attest'], (req, res) => {
  const parsed = interlockDeviceSchema.safeParse(req.body);
  const data = parsed.success ? parsed.data : (req.body || {});
  const attestation = parsed.success ? verifyInterlockReport(data) : { valid: false };
  const result = decisionFor(Number(data.reading), attestation.valid);
  // Never let an unauthenticated malformed request mutate an arbitrary vehicle.
  // Only a known device-to-vehicle pairing may create a persistent fail-secure record.
  if (attestation.device && Number(attestation.device.vehicle_id) === Number(data.vehicleId)) {
    recordInterlockDecision(data, result, attestation.valid);
  }
  res.status(attestation.valid ? 200 : 401).json({ decision: result.decision, reason: result.reason, attested: attestation.valid, failSecure: !attestation.valid });
});
app.get('/api/v1/interlock/vehicles/:id', requireAuth, (req, res) => {
  const vehicle = sql('SELECT id,vin,make,model,state,created_at createdAt,updated_at updatedAt FROM interlock_vehicles WHERE id=? AND user_id=?').get(req.params.id, req.user.id);
  if (!vehicle) return issue(res, 404, 'Vehicle not found');
  res.json({ vehicle });
});
app.get('/api/v1/interlock/vehicles/:id/decisions', requireAuth, (req, res) => {
  const vehicle = sql('SELECT id FROM interlock_vehicles WHERE id=? AND user_id=?').get(req.params.id, req.user.id);
  if (!vehicle) return issue(res, 404, 'Vehicle not found');
  res.json({ decisions: sql(`SELECT id,vehicle_id vehicleId,device_id deviceId,decision,reason,reading,attested,nonce,measured_at measuredAt,created_at createdAt
    FROM interlock_decisions WHERE vehicle_id=? ORDER BY id DESC LIMIT 100`).all(vehicle.id) });
});

app.get('/api/events', (req, res) => {
  const page = Math.max(1, Math.min(10000, Number.parseInt(req.query.page, 10) || 1));
  const limit = Math.max(1, Math.min(50, Number.parseInt(req.query.limit, 10) || 12));
  const search = String(req.query.search || '').trim().slice(0, 100);
  const where = search ? 'WHERE published=1 AND (title LIKE @search OR description LIKE @search OR location LIKE @search)' : 'WHERE published=1';
  const params = search ? { search: `%${search}%` } : {};
  const total = sql(`SELECT COUNT(*) count FROM events ${where}`).get(params).count;
  const events = sql(`SELECT id,title,slug,description,starts_at startsAt,ends_at endsAt,location,registration_url registrationUrl
    FROM events ${where} ORDER BY starts_at ASC LIMIT @limit OFFSET @offset`).all({ ...params, limit, offset: (page - 1) * limit });
  res.json({ events, page, limit, total, pages: Math.ceil(total / limit) });
});
app.get('/api/events/:slug', (req, res) => {
  const event = sql(`SELECT id,title,slug,description,starts_at startsAt,ends_at endsAt,location,registration_url registrationUrl
    FROM events WHERE slug=? AND published=1`).get(req.params.slug);
  if (!event) return issue(res, 404, 'Event not found');
  res.json({ event });
});
app.use('/api/manage', requireAuth, requireTechnicalTeam);
app.post('/api/manage/events', (req, res) => {
  const data = parseBody(eventSchema, req, res); if (!data) return;
  if (data.endsAt && new Date(data.endsAt) <= new Date(data.startsAt)) return issue(res, 400, 'End time must be after start time');
  const result = sql(`INSERT INTO events (title,slug,description,starts_at,ends_at,location,registration_url,published,created_by)
    VALUES (@title,@slug,@description,@startsAt,@endsAt,@location,@registrationUrl,@published,@createdBy)`).run({ ...data, slug: slugify(data.title), createdBy: req.user.id });
  res.status(201).json({ event: sql('SELECT * FROM events WHERE id=?').get(result.lastInsertRowid) });
  audit(req, 'CREATE', 'EVENT', result.lastInsertRowid, { title: data.title });
});
app.patch('/api/manage/events/:id', (req, res) => {
  const data = parseBody(eventSchema.partial(), req, res); if (!data) return;
  const current = sql('SELECT * FROM events WHERE id=?').get(req.params.id);
  if (!current) return issue(res, 404, 'Event not found');
  const next = { ...current, ...data };
  if (next.endsAt && new Date(next.endsAt) <= new Date(next.startsAt)) return issue(res, 400, 'End time must be after start time');
  sql(`UPDATE events SET title=@title,description=@description,starts_at=@startsAt,ends_at=@endsAt,location=@location,
    registration_url=@registrationUrl,published=@published,updated_at=CURRENT_TIMESTAMP WHERE id=@id`).run({
    ...next, id: current.id, startsAt: next.startsAt, endsAt: next.endsAt, registrationUrl: next.registrationUrl, published: next.published ? 1 : 0
  });
  res.json({ event: sql('SELECT * FROM events WHERE id=?').get(current.id) });
});
app.delete('/api/manage/events/:id', (req, res) => {
  const result = sql('DELETE FROM events WHERE id=?').run(req.params.id);
  if (!result.changes) return issue(res, 404, 'Event not found');
  audit(req, 'DELETE', 'EVENT', req.params.id);
  res.status(204).end();
});
app.get('/api/challenges', (_req, res) => res.json({ challenges: sql('SELECT id,title,description,language,starter_code starterCode FROM challenges ORDER BY created_at DESC LIMIT 100').all() }));
app.get('/api/challenges/:id', (req, res) => {
  const challenge = sql('SELECT id,title,description,language,starter_code starterCode FROM challenges WHERE id=?').get(req.params.id);
  if (!challenge) return issue(res, 404, 'Challenge not found');
  res.json({ challenge });
});
app.post('/api/challenges/:id/submissions', requireAuth, rateLimit({ windowMs: 60 * 1000, limit: 10 }), (req, res) => {
  const challenge = sql('SELECT id FROM challenges WHERE id=?').get(req.params.id);
  if (!challenge) return issue(res, 404, 'Challenge not found');
  const parsed = z.object({ sourceCode: z.string().min(1).max(50000) }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Source code is required and must be at most 50,000 characters');
  const result = sql('INSERT INTO submissions (challenge_id,user_id,source_code,status) VALUES (?,?,?,?)').run(challenge.id, req.user.id, parsed.data.sourceCode, 'QUEUED');
  res.status(202).json({ submission: { id: result.lastInsertRowid, status: 'QUEUED', message: 'Submission queued for isolated worker processing.' } });
});
app.post('/api/manage/challenges', (req, res) => {
  const parsed = z.object({ title: z.string().trim().min(3).max(160), description: z.string().trim().min(10).max(10000), language: z.string().trim().min(1).max(40), starterCode: z.string().max(50000).default('') }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Invalid challenge');
  const result = sql('INSERT INTO challenges (title,description,language,starter_code,created_by) VALUES (?,?,?,?,?)').run(parsed.data.title, parsed.data.description, parsed.data.language, parsed.data.starterCode, req.user.id);
  audit(req, 'CREATE', 'CHALLENGE', result.lastInsertRowid, { title: parsed.data.title });
  res.status(201).json({ id: result.lastInsertRowid });
});
app.post('/api/reports', requireAuth, (req, res) => {
  const parsed = z.object({ entityType: z.enum(['EVENT', 'CHALLENGE']), entityId: z.string().max(50), reason: z.string().trim().min(10).max(1000) }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'A valid content type, id, and reason are required');
  const result = sql('INSERT INTO reports (reporter_id,entity_type,entity_id,reason) VALUES (?,?,?,?)').run(req.user.id, parsed.data.entityType, parsed.data.entityId, parsed.data.reason);
  audit(req, 'REPORT', parsed.data.entityType, parsed.data.entityId);
  res.status(201).json({ reportId: result.lastInsertRowid, status: 'OPEN' });
});
app.get('/api/notifications', requireAuth, (req, res) => res.json({ notifications: sql('SELECT id,type,title,message,read_at readAt,created_at createdAt FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50').all(req.user.id) }));
app.post('/api/notifications/:id/read', requireAuth, (req, res) => { const result = sql("UPDATE notifications SET read_at=datetime('now') WHERE id=? AND user_id=?").run(req.params.id, req.user.id); if (!result.changes) return issue(res, 404, 'Notification not found'); res.status(204).end(); });
app.use('/api/admin', requireAuth, requireAdmin);
app.get('/api/admin/users', (req, res) => {
  const page = Math.max(1, Number.parseInt(req.query.page, 10) || 1);
  const limit = Math.min(50, Math.max(1, Number.parseInt(req.query.limit, 10) || 25));
  const users = sql('SELECT id,name,email,role,created_at createdAt FROM users ORDER BY created_at DESC LIMIT @limit OFFSET @offset').all({ limit, offset: (page - 1) * limit });
  res.json({ users, page, limit });
});
app.patch('/api/admin/users/:id/role', (req, res) => {
  const parsed = z.object({ role: z.enum(['MEMBER', 'TECHNICAL_TEAM', 'ADMIN']) }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Invalid role');
  if (Number(req.params.id) === req.user.id && parsed.data.role !== 'ADMIN') return issue(res, 400, 'You cannot remove your own administrator role');
  const result = sql('UPDATE users SET role=? WHERE id=?').run(parsed.data.role, req.params.id);
  if (!result.changes) return issue(res, 404, 'User not found');
  audit(req, 'ROLE_CHANGED', 'USER', req.params.id, { role: parsed.data.role });
  notify(Number(req.params.id), 'ROLE_CHANGED', 'Role updated', `Your TensorHub role is now ${parsed.data.role}.`);
  res.json({ ok: true });
});
app.get('/api/admin/reports', (req, res) => res.json({ reports: sql('SELECT id,reporter_id reporterId,entity_type entityType,entity_id entityId,reason,status,resolution,created_at createdAt FROM reports ORDER BY created_at DESC LIMIT 100').all() }));
app.patch('/api/admin/reports/:id', (req, res) => {
  const parsed = z.object({ status: z.enum(['OPEN', 'RESOLVED', 'DISMISSED']), resolution: z.string().trim().max(1000).optional().default('') }).safeParse(req.body);
  if (!parsed.success) return issue(res, 400, 'Invalid moderation update');
  const result = sql("UPDATE reports SET status=?,resolution=?,resolved_by=?,resolved_at=datetime('now') WHERE id=?").run(parsed.data.status, parsed.data.resolution, req.user.id, req.params.id);
  if (!result.changes) return issue(res, 404, 'Report not found');
  audit(req, 'MODERATION_UPDATE', 'REPORT', req.params.id, parsed.data);
  res.json({ ok: true });
});
app.get('/api/admin/audit-logs', (req, res) => res.json({ logs: sql('SELECT id,actor_id actorId,action,entity_type entityType,entity_id entityId,metadata,ip,created_at createdAt FROM audit_logs ORDER BY created_at DESC LIMIT 200').all() }));

app.use((error, _req, res, _next) => {
  console.error(error);
  if (!res.headersSent) res.status(500).json({ error: 'Internal server error' });
});
app.get('*', (req, res, next) => req.path.startsWith('/api/') ? issue(res, 404, 'Not found') : res.sendFile(path.join(__dirname, 'public', 'index.html'), (error) => error ? next(error) : undefined));
sql("DELETE FROM sessions WHERE expires_at <= datetime('now')").run();
const server = app.listen(PORT, '0.0.0.0', () => console.log(`TensorHub listening on 0.0.0.0:${server.address().port}`));
const shutdown = () => { server.close(() => { persist(); db.close(); process.exit(0); }); };
process.on('SIGTERM', shutdown); process.on('SIGINT', shutdown);
}
main().catch((error) => { console.error(error); process.exit(1); });
