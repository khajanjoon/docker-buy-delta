import requests
import json
import time
import hmac
import hashlib
import os
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# =========================
# LOAD ENV
# =========================
load_dotenv()
API_KEY = os.getenv("DELTA_API_KEY")
API_SECRET = os.getenv("DELTA_API_SECRET")

BASE_URL = "https://cdn.india.deltaex.org"

# =========================
# MQTT CONFIG
# =========================
MQTT_BROKER = "45.120.136.157"
MQTT_PORT = 1883
MQTT_STATE_TOPIC = "delta/account/khajan"
MQTT_CLIENT_ID = "delta_india_bot_khajan"

HA_PREFIX = "homeassistant"
DEVICE_ID = "delta_trading_bot_khajan"

# =========================
# SYMBOL CONFIG
# =========================
SYMBOL_CONFIG = {
    "ETHUSD": {"qty": 1, "leverage": 200, "contract_value": 0.01},
    "BTCUSD": {"qty": 1, "leverage": 200, "contract_value": 0.001},
    "XRPUSD": {"qty": 25, "leverage": 100, "contract_value": 1},
}

# =========================
# STRATEGY SETTINGS
# =========================
DROP_PERCENT = 0.75
TARGET_PERCENT = 0.75
MAX_BUYS = 8
MAX_MARGIN_USAGE = 0.60
MAX_EQUITY_RISK = 0.50
SLEEP_TIME = 10

# =========================
# SIGNATURE
# =========================
def generate_signature(method, endpoint, payload):
    timestamp = str(int(time.time()))
    message = method + timestamp + endpoint + payload
    signature = hmac.new(
        API_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature, timestamp

# =========================
# TRADING BOT
# =========================
class TradingBot:
    def __init__(self):
        self.mqtt = mqtt.Client(
            client_id=MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )
        self.mqtt.connect(MQTT_BROKER, MQTT_PORT, 60)
        self.mqtt.loop_start()

        self.publish_ha_discovery()
        self.publish_position_discovery()

        print("\n🚀 Delta USD Trading Bot Started\n")

    # =========================
    # HOME ASSISTANT – ACCOUNT
    # =========================
    def publish_ha_discovery(self):
        sensors = {
            "wallet_usd": ("Wallet USD", "{{ value_json.wallet_usd }}"),
            "equity_usd": ("Equity USD", "{{ value_json.equity_usd }}"),
            "blocked_margin_usd": ("Blocked Margin USD", "{{ value_json.blocked_margin_usd }}"),
        }

        for key, (name, template) in sensors.items():
            payload = {
                "name": name,
                "state_topic": MQTT_STATE_TOPIC,
                "value_template": template,
                "unit_of_measurement": "USD",
                "device_class": "monetary",
                "state_class": "measurement",
                "unique_id": f"{DEVICE_ID}_{key}",
                "device": {
                    "identifiers": [DEVICE_ID],
                    "name": "Delta Trading Bot",
                    "manufacturer": "Custom",
                    "model": "Algo Bot"
                }
            }
            self.mqtt.publish(
                f"{HA_PREFIX}/sensor/{DEVICE_ID}_{key}/config",
                json.dumps(payload),
                retain=True
            )

    # =========================
    # HOME ASSISTANT – POSITIONS
    # =========================
    def publish_position_discovery(self):
        for symbol in SYMBOL_CONFIG:
            base = symbol.lower()

            sensors = {
                f"{base}_size": ("Position Size", "{{ value_json.%s_size }}" % base, None),
                f"{base}_entry": ("Entry Price", "{{ value_json.%s_entry }}" % base, "USD"),
                f"{base}_mark": ("Mark Price", "{{ value_json.%s_mark }}" % base, "USD"),
                f"{base}_pnl": ("Unrealized PnL", "{{ value_json.%s_pnl }}" % base, "USD"),
            }

            for key, (name, template, unit) in sensors.items():
                payload = {
                    "name": f"{symbol} {name}",
                    "state_topic": MQTT_STATE_TOPIC,
                    "value_template": template,
                    "unique_id": f"{DEVICE_ID}_{key}",
                    "device": {
                        "identifiers": [DEVICE_ID],
                        "name": "Delta Trading Bot",
                        "manufacturer": "Custom",
                        "model": "Algo Bot"
                    }
                }
                if unit:
                    payload["unit_of_measurement"] = unit
                    payload["device_class"] = "monetary"
                    payload["state_class"] = "measurement"

                self.mqtt.publish(
                    f"{HA_PREFIX}/sensor/{DEVICE_ID}_{key}/config",
                    json.dumps(payload),
                    retain=True
                )

    # =========================
    # BALANCE (USD ONLY)
    # =========================
    def get_user_balance(self):
        sig, ts = generate_signature("GET", "/v2/wallet/balances", "")
        r = requests.get(
            BASE_URL + "/v2/wallet/balances",
            headers={"api-key": API_KEY, "timestamp": ts, "signature": sig}
        )
        r.raise_for_status()

        for asset in r.json()["result"]:
            if asset["asset_symbol"] == "USD":
                return {
                    "wallet_usd": float(asset["available_balance"]),
                    "equity_usd": float(asset["balance"]),
                    "blocked_margin_usd": float(asset["blocked_margin"])
                }

        return {"wallet_usd": 0, "equity_usd": 0, "blocked_margin_usd": 0}

    # =========================
    # POSITIONS
    # =========================
    def get_positions(self):
        sig, ts = generate_signature("GET", "/v2/positions/margined", "")
        r = requests.get(
            BASE_URL + "/v2/positions/margined",
            headers={"api-key": API_KEY, "timestamp": ts, "signature": sig}
        )
        r.raise_for_status()
        return r.json()["result"]

    # =========================
    # PRODUCT ID
    # =========================
    def get_product_id(self, symbol):
        r = requests.get(BASE_URL + "/v2/products")
        r.raise_for_status()
        for p in r.json()["result"]:
            if p["symbol"] == symbol:
                return p["id"]
        return None

    # =========================
    # MARK PRICE
    # =========================
    def get_mark_price(self, symbol):
        r = requests.get(f"{BASE_URL}/v2/tickers/{symbol}")
        r.raise_for_status()
        return float(r.json()["result"]["mark_price"])

    # =========================
    # BUY + TAKE PROFIT
    # =========================
    def place_buy_with_tp(self, product_id, qty, target_price):
        payload = {
            "order_type": "market_order",
            "side": "buy",
            "product_id": int(product_id),
            "reduce_only": False,
            "size": qty,
        }

        sig, ts = generate_signature("POST", "/v2/orders", json.dumps(payload))
        r = requests.post(
            BASE_URL + "/v2/orders",
            json=payload,
            headers={"api-key": API_KEY, "timestamp": ts, "signature": sig}
        )
        print("🛒 BUY:", r.json())

        if r.status_code == 200:
            self.place_take_profit(product_id, qty, target_price)

    def place_take_profit(self, product_id, qty, price):
        payload = {
            "order_type": "market_order",
            "side": "sell",
            "product_id": int(product_id),
            "stop_order_type": "take_profit_order",
            "stop_price": price,
            "stop_trigger_method": "mark_price",
            "reduce_only": True,
            "size": qty,
        }

        sig, ts = generate_signature("POST", "/v2/orders", json.dumps(payload))
        r = requests.post(
            BASE_URL + "/v2/orders",
            json=payload,
            headers={"api-key": API_KEY, "timestamp": ts, "signature": sig}
        )
        print("🎯 TP:", r.json())

    # =========================
    # MQTT STATE
    # =========================
    def publish_state(self, bal, pos_map):
        payload = {
            "wallet_usd": bal["wallet_usd"],
            "equity_usd": bal["equity_usd"],
            "blocked_margin_usd": bal["blocked_margin_usd"],
            "timestamp": int(time.time())
        }

        for symbol in SYMBOL_CONFIG:
            key = symbol.lower()
            pos = pos_map.get(symbol)

            payload[f"{key}_size"] = float(pos["size"]) if pos else 0
            payload[f"{key}_entry"] = float(pos["entry_price"]) if pos else 0
            payload[f"{key}_mark"] = float(pos["mark_price"]) if pos else 0
            payload[f"{key}_pnl"] = float(pos["unrealized_pnl"]) if pos else 0

        self.mqtt.publish(MQTT_STATE_TOPIC, json.dumps(payload), qos=1)

    # =========================
    # MAIN LOOP
    # =========================
    def run(self):
        while True:
            try:
                bal = self.get_user_balance()
                positions = self.get_positions()
                pos_map = {p["product_symbol"]: p for p in positions}

                self.publish_state(bal, pos_map)

                for symbol, cfg in SYMBOL_CONFIG.items():
                    qty = cfg["qty"]
                    leverage = cfg["leverage"]
                    cv = cfg["contract_value"]

                    mark = self.get_mark_price(symbol)
                    notional = qty * mark * cv
                    margin_needed = notional / leverage

                    pos = pos_map.get(symbol)

                    if not pos:
                        if margin_needed <= bal["wallet_usd"] * MAX_MARGIN_USAGE:
                            pid = self.get_product_id(symbol)
                            tp = mark * (1 + TARGET_PERCENT / 100)
                            self.place_buy_with_tp(pid, qty, round(tp, 4))
                        continue

                    size = abs(float(pos["size"]))
                    entry = float(pos["entry_price"])
                    margin_used = float(pos["margin"])

                    if margin_used > bal["equity_usd"] * MAX_EQUITY_RISK:
                        continue

                    buy_count = int(size / qty)
                    if buy_count >= MAX_BUYS:
                        continue

                    next_price = entry * (1 - (DROP_PERCENT / 100) * buy_count)

                    if mark < next_price:
                        tp = mark * (1 + TARGET_PERCENT / 100)
                        self.place_buy_with_tp(pos["product_id"], qty, round(tp, 4))

                    print(
                        f"{symbol} | Size:{size} | Entry:{entry} | "
                        f"Mark:{mark} | Next:{next_price}"
                    )

                time.sleep(SLEEP_TIME)

            except Exception as e:
                print("❌ ERROR:", e)
                time.sleep(5)

# =========================
# START
# =========================
if __name__ == "__main__":
    TradingBot().run()
