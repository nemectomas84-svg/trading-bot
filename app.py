import yfinance as yf
import numpy as np
import pandas as pd
import requests
import json
import os
from flask import Flask, jsonify

# =========================
BOT_TOKEN = "8764608057:AAGkxxNSFVWKDYmCeP6L-_FG5Dq-NFa0-lk"
CHAT_ID = "1950077580"
SEND_TELEGRAM = True
# =========================

FILE = "trade.json"
app = Flask(__name__)


# =========================
# TELEGRAM
# =========================
def send(msg):
    if SEND_TELEGRAM:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=5)
        except Exception as e:
            print("Telegram error:", e)


def log(msg, logs):
    print(msg)
    logs.append(msg)


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

    # =====================
    # ENTRY
    # =====================
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

            # LONG
            if ema50 > ema200 and c > high20 + atr * 0.2:

                trade = {
                    "symbol": symbol,
                    "direction": "LONG",
                    "entry": c,
                    "stop": c - atr * 2,
                    "last_sl": c - atr * 2
                }

                save_trade(trade)

                msg = f"📈 ENTRY\nSymbol: {symbol}\nType: LONG\nEntry: {round(c,2)}\nSL: {round(trade['stop'],2)}"
                send(msg)
                log(msg, logs)

                return logs

            # SHORT
            elif ema50 < ema200 and c < low20 - atr * 0.2:

                trade = {
                    "symbol": symbol,
                    "direction": "SHORT",
                    "entry": c,
                    "stop": c + atr * 2,
                    "last_sl": c + atr * 2
                }

                save_trade(trade)

                msg = f"📉 ENTRY\nSymbol: {symbol}\nType: SHORT\nEntry: {round(c,2)}\nSL: {round(trade['stop'],2)}"
                send(msg)
                log(msg, logs)

                return logs

        log("NO TRADE", logs)
        return logs

    # =====================
    # TRAILING
    # =====================
    else:

        df = get_data(trade["symbol"])
        if df is None:
            log("DATA ERROR", logs)
            return logs

        last = df.iloc[-1]

        price = float(last["Close"])
        atr = float(last["ATR"])

        entry = trade["entry"]
        stop = trade["stop"]

        # =====================
        # LONG
        # =====================
        if trade["direction"] == "LONG":

            profit = price - entry

            if profit > atr * 2 and stop < entry:
                trade["stop"] = entry
                trade["last_sl"] = entry
                msg = "SL → BREAK EVEN"
                send(msg)
                log(msg, logs)

            new_sl = price - atr * 1.5

            if new_sl > trade["stop"]:
                if abs(new_sl - trade["last_sl"]) > atr * 0.5:

                    trade["stop"] = new_sl
                    trade["last_sl"] = new_sl

                    msg = f"🔁 TRAILING\nSymbol: {trade['symbol']}\nNew SL: {round(new_sl,2)}"
                    send(msg)
                    log(msg, logs)

            if price <= trade["stop"]:
                profit = price - entry

                msg = f"❌ EXIT\nSymbol: {trade['symbol']}\nResult: {round(profit,2)}"
                send(msg)
                log(msg, logs)

                delete_trade()
                return logs

        # =====================
        # SHORT
        # =====================
        else:

            profit = entry - price

            if profit > atr * 2 and stop > entry:
                trade["stop"] = entry
                trade["last_sl"] = entry
                msg = "SL → BREAK EVEN"
                send(msg)
                log(msg, logs)

            new_sl = price + atr * 1.5

            if new_sl < trade["stop"]:
                if abs(new_sl - trade["last_sl"]) > atr * 0.5:

                    trade["stop"] = new_sl
                    trade["last_sl"] = new_sl

                    msg = f"🔁 TRAILING\nSymbol: {trade['symbol']}\nNew SL: {round(new_sl,2)}"
                    send(msg)
                    log(msg, logs)

            if price >= trade["stop"]:
                msg = f"❌ EXIT\nSymbol: {trade['symbol']}\nReason: SL HIT"
                send(msg)
                log(msg, logs)

                delete_trade()
                return logs

        save_trade(trade)
        log("Trade managed", logs)
        return logs


# =========================
# API
# =========================
@app.route("/", methods=["GET"])
def home():
    return "BOT BEZI"


@app.route("/run", methods=["GET"])
def run_manual():
    logs = main(send_tg=False)
    return "<br>".join(logs)


@app.route("/auto", methods=["GET"])
def run_auto():
    logs = main(send_tg=True)
    return jsonify({"logs": logs})


# =========================
# START SERVER (RENDER FIX)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
