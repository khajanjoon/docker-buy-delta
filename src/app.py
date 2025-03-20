import hashlib
import requests
import hmac
import json
import time
from datetime import datetime, timedelta

# API Keys and URLs
API_KEY = 'jStY6DkilzfHFpexXd7aWim5us9qlK'
API_SECRET = 'o6yy45lX5x0YX9dZoLFkkiP68p23fkVHTcgnXutgv3ZUNPmxHDBEb9lXggfQ'
API_URL = "https://cdn.india.deltaex.org/v2/tickers/BTCUSD"
ORDER_URL = "https://cdn.india.deltaex.org/v2/orders"
OPEN_ORDERS_URL = "https://api.india.delta.exchange/v2/positions/margined"  # Open orders API


def generate_signature(method, endpoint, payload):
    timestamp = str(int(time.time()))
    signature_data = method + timestamp + endpoint + payload
    message = bytes(signature_data, 'utf-8')
    secret = bytes(API_SECRET, 'utf-8')
    hash = hmac.new(secret, message, hashlib.sha256)
    return hash.hexdigest(), timestamp

def get_expiry():
    """Fetches the nearest BTC expiry date in DDMMYY format"""
    url = "https://cdn.india.deltaex.org/web/options/info"
    headers = {
        'Accept': '*/*',
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.delta.exchange/'
    }

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()

        # Extract expiry dates for BTC call options
        for contract in data.get("result", []):
            if contract["contract_type"] == "call_options":
                for item in contract["data"]:
                    if item["asset"] == "BTC":
                        expiry_dates = item["settlement_time"]
                        if expiry_dates:
                            # Convert the first expiry date to DDMMYY format
                            nearest_expiry = datetime.strptime(expiry_dates[5], "%Y-%m-%dT%H:%M:%SZ")
                            return nearest_expiry.strftime("%d%m%y")

    print("Failed to fetch expiry date or no expiry available.")
    return None  # Return None if data isn't available




def get_tomorrow_expiry():
    """ Returns tomorrow's expiry date in DDMMYY format """
    return (datetime.now() + timedelta(days=1)).strftime("%d%m%y")

def get_ticker(ticker):
    """ Fetches BTC price from API """
    response = requests.get("https://cdn.india.deltaex.org/v2/tickers/"+ticker)
    if response.status_code == 200:
        data = response.json()
        price = float(data["result"]["mark_price"])
        return price
    else:
        print("Failed to fetch BTC price")
        return None

def get_atm_strike():
    """ Fetches BTC price and rounds to the nearest 500 to determine ATM strike """
    response = requests.get(API_URL)
    if response.status_code == 200:
        data = response.json()
        btc_price = float(data["result"]["mark_price"])
        atm_strike = round(btc_price / 1000) * 1000
        return atm_strike
    else:
        print("Failed to fetch BTC price")
        return None


def get_open_orders():
    """ Fetches all open orders from API """
    method = 'GET'
    endpoint = '/v2/positions/margined'
    payload = ""
    signature, timestamp = generate_signature(method, endpoint, payload)

    headers = {
        'api-key': API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'rest-client'
    }

    response = requests.get(OPEN_ORDERS_URL, headers=headers)
    if response.status_code == 200:
        return response.json().get("result", [])
    else:
        print(f"Failed to fetch open orders. Status code: {response.status_code}")
        return []


def order_exists(order_product_id):
    """ Checks if an order for the given product symbol already exists """
    open_orders = get_open_orders()
    for order in open_orders:
        if order["product_symbol"] == order_product_id:
            return True
    return False


def place_order(order_type, side, order_product_id, order_size,target):
    """ Places an order via REST API """
    if order_exists(order_product_id):
        print(f"Order for {order_product_id} already exists. Skipping...")
        return

    payload = {
        "order_type": order_type,
        "side": side,
        "product_symbol": order_product_id,
        "reduce_only": False,
        "size": order_size,
        "post_only":"false",
        "reduce_only":"false",
        "time_in_force":"gtc",
        "bracket_take_profit_price":target,
        "bracket_take_profit_limit_price":target,
        "bracket_stop_trigger_method":"mark_price"
    
        }
  
    
    method = 'POST'
    endpoint = '/v2/orders'
    payload_str = json.dumps(payload)
    signature, timestamp = generate_signature(method, endpoint, payload_str)

    headers = {
        'api-key': API_KEY,
        'timestamp': timestamp,
        'signature': signature,
        'User-Agent': 'rest-client',
        'Content-Type': 'application/json'
    }
    

    response = requests.post(ORDER_URL, json=payload, headers=headers)

    if response.status_code == 200:
        print(f"Order placed successfully: {json.dumps(payload, indent=4)}")
       
       
    else:
        print(f"Failed to place order. Status code: {response.status_code}")





if __name__ == "__main__":
    previous_atm_strikes = set()  # Store last ATM strikes

while True:
    atm_strike = get_atm_strike()
    expiry = get_expiry()

    if atm_strike and expiry:
        strikes = [atm_strike - 1000, atm_strike, atm_strike + 1000]  # Nearest 3 strikes

        for strike in strikes:
            call_option = f"C-BTC-{strike}-{expiry}"
            put_option = f"P-BTC-{strike}-{expiry}"

            if strike not in previous_atm_strikes:
                print(f"Checking orders for {strike}...")

                # Get option prices
                price_call = get_ticker(call_option)
                price_put = get_ticker(put_option)
                
                target_call = price_call * 1.25 if price_call else None
                target_put = price_put * 1.25 if price_put else None

                if target_call:
                    place_order("market_order", "buy", call_option, 1, target_call)
                if target_put:
                    place_order("market_order", "buy", put_option, 1, target_put)

                # Track placed orders
                previous_atm_strikes.add(strike)

            else:
                print(f"Orders for {strike} already exist. Skipping...")

    else:
        print("Failed to get ATM strike or expiry. Retrying...")

    time.sleep(5)
