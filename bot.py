import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from app.games import engine
from app.games.engine import ErrCode
from app.db.database import initialize_db

logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)
log = logging.getLogger("ChelseaBot")

TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBAPP_URL= os.getenv("WEBAPP_URL", "https://your-app.onrender.com")
ADMIN_IDS = set(os.getenv("ADMIN_TELEGRAM_IDS", "").split(","))

def main_menu(is_locked=False, locked_game=None):
    games = [("⚽ التشكيلة الرسمية","enter_lineup","lineup"),
             ("🎯 لعبة التوقعات","enter_predictions","predictions"),
             ("🧠 لعبة الأسئلة","enter_trivia","trivia")]
    buttons = []
    for label, cb, key in games:
        if is_locked and key != locked_game:
            buttons.append([InlineKeyboardButton(f"🔒 {label}", callback_data="locked_notice")])
        else:
            buttons.append([InlineKeyboardButton(label, callback_data=cb)])
    buttons.append([InlineKeyboardButton("💎 رصيدي وحالتي", callback_data="my_status")])
    buttons.append([InlineKeyboardButton("🌐 فتح التطبيق", web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(buttons)

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    reg = engine.register_user(str(u.id), u.username, u.full_name)
    user = reg["user"]
    st = engine.get_user_status(str(u.id))
    lock = st.get("lock", {})
    await update.message.reply_html(
        f"🔵 <b>Chelsea FC Games</b>\n\nأهلاً <b>{u.first_name}</b>! 👋\n"
        f"💎 نقاطك: <b>{user['points_balance']:,}</b>\n\nاختر لعبتك:",
        reply_markup=main_menu(lock.get("is_locked"), lock.get("locked_game")))

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    r = engine.get_user_status(str(update.effective_user.id))
    if not r["ok"]:
        await update.message.reply_text("❌ استخدم /start أولاً"); return
    u, lock, sess = r["user"], r["lock"], r.get("active_session")
    lines = [f"👤 <b>{u['name']}</b>", f"💎 النقاط: <b>{u['points_balance']:,}</b>",
             f"💵 الكاش: <b>${u['cash_balance']:.2f}</b>", ""]
    if lock["is_locked"]:
        lines += [f"🔒 مقفل على: <b>{lock['locked_game']}</b>"]
        if sess: lines += [f"📋 اللعبة: {sess.get('display_name','')}"]
    else:
        lines.append("✅ حر — يمكنك دخول أي لعبة")
    await update.message.reply_html("\n".join(lines))

async def cmd_convert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_html("💡 الاستخدام: <code>/convert 10</code>\nالمعدل: 1$ = 100 نقطة"); return
    try: amount = float(ctx.args[0])
    except: await update.message.reply_text("❌ اكتب رقماً. مثال: /convert 10"); return
    r = engine.convert_cash_to_points(str(update.effective_user.id), amount)
    if r["ok"]:
        await update.message.reply_html(f"✅ <b>تم التحويل!</b>\n💎 النقاط المضافة: <b>{r['points_added']:,}</b>\n📊 رصيدك: <b>{r['new_balance']:,}</b> نقطة")
    else:
        await update.message.reply_text(f"❌ {r['message']}")

GAME_MAP = {"enter_lineup":"lineup","enter_predictions":"predictions","enter_trivia":"trivia"}

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid, data = str(q.from_user.id), q.data

    if data == "locked_notice":
        st = engine.get_user_status(tid)
        lock = st.get("lock", {})
        await q.answer(f"🔒 مقفل على: {lock.get('locked_game','؟')}\nلا يمكنك الدخول لأي لعبة أخرى.", show_alert=True)
        return

    if data == "my_status":
        r = engine.get_user_status(tid)
        if r["ok"]:
            u, lock = r["user"], r["lock"]
            text = f"👤 <b>{u['name']}</b>\n💎 {u['points_balance']:,} نقطة\n"
            text += f"🔒 مقفل على: {lock['locked_game']}" if lock["is_locked"] else "✅ حر"
            await q.message.reply_html(text)
        return

    if data in GAME_MAP:
        r = engine.enter_game(tid, GAME_MAP[data])
        if r["ok"]:
            await q.message.reply_html(
                f"{r['icon']} <b>{r['game_name']}</b>\n\n✅ دخلت اللعبة!\n"
                f"💎 مُخصوم: {r['points_spent']:,} نقطة\n📊 رصيدك: {r['points_left']:,} نقطة\n\n"
                f"🔒 <i>حسابك مقفل على هذه اللعبة حتى انتهاء الجولة</i>",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🌐 افتح اللعبة", web_app=WebAppInfo(url=f"{WEBAPP_URL}/game/{GAME_MAP[data]}"))
                ]]))
        elif r["code"] == ErrCode.LOCKED_TO_ANOTHER_GAME:
            await q.message.reply_html(
                f"🔒 <b>لا يمكنك الدخول الآن</b>\n\n"
                f"حسابك مقفل على: <b>{r.get('locked_name','')}</b>\n\n"
                f"⛔ لا يُسمح بالتنقل بين الألعاب خلال الجولة الواحدة.\n"
                f"انتظر انتهاء الجولة أو تواصل مع الآدمن.")
        else:
            await q.message.reply_text(f"❌ {r['message']}")

async def cmd_admin_unlock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMIN_IDS: return
    if not ctx.args: await update.message.reply_text("الاستخدام: /admin_unlock <id> [reason]"); return
    r = engine.admin_unlock_user(str(update.effective_user.id), ctx.args[0],
                                  " ".join(ctx.args[1:]) if len(ctx.args)>1 else "")
    await update.message.reply_html(f"{'✅' if r['ok'] else '❌'} {r['message']}")

async def cmd_admin_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMIN_IDS: return
    r = engine.admin_reset_round(str(update.effective_user.id), " ".join(ctx.args) if ctx.args else "انتهاء الجولة")
    if r["ok"]:
        await update.message.reply_html(f"🔄 <b>تمت إعادة التعيين</b>\n👥 مفكوكون: <b>{r['users_unlocked']}</b>")
    else:
        await update.message.reply_text(f"❌ {r['message']}")

async def cmd_admin_points(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMIN_IDS: return
    if len(ctx.args) < 3: await update.message.reply_text("الاستخدام: /admin_points <id> <amount> <reason>"); return
    try: amount = int(ctx.args[1])
    except: await update.message.reply_text("❌ amount يجب أن يكون رقماً"); return
    r = engine.admin_adjust_points(str(update.effective_user.id), ctx.args[0], amount, " ".join(ctx.args[2:]))
    await update.message.reply_html(f"{'✅' if r['ok'] else '❌'} {r['message']}")

async def cmd_admin_cash(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMIN_IDS: return
    if len(ctx.args) < 2: await update.message.reply_text("الاستخدام: /admin_cash <id> <amount_usd>"); return
    try: amount = float(ctx.args[1])
    except: await update.message.reply_text("❌ amount يجب أن يكون رقماً"); return
    r = engine.admin_add_cash(str(update.effective_user.id), ctx.args[0], amount)
    await update.message.reply_html(f"{'✅' if r['ok'] else '❌'} {r['message']}")

def run_bot():
    if not TOKEN: raise ValueError("TELEGRAM_BOT_TOKEN غير موجود")
    initialize_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("status",        cmd_status))
    app.add_handler(CommandHandler("convert",       cmd_convert))
    app.add_handler(CommandHandler("admin_unlock",  cmd_admin_unlock))
    app.add_handler(CommandHandler("admin_reset",   cmd_admin_reset))
    app.add_handler(CommandHandler("admin_points",  cmd_admin_points))
    app.add_handler(CommandHandler("admin_cash",    cmd_admin_cash))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info("🤖 Chelsea Bot يعمل...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    run_bot()
