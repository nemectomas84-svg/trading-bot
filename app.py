import yfinance as yf
import pandas as pd
import requests
import json
import os
from flask import Flask, jsonify, request

# =========================
# TELEGRAM
# =========================
BOT_TOKEN = "8764608057:AAGkxxNSFVWKDYmCeP6L-_FG5Dq-NFa0-lk"
CHAT_ID = "1950077580"
SEND_TELEGRAM = True

# =========================
# EMAIL (RESEND)
# =========================
RESEND_API_KEY = "re_6NxT7WKB_N1QMzY4jCsQvrQeBgrYig31s"

# =========================
FILE = "trade.json"
CONFIG_FILE = "config.json"

app = Flask(__name__)

# =========================
# CONFIG
# =========================
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"email_enabled": False, "email_address": ""}


def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

# =========================
# TRADE STORAGE
# =========================
def load_trade():
    if os.path.exists(FILE):
        with open(FILE, "r") as f:
            return json.load(f)
    return None


def save_trade(data):
    with open(FILE, "w") as f:
        json.dump(data, f)

# =========================
# EMAIL
# =========================
def send_email(message, to_email):
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "from": "bot@resend.dev",
        "to": [to_email],
        "subject": "Trade Alert",
        "text": message
    }

    requests.post("https://api.resend.com/emails", headers=headers, json=data)

# =========================
# SEND
# =========================
def send(msg):
    config = load_config()

    if SEND_TELEGRAM:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=5)
        except Exception as e:
            print("Telegram error:", e)

    if config.get("email_enabled"):
        email = config.get("email_address")
        if email:
            send_email(msg, email)

# =========================
# SIGNAL
# =========================
def get_signal():
    df = yf.download("NQ=F", period="1d", interval="5m")

    if df.empty:
        return None

    df["ema"] = df["Close"].ewm(span=20).mean()

    price = df["Close"].iloc[-1].item()
    ema = df["ema"].iloc[-1].item()

    if price > ema:
        return "LONG", price
    elif price < ema:
        return "SHORT", price

    return None

# =========================
# AUTO LOGIKA
# =========================
@app.route("/auto")
def auto():
    trade = load_trade()
    signal = get_signal()

    if signal is None:
        return "no data"

    direction, price = signal

    trailing_distance = 40

    # =====================
    # NOVÝ TRADE
    # =====================
    if trade is None:
        if direction == "LONG":
            sl = price - trailing_distance
            trail = price - trailing_distance
        else:
            sl = price + trailing_distance
            trail = price + trailing_distance

        trade = {
            "direction": direction,
            "entry": price,
            "sl": sl,
            "trail": trail
        }

        save_trade(trade)

        msg = f"""
📈 NEW TRADE

{direction}
Entry: {price:.2f}
SL: {sl:.2f}
Trailing: {trail:.2f}
"""
        send(msg)
        return msg

    # =====================
    # EXISTUJÚCI TRADE
    # =====================
    direction = trade["direction"]
    sl = trade["sl"]
    trail = trade["trail"]

    # LONG
    if direction == "LONG":
        # trailing update
        new_trail = price - trailing_distance
        if new_trail > trail:
            trade["trail"] = new_trail
            save_trade(trade)
            send(f"🔄 TRAIL MOVED: {new_trail:.2f}")

        # exit
        if price <= trade["trail"]:
            send(f"❌ EXIT LONG {price:.2f}")
            save_trade(None)
            return "closed"

    # SHORT
    if direction == "SHORT":
        new_trail = price + trailing_distance
        if new_trail < trail:
            trade["trail"] = new_trail
            save_trade(trade)
            send(f"🔄 TRAIL MOVED: {new_trail:.2f}")

        if price >= trade["trail"]:
            send(f"❌ EXIT SHORT {price:.2f}")
            save_trade(None)
            return "closed"

    return "running"

# =========================
# MANUAL RUN (APPKA)
# =========================
@app.route("/run")
def run():
    signal = get_signal()

    if signal is None:
        return jsonify({"msg": "No data"})

    direction, price = signal

    return jsonify({
        "direction": direction,
        "price": round(price, 2)
    })

# =========================
# SETTINGS (APP)
# =========================
@app.route("/settings", methods=["POST"])
def settings():
    data = request.json
    save_config(data)
    return jsonify({"status": "ok"})

@app.route("/config")
def config():
    return jsonify(load_config())

# =========================
# START
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
