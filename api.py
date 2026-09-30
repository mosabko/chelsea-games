from flask import Blueprint, request, jsonify
from app.games import engine
from app.games.engine import ErrCode

api = Blueprint("api", __name__, url_prefix="/api")

def get_tid():
    return (request.headers.get("X-Telegram-Id") or
            (request.json or {}).get("telegram_id") or
            request.args.get("telegram_id"))

def resp(result, ok_status=200):
    status = ok_status if result.get("ok") else {
        ErrCode.LOCKED_TO_ANOTHER_GAME: 403,
        ErrCode.INSUFFICIENT_POINTS: 402,
        ErrCode.INSUFFICIENT_CASH: 402,
        ErrCode.GAME_NOT_FOUND: 404,
        ErrCode.USER_NOT_FOUND: 404,
        ErrCode.GAME_CLOSED: 409,
        ErrCode.ALREADY_IN_GAME: 409,
        ErrCode.USER_BANNED: 403,
        ErrCode.ADMIN_REQUIRED: 403,
    }.get(result.get("code", ""), 400)
    return jsonify(result), status

@api.get("/health")
def health():
    return jsonify({"ok": True, "service": "Chelsea FC Games"})

@api.post("/users/register")
def register():
    d = request.json or {}
    tid, name = str(d.get("telegram_id","")).strip(), str(d.get("full_name","")).strip()
    if not tid or not name:
        return jsonify({"ok":False,"message":"telegram_id و full_name مطلوبان"}), 400
    return resp(engine.register_user(tid, d.get("username"), name), 201)

@api.get("/users/status")
def user_status():
    tid = get_tid()
    if not tid: return jsonify({"ok":False,"message":"X-Telegram-Id مطلوب"}), 401
    return resp(engine.get_user_status(tid))

@api.post("/points/convert")
def convert_points():
    tid = get_tid()
    if not tid: return jsonify({"ok":False,"message":"X-Telegram-Id مطلوب"}), 401
    try: amount = float((request.json or {}).get("cash_amount", 0))
    except: return jsonify({"ok":False,"message":"cash_amount يجب أن يكون رقماً"}), 400
    return resp(engine.convert_cash_to_points(tid, amount))

@api.get("/games")
def games_list():
    return resp(engine.list_games())

@api.post("/games/enter")
def enter_game():
    tid = get_tid()
    if not tid: return jsonify({"ok":False,"message":"X-Telegram-Id مطلوب"}), 401
    game_key = str((request.json or {}).get("game_key","")).strip()
    if not game_key: return jsonify({"ok":False,"message":"game_key مطلوب"}), 400
    return resp(engine.enter_game(tid, game_key))

@api.post("/games/submit")
def submit():
    tid = get_tid()
    if not tid: return jsonify({"ok":False,"message":"X-Telegram-Id مطلوب"}), 401
    d = request.json or {}
    return resp(engine.submit_answer(tid, d.get("game_key"), d.get("submission")))

@api.get("/games/<game_key>/leaderboard")
def leaderboard(game_key):
    return resp(engine.get_leaderboard(game_key, min(int(request.args.get("limit",10)),50)))

@api.post("/admin/unlock")
def admin_unlock():
    tid = get_tid()
    d = request.json or {}
    return resp(engine.admin_unlock_user(tid, str(d.get("target_telegram_id","")), d.get("reason","")))

@api.post("/admin/reset-round")
def admin_reset():
    tid = get_tid()
    if not tid: return jsonify({"ok":False,"message":"X-Telegram-Id مطلوب"}), 401
    d = request.json or {}
    return resp(engine.admin_reset_round(tid, d.get("reason","انتهاء الجولة")))

@api.post("/admin/adjust-points")
def admin_adjust():
    tid = get_tid()
    d = request.json or {}
    return resp(engine.admin_adjust_points(tid, str(d.get("target_telegram_id","")),
                                           int(d.get("amount",0)), d.get("reason","")))

@api.post("/admin/add-cash")
def admin_cash():
    tid = get_tid()
    d = request.json or {}
    return resp(engine.admin_add_cash(tid, str(d.get("target_telegram_id","")),
                                      float(d.get("amount_usd",0)), d.get("reason","")))
