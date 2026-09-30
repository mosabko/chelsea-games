import os, threading
from flask import Flask
from app.db.database import initialize_db
from app.routes.api import api

app = Flask(__name__)
app.register_blueprint(api)

@app.route("/")
def index():
    return {"service": "Chelsea FC Games", "version": "2.0", "status": "running"}

def start_bot():
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        from app.telegram.bot import run_bot
        run_bot()

if __name__ == "__main__":
    initialize_db()
    if os.getenv("RUN_BOT", "true").lower() == "true":
        threading.Thread(target=start_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
