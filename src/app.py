import requests
import asyncio
import json
import os
import hashlib
import hmac
import time
import datetime
from decimal import Decimal

api_key = 'TcwdPNNYGjjgkRW4BRIAnjL7z5TLyJ'
api_secret = 'B5ALo5Mh8mgUREB6oGD4oyX3y185oElaz1LoU6Y3X5ZX0s8TvFZcX4YTVToJ'

# ===== CONFIG =====
TRADE_SYMBOL = "AVAXUSD"   # change to your pair
Initial_Size = 1
Entry_Percantage = 1
Target_Percantage = 2


def generate_signature(method, endpoint, payload):
    timestamp = str(int(time.time()))
    signature_data = method + timestamp + endpoint + payload
    message = bytes(signature_data, 'utf-8')
    secret = bytes(api_secret, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha256)
    return hash.hexdigest(), timestamp

def get_time_stamp():
    d = datetime.datetime.utcnow()
    epoch = datetime.datetime(1970,1,1)
    return str(int((d - epoch).total_seconds()))

async def fetch_profile_data():
    print("Algo Start")

async def place_target_order(order_type, side, order_product, order_size, stop_order_type, stop_price):
    payload = {
        "order_type": order_type,
        "side": side,
        "product_id": int(order_product),
        "stop_order_type": stop_order_type,
        "stop_price": stop_price,
        "reduce_only": False,
        "stop_trigger_method": "mark_price",
        "size": order_size
    }

    method = 'POST'
    endpoint = '/v2/orders'
    payload_str = json.dumps(payload)
    signature, _ = generate_signature(method, endpoint, payload_str)
    timestamp = get_time_stamp()

    headers = {
        'api-key': api_key,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'rest-client',
        'Content-Type': 'application/json'
    }

    response = requests.post(
        'https://cdn.india.deltaex.org/v2/orders',
        json=payload,
        headers=headers
    )

    if response.status_code == 200:
        print("Target order placed successfully.")
    else:
        print("Target order failed:", response.text)

async def place_order(order_type, side, order_product_id, order_size, stop_order_type, target_value):
    payload = {
        "order_type": order_type,
        "side": side,
        "product_id": int(order_product_id),
        "reduce_only": False,
        "size": order_size
    }

    method = 'POST'
    endpoint = '/v2/orders'
    payload_str = json.dumps(payload)
    signature, _ = generate_signature(method, endpoint, payload_str)
    timestamp = get_time_stamp()

    headers = {
        'api-key': api_key,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'rest-client',
        'Content-Type': 'application/json'
    }

    response = requests.post(
        'https://cdn.india.deltaex.org/v2/orders',
        json=payload,
        headers=headers
    )

    if response.status_code == 200:
        print("Main order placed successfully.")
        await place_target_order(
            "market_order",
            "sell",
            order_product_id,
            Initial_Size,
            "take_profit_order",
            target_value
        )
    else:
        print("Main order failed:", response.text)

async def fetch_position_data():
    while True:
        method = 'GET'
        endpoint = '/v2/positions/margined'
        payload = ''
        signature, _ = generate_signature(method, endpoint, payload)
        timestamp = get_time_stamp()

        headers = {
            'api-key': api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'rest-client',
            'Content-Type': 'application/json'
        }

        r = requests.get(
            'https://cdn.india.deltaex.org/v2/positions/margined',
            headers=headers
        )

        position_data = r.json()
        print("Algo Live")

        for result in position_data.get("result", []):

            # ✅ FILTER ONLY ONE SYMBOL
            if result["product_symbol"] != TRADE_SYMBOL:
                continue

            product_id = result["product_id"]
            product_symbol = result["product_symbol"]
            size = float(result["size"])
            entry_price = float(result["entry_price"])
            mark_price = float(result["mark_price"])
            unrealized_pnl = float(result["unrealized_pnl"])

            percentage = (size/Initial_Size) * Entry_Percantage 

            next_entry = entry_price - (entry_price * percentage / 100)

            digit_count = count_digits_after_point(mark_price)
            target = mark_price + (mark_price * Target_Percantage  / 100)
            target = round(target, digit_count)

            print(
                f"{product_symbol} | Size: {size} | "
                f"Entry: {entry_price} | Mark: {mark_price} | "
                f"Next_entry: {next_entry} | "
                f"Target: {target}"
            )

            if mark_price < next_entry:
                print("Ready to buy")
                await place_order(
                    "market_order",
                    "buy",
                    product_id,
                    Initial_Size,
                    0,
                    target
                )

        await asyncio.sleep(30)



def count_digits_after_point(number):
    s = str(number)
    return len(s.split('.')[1]) if '.' in s else 0

async def main():
    while True:
        try:
            await asyncio.gather(
                fetch_profile_data(),
                fetch_position_data()
            )
        except Exception as e:
            print("Error:", e)
        finally:
            await asyncio.sleep(10)

asyncio.run(main())
