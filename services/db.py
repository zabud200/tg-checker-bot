import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH, FREE_TRIAL_CHECKS

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            lang TEXT DEFAULT 'ru',
            role TEXT DEFAULT 'user',
            subscription_end TEXT,
            free_checks_left INTEGER DEFAULT 3,
            referred_by INTEGER,
            referral_balance REAL DEFAULT 0,
            referral_earned_total REAL DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, channel_username TEXT, category TEXT,
            subs INTEGER, avg_reach INTEGER, err REAL, quality_score INTEGER,
            verdict TEXT, checked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS channels_cache (
            username TEXT PRIMARY KEY, category TEXT,
            last_subs INTEGER, last_err REAL, last_checked TEXT
        );
        CREATE TABLE IF NOT EXISTS blacklist (
            username TEXT PRIMARY KEY, reason TEXT, added_by INTEGER, added_at TEXT
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER, referral_id INTEGER,
            bonus_days INTEGER, commission REAL, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount REAL, status TEXT DEFAULT 'pending',
            requested_at TEXT, paid_at TEXT
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount INTEGER, plan TEXT, payload TEXT,
            created_at TEXT
        );
        """)

def get_user(uid):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE telegram_id=?", (uid,)).fetchone()

def create_user(uid, username, referred_by=None):
    with conn() as c:
        c.execute("""INSERT OR IGNORE INTO users 
            (telegram_id, username, lang, role, free_checks_left, referred_by, created_at)
            VALUES (?, ?, 'ru', 'user', ?, ?, ?)""",
            (uid, username, FREE_TRIAL_CHECKS, referred_by, datetime.now().isoformat()))

def set_lang(uid, lang):
    with conn() as c:
        c.execute("UPDATE users SET lang=? WHERE telegram_id=?", (lang, uid))

def has_access(uid):
    u = get_user(uid)
    if not u: return False
    if u["role"] in ("admin", "owner"): return True
    if u["free_checks_left"] and u["free_checks_left"] > 0: return True
    if u["subscription_end"]:
        return datetime.fromisoformat(u["subscription_end"]) > datetime.now()
    return False

def consume_check(uid):
    u = get_user(uid)
    if u and u["free_checks_left"] and u["free_checks_left"] > 0:
        with conn() as c:
            c.execute("UPDATE users SET free_checks_left=free_checks_left-1 WHERE telegram_id=?", (uid,))

def add_subscription(uid, days):
    u = get_user(uid)
    base = datetime.now()
    if u and u["subscription_end"]:
        cur = datetime.fromisoformat(u["subscription_end"])
        if cur > base: base = cur
    new = (base + timedelta(days=days)).isoformat()
    with conn() as c:
        c.execute("UPDATE users SET subscription_end=? WHERE telegram_id=?", (new, uid))
    return new

def save_check(uid, username, category, subs, reach, err, qs, verdict):
    with conn() as c:
        c.execute("""INSERT INTO checks 
            (user_id, channel_username, category, subs, avg_reach, err, quality_score, verdict, checked_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (uid, username, category, subs, reach, err, qs, verdict, datetime.now().isoformat()))
        c.execute("""INSERT OR REPLACE INTO channels_cache 
            (username, category, last_subs, last_err, last_checked) VALUES (?,?,?,?,?)""",
            (username, category, subs, err, datetime.now().isoformat()))

def avg_err_by_category(category):
    with conn() as c:
        r = c.execute("SELECT AVG(err) FROM checks WHERE LOWER(category)=LOWER(?)", (category,)).fetchone()
        return r[0] or 0.0

def in_blacklist(username):
    with conn() as c:
        return c.execute("SELECT reason FROM blacklist WHERE username=?", (username,)).fetchone()

def add_blacklist(username, reason, by):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO blacklist VALUES (?,?,?,?)",
                  (username, reason, by, datetime.now().isoformat()))

def user_history(uid, limit=10):
    with conn() as c:
        return c.execute("SELECT * FROM checks WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit)).fetchall()

def set_role(uid, role):
    with conn() as c:
        c.execute("UPDATE users SET role=? WHERE telegram_id=?", (role, uid))

def all_users(limit=20):
    with conn() as c:
        return c.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

def add_referral(referrer_id, referral_id, bonus_days, commission):
    with conn() as c:
        c.execute("INSERT INTO referrals (referrer_id, referral_id, bonus_days, commission, created_at) VALUES (?,?,?,?,?)",
                  (referrer_id, referral_id, bonus_days, commission, datetime.now().isoformat()))
        c.execute("UPDATE users SET referral_balance=referral_balance+?, referral_earned_total=referral_earned_total+? WHERE telegram_id=?",
                  (commission, commission, referrer_id))

def request_payout(uid, amount):
    with conn() as c:
        c.execute("INSERT INTO payouts (user_id, amount, requested_at) VALUES (?,?,?)",
                  (uid, amount, datetime.now().isoformat()))
        c.execute("UPDATE users SET referral_balance=referral_balance-? WHERE telegram_id=?", (amount, uid))

def save_payment(uid, amount, plan, payload):
    with conn() as c:
        c.execute("INSERT INTO payments (user_id, amount, plan, payload, created_at) VALUES (?,?,?,?,?)",
                  (uid, amount, plan, payload, datetime.now().isoformat()))
