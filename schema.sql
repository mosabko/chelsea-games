CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT UNIQUE NOT NULL,
    username TEXT DEFAULT NULL,
    full_name TEXT NOT NULL,
    cash_balance REAL DEFAULT 0.00,
    points_balance INTEGER DEFAULT 0,
    current_game_lock TEXT DEFAULT NULL,
    lock_applied_at DATETIME DEFAULT NULL,
    active_session_id TEXT DEFAULT NULL,
    total_deposited REAL DEFAULT 0.00,
    total_points_spent INTEGER DEFAULT 0,
    games_played INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_admin INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_key TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT DEFAULT NULL,
    icon_emoji TEXT DEFAULT '🎮',
    entry_cost INTEGER NOT NULL,
    prize_pool INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',
    current_players INTEGER DEFAULT 0,
    round_number INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS game_sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    game_id INTEGER NOT NULL REFERENCES games(id),
    game_key TEXT NOT NULL,
    points_spent INTEGER NOT NULL,
    status TEXT DEFAULT 'active',
    score INTEGER DEFAULT 0,
    prize_won INTEGER DEFAULT 0,
    submission_data TEXT DEFAULT NULL,
    submitted_at DATETIME DEFAULT NULL,
    entered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME DEFAULT NULL,
    UNIQUE(user_id, game_key)
);

CREATE TABLE IF NOT EXISTS point_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    session_id TEXT REFERENCES game_sessions(id),
    tx_type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_before INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    cash_usd REAL DEFAULT NULL,
    rate_used INTEGER DEFAULT 100,
    description TEXT,
    ref_admin_id INTEGER REFERENCES users(id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL REFERENCES users(id),
    target_user_id INTEGER REFERENCES users(id),
    action_type TEXT NOT NULL,
    details TEXT DEFAULT NULL,
    reason TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS round_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_by INTEGER NOT NULL REFERENCES users(id),
    users_unlocked INTEGER DEFAULT 0,
    sessions_closed INTEGER DEFAULT 0,
    reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_lock ON users(current_game_lock);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON game_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_key ON game_sessions(game_key, status);
CREATE INDEX IF NOT EXISTS idx_transactions_user ON point_transactions(user_id);

INSERT OR IGNORE INTO games (game_key, display_name, description, icon_emoji, entry_cost, prize_pool) VALUES
    ('lineup',      'لعبة التشكيلة الرسمية', 'توقّع التشكيلة التي سيستخدمها المدرب', '⚽', 50,  500),
    ('predictions', 'لعبة التوقعات',         'توقّع نتيجة المباراة والهدافين',        '🎯', 100, 1000),
    ('trivia',      'لعبة الأسئلة الذكية',   'أجب على أسئلة عن تشيلسي',             '🧠', 30,  300);
