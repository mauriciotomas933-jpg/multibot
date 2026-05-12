import os
import time
import requests
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CHECK_INTERVAL   = int(os.getenv("CHECK_INTERVAL_MINUTES", "5")) * 60

TAKE_PROFIT_PCT = 1.5
STOP_LOSS_PCT   = 5.0

# ── Monedas ────────────────────────────────────────────────────────────────────
COINS = {
    "ethereum":    "ETH",
    "ripple":      "XRP",
    "avalanche-2": "AVAX",
    "chainlink":   "LINK",
}

# ── Estado independiente por moneda ───────────────────────────────────────────
state = {
    coin_id: {"in_trade": False, "buy_price": None}
    for coin_id in COINS
}

# ── CoinGecko ──────────────────────────────────────────────────────────────────
def get_data(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": "2", "interval": "hourly"}
    r = requests.get(url, params=params, timeout=20)
    if r.status_code == 429:
        print(f"[RATE LIMIT] {coin_id} - esperando 60s...")
        time.sleep(60)
        r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    prices = r.json()["prices"]
    closes = [p[1] for p in prices]
    return closes, closes[-1]

# ── Indicadores ────────────────────────────────────────────────────────────────
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

# ── Telegram ───────────────────────────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }, timeout=10)

# ── Loop principal ─────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] Multi-bot iniciado.")
    send_telegram(
        "🤖 <b>Multi Crypto Bot activo</b>\n"
        "📊 Monitoreando: ETH | XRP | AVAX | LINK\n"
        f"🎯 Take profit: +{TAKE_PROFIT_PCT}% | 🛑 Stop loss: -{STOP_LOSS_PCT}%\n"
        "⏱ Cada 5 minutos."
    )

    while True:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")

        for coin_id, symbol in COINS.items():
            try:
                closes, price = get_data(coin_id)
                rsi = calculate_rsi(closes)
                coin_state = state[coin_id]

                print(f"[{datetime.now()}] {symbol} ${price:.4f} | RSI: {rsi} | En trade: {coin_state['in_trade']}")

                if not coin_state["in_trade"]:
                    if rsi < 35:
                        coin_state["buy_price"] = price
                        coin_state["in_trade"]  = True
                        send_telegram(
                            f"🟢 <b>COMPRÁ {symbol}</b>\n\n"
                            f"💰 Precio entrada: <b>${price:,.4f}</b>\n"
                            f"📊 RSI: <b>{rsi}</b> (sobrevendido)\n"
                            f"🎯 Take profit: <b>${price * (1 + TAKE_PROFIT_PCT/100):,.4f}</b> (+{TAKE_PROFIT_PCT}%)\n"
                            f"🛑 Stop loss:   <b>${price * (1 - STOP_LOSS_PCT/100):,.4f}</b> (-{STOP_LOSS_PCT}%)\n"
                            f"🕐 {now}"
                        )
                else:
                    buy_price  = coin_state["buy_price"]
                    change_pct = ((price - buy_price) / buy_price) * 100

                    if change_pct >= TAKE_PROFIT_PCT:
                        send_telegram(
                            f"💰 <b>VENDÉ {symbol} — GANANCIA</b>\n\n"
                            f"📈 Entrada: <b>${buy_price:,.4f}</b>\n"
                            f"📈 Salida:  <b>${price:,.4f}</b>\n"
                            f"✅ Ganancia: <b>+{change_pct:.2f}%</b>\n"
                            f"🕐 {now}"
                        )
                        coin_state["in_trade"]  = False
                        coin_state["buy_price"] = None

                    elif change_pct <= -STOP_LOSS_PCT:
                        send_telegram(
                            f"🛑 <b>VENDÉ {symbol} — STOP LOSS</b>\n\n"
                            f"📉 Entrada: <b>${buy_price:,.4f}</b>\n"
                            f"📉 Salida:  <b>${price:,.4f}</b>\n"
                            f"❌ Pérdida: <b>{change_pct:.2f}%</b>\n"
                            f"🕐 {now}"
                        )
                        coin_state["in_trade"]  = False
                        coin_state["buy_price"] = None
                    else:
                        direction = "📈" if change_pct >= 0 else "📉"
                        print(f"  └─ {symbol} en posición: {direction} {change_pct:+.2f}% desde ${buy_price:.4f}")

            except Exception as e:
                # Solo loguea el error, no spamea Telegram
                print(f"[ERROR] {symbol}: {e}")

            # 35 segundos entre cada moneda para respetar rate limit
            time.sleep(35)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
