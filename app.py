import yfinance as yf
import numpy as np
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
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except:
        pass

    return {
        "email_enabled": False,
        "email_address": ""
    }


def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)


# =========================
# EMAIL
# =========================
def send_email(message, to_email):
    url = "https://api.resend.com/emails"

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "from": "Bot <onboarding@resend.dev>",
        "to": [to_email],
        "subject": "Trading Alert",
        "html": f"<pre>{message}</pre>"
    }

    requests.post(url, headers=headers, json=data)


# =========================
# SEND (Telegram + Email)
# =========================
def send(msg):
    config = load_config()

    # TELEGRAM
    if SEND_TELEGRAM:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=5)
        except Exception as e:
            print("Telegram error:", e)

    # EMAIL
    if config.get("email_enabled"):
        email = config.get("email_address")

        if email:
            try:
                send_email(msg, email)
            except Exception as e:
                print("Email error:", e)


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
# STRATEGY
# =========================
def get_signal():
    df = yf.download("NQ=F", period="1d", interval="5m")

    if df is None or df.empty or len(df) < 50:
        return None

    df["ema"] = df["Close"].ewm(span=20).mean()

    price = float(df["Close"].iloc[-1])
    ema = float(df["ema"].iloc[-1])

    # jednoduchá logika
    if price > ema:
        direction = "LONG"
    elif price < ema:
        direction = "SHORT"
    else:
        return None

    # ATR pre trailing
    df["tr"] = np.maximum(
        df["High"] - df["Low"],
        np.maximum(
            abs(df["High"] - df["Close"].shift()),
            abs(df["Low"] - df["Close"].shift())
        )
    )
    df["atr"] = df["tr"].rolling(14).mean()
    atr = df["atr"].iloc[-1]

    sl = price - atr if direction == "LONG" else price + atr
    trail = atr  # veľkosť trailing stopu

    return {
        "symbol": "NQ=F",
        "direction": direction,
        "price": float(price),
        "sl": float(sl),
        "trail": float(trail)
    }


# =========================
# FORMAT MESSAGE
# =========================
def format_msg(signal):
    return f"""
📈 TRADE SIGNAL

Symbol: {signal['symbol']}
Direction: {signal['direction']}

Entry: {signal['price']:.2f}
SL: {signal['sl']:.2f}
Trailing Stop: {signal['trail']:.2f}
"""


# =========================
# RUN (pre appku)
# =========================
@app.route("/run")
def run():
    signal = get_signal()

    if not signal:
        return "NO TRADE"

    return format_msg(signal)


# =========================
# AUTO (alerty)
# =========================
@app.route("/auto")
def auto():
    signal = get_signal()

    if not signal:
        return "NO TRADE"

    last = load_trade()

    # anti spam
    if last and last.get("direction") == signal["direction"]:
        return "SKIP (same signal)"

    save_trade(signal)

    msg = format_msg(signal)
    send(msg)

    return "SENT"


# =========================
# SETTINGS (z appky)
# =========================
@app.route("/settings", methods=["POST"])
def settings():
    email_flag = request.form.get("email")
    email_address = request.form.get("email_address")

    config = {
        "email_enabled": email_flag == "on",
        "email_address": email_address
    }

    save_config(config)

    return "OK"


# =========================
# CONFIG (pre appku)
# =========================
@app.route("/config")
def config():
    return jsonify(load_config())


# =========================
# START
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
