import uuid
import json
from datetime import datetime
from app.db.database import fetchone, fetchall, execute, transaction

CONVERSION_RATE = 100

class ErrCode:
    LOCKED_TO_ANOTHER_GAME = "LOCKED_TO_ANOTHER_GAME"
    ALREADY_IN_GAME        = "ALREADY_IN_GAME"
    ALREADY_SUBMITTED      = "ALREADY_SUBMITTED"
    INSUFFICIENT_POINTS    = "INSUFFICIENT_POINTS"
    INSUFFICIENT_CASH      = "INSUFFICIENT_CASH"
    GAME_NOT_FOUND         = "GAME_NOT_FOUND"
    GAME_CLOSED            = "GAME_CLOSED"
    USER_NOT_FOUND         = "USER_NOT_FOUND"
    USER_BANNED            = "USER_BANNED"
    NOT_IN_GAME            = "NOT_IN_GAME"
    ADMIN_REQUIRED         = "ADMIN_REQUIRED"
    INVALID_AMOUNT         = "INVALID_AMOUNT"

def ok(**data):   return {"ok": True,  **data}
def err(code, message, **extra): return {"ok": False, "code": code, "message": message, **extra}

def register_user(telegram_id, username, full_name):
    existing = fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if existing:
        return ok(user=existing, is_new=False)
    execute("INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
            (telegram_id, username, full_name))
    user = fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return ok(user=user, is_new=True)

def get_user_status(telegram_id):
    user = fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not user:
        return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    session = None
    if user["current_game_lock"]:
        session = fetchone(
            "SELECT gs.*, g.display_name FROM game_sessions gs JOIN games g ON gs.game_key=g.game_key WHERE gs.user_id=? AND gs.status IN ('active','submitted')",
            (user["id"],))
    return ok(
        user={"id": user["id"], "name": user["full_name"], "username": user["username"],
              "points_balance": user["points_balance"], "cash_balance": user["cash_balance"],
              "games_played": user["games_played"]},
        lock={"is_locked": user["current_game_lock"] is not None,
              "locked_game": user["current_game_lock"],
              "locked_since": user["lock_applied_at"],
              "session_id": user["active_session_id"]},
        active_session=dict(session) if session else None)

def convert_cash_to_points(telegram_id, cash_usd):
    if not (1.0 <= cash_usd <= 10000.0):
        return err(ErrCode.INVALID_AMOUNT, "المبلغ يجب أن يكون بين $1 و $10,000")
    user = fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not user:  return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    if user["is_banned"]: return err(ErrCode.USER_BANNED, "الحساب موقوف")
    if user["cash_balance"] < cash_usd:
        return err(ErrCode.INSUFFICIENT_CASH, f"رصيدك (${user['cash_balance']:.2f}) غير كافٍ")
    points = int(cash_usd * CONVERSION_RATE)
    new_pts  = user["points_balance"] + points
    new_cash = round(user["cash_balance"] - cash_usd, 2)
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        conn.execute("UPDATE users SET points_balance=?, cash_balance=?, total_deposited=total_deposited+?, updated_at=? WHERE telegram_id=?",
                     (new_pts, new_cash, cash_usd, now, telegram_id))
        conn.execute("INSERT INTO point_transactions (user_id,tx_type,amount,balance_before,balance_after,cash_usd,rate_used,description) VALUES (?,?,?,?,?,?,?,?)",
                     (user["id"],'cash_to_points',points,user["points_balance"],new_pts,cash_usd,CONVERSION_RATE,f"تحويل ${cash_usd:.2f} ← {points} نقطة"))
    return ok(message=f"✅ تم التحويل: ${cash_usd:.2f} = {points:,} نقطة",
              points_added=points, new_balance=new_pts, cash_remaining=new_cash)

def enter_game(telegram_id, game_key):
    user = fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not user:  return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    if user["is_banned"]: return err(ErrCode.USER_BANNED, "الحساب موقوف")
    game = fetchone("SELECT * FROM games WHERE game_key = ?", (game_key,))
    if not game:  return err(ErrCode.GAME_NOT_FOUND, "اللعبة غير موجودة")
    if game["status"] != "open": return err(ErrCode.GAME_CLOSED, f"{game['display_name']} مغلقة حالياً")

    # ══════════════════════════════════════════
    # 🔒 نظام القفل الصارم — لا استثناءات
    # ══════════════════════════════════════════
    if user["current_game_lock"] is not None:
        if user["current_game_lock"] != game_key:
            locked = fetchone("SELECT display_name FROM games WHERE game_key=?", (user["current_game_lock"],))
            locked_name = locked["display_name"] if locked else user["current_game_lock"]
            return err(ErrCode.LOCKED_TO_ANOTHER_GAME,
                       f"🔒 حسابك مقفل على {locked_name}\nلا يمكنك الدخول لأي لعبة أخرى حتى تنتهي الجولة أو يفك الآدمن القفل.",
                       locked_on=user["current_game_lock"], locked_name=locked_name)
        return err(ErrCode.ALREADY_IN_GAME, f"أنت بالفعل داخل {game['display_name']}")
    # ══════════════════════════════════════════

    if user["points_balance"] < game["entry_cost"]:
        return err(ErrCode.INSUFFICIENT_POINTS,
                   f"رصيدك ({user['points_balance']:,}) لا يكفي. المطلوب: {game['entry_cost']:,} نقطة")

    session_id  = str(uuid.uuid4())
    new_balance = user["points_balance"] - game["entry_cost"]
    now = datetime.utcnow().isoformat()

    with transaction() as conn:
        conn.execute("UPDATE users SET points_balance=?, current_game_lock=?, lock_applied_at=?, active_session_id=?, total_points_spent=total_points_spent+?, updated_at=? WHERE telegram_id=?",
                     (new_balance, game_key, now, session_id, game["entry_cost"], now, telegram_id))
        conn.execute("INSERT INTO game_sessions (id,user_id,game_id,game_key,points_spent,status) VALUES (?,?,?,?,?,'active')",
                     (session_id, user["id"], game["id"], game_key, game["entry_cost"]))
        conn.execute("UPDATE games SET current_players=current_players+1 WHERE game_key=?", (game_key,))
        conn.execute("INSERT INTO point_transactions (user_id,session_id,tx_type,amount,balance_before,balance_after,description) VALUES (?,?,'game_entry',?,?,?,?)",
                     (user["id"], session_id, -game["entry_cost"], user["points_balance"], new_balance,
                      f"دخول {game['display_name']} — خصم {game['entry_cost']:,} نقطة"))

    return ok(message=f"🎮 تم الدخول إلى {game['display_name']}", session_id=session_id,
              game_key=game_key, game_name=game["display_name"], icon=game["icon_emoji"],
              points_spent=game["entry_cost"], points_left=new_balance, prize_pool=game["prize_pool"],
              lock_note="🔒 حسابك مقفل — لا يمكن دخول لعبة أخرى حتى انتهاء الجولة")

def submit_answer(telegram_id, game_key, submission):
    user = fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    if not user: return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    session = fetchone("SELECT * FROM game_sessions WHERE user_id=? AND game_key=? AND status IN ('active','submitted')",
                       (user["id"], game_key))
    if not session: return err(ErrCode.NOT_IN_GAME, "أنت لست في هذه اللعبة")
    if session["status"] == "submitted" or session["submitted_at"]:
        return err(ErrCode.ALREADY_SUBMITTED, "لقد قدّمت إجاباتك مسبقاً")
    now = datetime.utcnow().isoformat()
    execute("UPDATE game_sessions SET submission_data=?, submitted_at=?, status='submitted' WHERE id=?",
            (json.dumps(submission, ensure_ascii=False), now, session["id"]))
    return ok(message="✅ تم تسليم إجاباتك", session_id=session["id"], submitted_at=now)

def admin_unlock_user(admin_tid, target_tid, reason=""):
    admin = fetchone("SELECT * FROM users WHERE telegram_id=?", (admin_tid,))
    if not admin or not admin["is_admin"]: return err(ErrCode.ADMIN_REQUIRED, "⛔ للآدمن فقط")
    target = fetchone("SELECT * FROM users WHERE telegram_id=?", (target_tid,))
    if not target: return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    if not target["current_game_lock"]:
        return ok(message=f"{target['full_name']} ليس مقفلاً")
    unlocked_from = target["current_game_lock"]
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        conn.execute("UPDATE game_sessions SET status='cancelled', completed_at=? WHERE user_id=? AND status IN ('active','submitted')",
                     (now, target["id"]))
        conn.execute("UPDATE users SET current_game_lock=NULL, lock_applied_at=NULL, active_session_id=NULL, updated_at=? WHERE telegram_id=?",
                     (now, target_tid))
        conn.execute("UPDATE games SET current_players=MAX(0,current_players-1) WHERE game_key=?", (unlocked_from,))
        conn.execute("INSERT INTO admin_actions (admin_id,target_user_id,action_type,reason) VALUES (?,?,'unlock_user',?)",
                     (admin["id"], target["id"], reason or "فك قفل يدوي"))
    return ok(message=f"🔓 تم فك قفل {target['full_name']}", unlocked_from=unlocked_from,
              by_admin=admin["full_name"], reason=reason)

def admin_reset_round(admin_tid, reason="انتهاء الجولة"):
    admin = fetchone("SELECT * FROM users WHERE telegram_id=?", (admin_tid,))
    if not admin or not admin["is_admin"]: return err(ErrCode.ADMIN_REQUIRED, "⛔ للآدمن فقط")
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        s = conn.execute("UPDATE game_sessions SET status='completed', completed_at=? WHERE status IN ('active','submitted')", (now,))
        u = conn.execute("UPDATE users SET current_game_lock=NULL, lock_applied_at=NULL, active_session_id=NULL, updated_at=? WHERE current_game_lock IS NOT NULL", (now,))
        conn.execute("UPDATE games SET current_players=0, round_number=round_number+1")
        conn.execute("INSERT INTO round_resets (triggered_by,users_unlocked,sessions_closed,reason) VALUES (?,?,?,?)",
                     (admin["id"], u.rowcount, s.rowcount, reason))
    return ok(message="🔄 تمت إعادة تعيين الجولة", users_unlocked=u.rowcount,
              sessions_closed=s.rowcount, reset_by=admin["full_name"])

def admin_adjust_points(admin_tid, target_tid, amount, reason):
    admin = fetchone("SELECT * FROM users WHERE telegram_id=?", (admin_tid,))
    if not admin or not admin["is_admin"]: return err(ErrCode.ADMIN_REQUIRED, "⛔ للآدمن فقط")
    target = fetchone("SELECT * FROM users WHERE telegram_id=?", (target_tid,))
    if not target: return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    new_bal = target["points_balance"] + amount
    if new_bal < 0: return err(ErrCode.INSUFFICIENT_POINTS, "الرصيد سيصبح سالباً")
    now = datetime.utcnow().isoformat()
    with transaction() as conn:
        conn.execute("UPDATE users SET points_balance=?, updated_at=? WHERE telegram_id=?", (new_bal, now, target_tid))
        conn.execute("INSERT INTO point_transactions (user_id,tx_type,amount,balance_before,balance_after,description,ref_admin_id) VALUES (?,?,?,?,?,?,?)",
                     (target["id"], "admin_credit" if amount>0 else "admin_debit",
                      amount, target["points_balance"], new_bal, reason, admin["id"]))
    return ok(message=f"✅ تم تعديل رصيد {target['full_name']}", new_balance=new_bal)

def admin_add_cash(admin_tid, target_tid, amount_usd, reason=""):
    admin = fetchone("SELECT * FROM users WHERE telegram_id=?", (admin_tid,))
    if not admin or not admin["is_admin"]: return err(ErrCode.ADMIN_REQUIRED, "⛔ للآدمن فقط")
    target = fetchone("SELECT * FROM users WHERE telegram_id=?", (target_tid,))
    if not target: return err(ErrCode.USER_NOT_FOUND, "المشترك غير موجود")
    new_cash = round(target["cash_balance"] + amount_usd, 2)
    execute("UPDATE users SET cash_balance=?, total_deposited=total_deposited+? WHERE telegram_id=?",
            (new_cash, amount_usd, target_tid))
    return ok(message=f"💵 تمت إضافة ${amount_usd:.2f} لـ {target['full_name']}", new_cash=new_cash)

def list_games():
    games = fetchall("SELECT * FROM games WHERE status='open' ORDER BY entry_cost")
    return ok(games=games, count=len(games))

def get_leaderboard(game_key, limit=10):
    rows = fetchall(
        "SELECT u.full_name, u.username, gs.score, gs.rank, gs.prize_won FROM game_sessions gs JOIN users u ON gs.user_id=u.id WHERE gs.game_key=? AND gs.status IN ('completed','submitted') ORDER BY gs.score DESC LIMIT ?",
        (game_key, limit))
    return ok(leaderboard=rows, game_key=game_key)
