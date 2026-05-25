import yfinance as yf
import numpy as np
import pandas as pd
import requests
import json
import os
from flask import Flask, jsonify, request

# =========================
BOT_TOKEN = "8764608057:AAGkxxNSFVWKDYmCeP6L-_FG5Dq-NFa0-lk"
CHAT_ID = "1950077580"
SEND_TELEGRAM = True
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
    import smtplib
    from email.mime.text import MIMEText

    sender = "nemec.tomas84@gmail.com"
    password = "phlnwehwvwmomzzc"  # !!! Gmail app password

    msg = MIMEText(message)
    msg["Subject"] = "Trading Bot"
    msg["From"] = sender
    msg["To"] = to_email

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender, password)
    server.send_message(msg)
    server.quit()

@app.route("/test-email")
def test_email():
    try:
        send_email(
            "🧪 TEST EMAIL z Trading Botu funguje!",
            "nemec.tomas84@gmail.com"
        )
        return "EMAIL POSLANY"
    except Exception as e:
        return f"CHYBA: {e}"
        
# =========================
# TELEGRAM + EMAIL
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
        try:
            send_email(msg, config.get("email_address"))
        except Exception as e:
            print("Email error:", e)


def log(msg, logs):
    print(msg)
    logs.append(msg)


# =========================
# SETTINGS (checkbox save)
# =========================
@app.route("/settings", methods=["POST"])
def settings():
    email_enabled = request.form.get("email") == "on"
    email_address = request.form.get("email_address")

    save_config({
        "email_enabled": email_enabled,
        "email_address": email_address
    })

    return "ULOZENE"


# =========================
# FILE STORAGE
# =========================
def load_trade():
    try:
        if os.path.exists(FILE):
            with open(FILE, "r") as f:
                return json.load(f)
    except:
        return None
    return None


def save_trade(trade):
    with open(FILE, "w") as f:
        json.dump(trade, f)


def delete_trade():
    if os.path.exists(FILE):
        os.remove(FILE)


# =========================
# DATA
# =========================
def get_data(symbol):
    try:
        df = yf.download(symbol, interval="1h", period="60d")

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna()

        close = df["Close"].astype(float)
        high = df["High"].astype(float)
        low = df["Low"].astype(float)

        df["EMA50"] = close.ewm(span=50).mean()
        df["EMA200"] = close.ewm(span=200).mean()

        df["HIGH_20"] = high.rolling(20).max()
        df["LOW_20"] = low.rolling(20).min()

        df["TR"] = np.maximum(
            high - low,
            np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1)))
        )
        df["ATR"] = df["TR"].rolling(14).mean()

        return df.dropna()

    except Exception as e:
        print("DATA ERROR:", e)
        return None


# =========================
# MAIN LOGIC
# =========================
def main(send_tg=True):
    global SEND_TELEGRAM
    SEND_TELEGRAM = send_tg

    logs = []
    trade = load_trade()

    symbols = ["GC=F", "NQ=F"]

    if not trade:
        for symbol in symbols:
            df = get_data(symbol)
            if df is None:
                continue

            last = df.iloc[-1]

            c = float(last["Close"])
            ema50 = float(last["EMA50"])
            ema200 = float(last["EMA200"])
            high20 = float(df["HIGH_20"].iloc[-2])
            low20 = float(df["LOW_20"].iloc[-2])
            atr = float(last["ATR"])

            if ema50 > ema200 and c > high20 + atr * 0.2:
                trade = {
                    "symbol": symbol,
                    "direction": "LONG",
                    "entry": c,
                    "stop": c - atr * 2,
                    "last_sl": c - atr * 2
                }

                save_trade(trade)

                msg = f"📈 ENTRY {symbol} LONG {round(c,2)}"
                send(msg)
                log(msg, logs)
                return logs

            elif ema50 < ema200 and c < low20 - atr * 0.2:
                trade = {
                    "symbol": symbol,
                    "direction": "SHORT",
                    "entry": c,
                    "stop": c + atr * 2,
                    "last_sl": c + atr * 2
                }

                save_trade(trade)

                msg = f"📉 ENTRY {symbol} SHORT {round(c,2)}"
                send(msg)
                log(msg, logs)
                return logs

        log("NO TRADE", logs)
        return logs

    else:
        df = get_data(trade["symbol"])
        if df is None:
            return logs

        last = df.iloc[-1]
        price = float(last["Close"])
        atr = float(last["ATR"])

        entry = trade["entry"]

        if trade["direction"] == "LONG":
            if price <= trade["stop"]:
                msg = f"❌ EXIT {trade['symbol']}"
                send(msg)
                delete_trade()
                log(msg, logs)
                return logs

        else:
            if price >= trade["stop"]:
                msg = f"❌ EXIT {trade['symbol']}"
                send(msg)
                delete_trade()
                log(msg, logs)
                return logs

        save_trade(trade)
        log("Trade managed", logs)
        return logs


# =========================
# API
# =========================
@app.route("/")
def home():
    return "BOT BEZI"


@app.route("/run")
def run_manual():
    logs = main(send_tg=False)
    return "<br>".join(logs)


@app.route("/auto")
def run_auto():
    logs = main(send_tg=True)
    return jsonify({"logs": logs})


# =========================
# START
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
