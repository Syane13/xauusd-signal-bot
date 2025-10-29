import requests, time, numpy as np
from datetime import datetime, timezone
import pandas as pd
import os

# === CONFIG ===
API_KEY = os.getenv("TWELVEDATA_API_KEY")  # or FINNHUB_API_KEY
SYMBOL = "XAU/USD"
INTERVAL = "15min"
SLEEP_TIME = 900  # 15 minutes in seconds
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === FUNCTION: send alert ===
def send_telegram(msg):
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

# === FUNCTION: fetch data ===
def get_data():
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={INTERVAL}&outputsize=100&apikey={API_KEY}"
    r = requests.get(url)
    data = r.json().get("values", [])
    df = pd.DataFrame(data)
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df

# === FUNCTION: indicators ===
def compute_indicators(df):
    df["EMA8"] = df["close"].ewm(span=8).mean()
    df["EMA21"] = df["close"].ewm(span=21).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df["ATR"] = true_range.rolling(14).mean()
    return df

# === FUNCTION: signal generation ===
def generate_signal(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = "HOLD"
    if prev["EMA8"] < prev["EMA21"] and last["EMA8"] > last["EMA21"] and last["RSI"] < 80:
        signal = "BUY"
    elif prev["EMA8"] > prev["EMA21"] and last["EMA8"] < last["EMA21"] and last["RSI"] > 20:
        signal = "SELL"

    atr = last["ATR"]
    price = last["close"]
    stop = price - 2 * atr if signal == "BUY" else price + 2 * atr if signal == "SELL" else None
    target = price + 2.5 * atr if signal == "BUY" else price - 2.5 * atr if signal == "SELL" else None

    return {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "signal": signal,
        "price": round(price, 2),
        "rsi": round(last["RSI"], 2),
        "ema8": round(last["EMA8"], 2),
        "ema21": round(last["EMA21"], 2),
        "atr": round(atr, 2),
        "stop": round(stop, 2) if stop else None,
        "target": round(target, 2) if target else None,
    }

# === MAIN LOOP ===
while True:
    try:
        df = get_data()
        df = compute_indicators(df)
        sig = generate_signal(df)

        text = f"📊 XAUUSD Signal @ {sig['time']}\n" \
               f"Signal: {sig['signal']}\n" \
               f"Price: {sig['price']}\n" \
               f"RSI: {sig['rsi']} | EMA8: {sig['ema8']} | EMA21: {sig['ema21']}\n" \
               f"ATR: {sig['atr']}\n"
        if sig["signal"] in ["BUY", "SELL"]:
            text += f"🎯 Target: {sig['target']} | 🛑 Stop: {sig['stop']}"
            print(text)
            send_telegram(text)
        else:
            print(f"{sig['time']} | HOLD | Price: {sig['price']}")

        time.sleep(SLEEP_TIME)
    except Exception as e:
        print("Error:", e)
        time.sleep(SLEEP_TIME)
