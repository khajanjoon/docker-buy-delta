import requests
import asyncio
import json
import os
import hashlib
import hmac
import time
import datetime
import hashlib
import hmac
import base64



api_key = 'xFIdqIAYlMojHcLKQxaYcI9F22xWZg'
api_secret = 'uI4Qa6swjkAWmioPsamHr6oAZRs5R07oGU9UapAsqhFlRt1vWoHLWj5GFGhz'

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






BOT_TOKEN = '7003653511:AAGkx1MumC07d4gJh9zb9l7dCqDfyeTHjtY'
# Replace 'YOUR_CHAT_ID' with the chat ID you want to send the message to
CHAT_ID = '311396636'

async def fetch_profile_data():
    
  send_message("response")
        

async def place_target_order(order_type,side,order_product,order_size,stop_order_type,stop_price):
    # Define the payload
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
    # Fetch data from REST API
    # Fetch data from REST API
    method = 'POST'
    endpoint = '/v2/orders'
    signature, timestamp = generate_signature(method, endpoint, payload)
    timestamp = get_time_stamp() 

    headers = {
         'api-key': api_key,
         'timestamp': timestamp,
         'signature': signature,
         'User-Agent': 'rest-client',
         'Content-Type': 'application/json'
           }

    # Send the POST request with the payload
    response = requests.post('https://cdn.india.deltaex.org/v2/orders', json=payload, headers=headers)
    
    # Check if the request was successful
    if response.status_code == 200:
        print("Order placed successfully.")
        message = f"😀New Order:\n" \
          f"Order Type: {payload['order_type']}\n" \
          f"Side: {payload['side']}\n" \
          f"Product ID: {payload['product_id']}\n" \
          f"Stop Order Type: {payload['stop_order_type']}\n" \
          f"Stop Price: {payload['stop_price']}\n" \
          f"Reduce Only: {payload['reduce_only']}\n" \
          f"Stop Trigger Method: {payload['stop_trigger_method']}\n" \
          f"Size: {payload['size']}😀"
        send_message(message)
    else:
        print("Failed to place order. Status code:", response.status_code)

        
async def place_order(order_type,side,order_product_id,order_size,stop_order_type,target_value ):
    # Define the payload
    payload = {
        "order_type": order_type,
        "side": side,
        "product_id": int(order_product_id),
        "reduce_only": False,     
        "size": order_size
    }
    
    # Fetch data from REST API
    method = 'POST'
    endpoint = '/v2/orders'
    signature, timestamp = generate_signature(method, endpoint, payload)
    timestamp = get_time_stamp() 

    headers = {
         'api-key': api_key,
         'timestamp': timestamp,
         'signature': signature,
         'User-Agent': 'rest-client',
         'Content-Type': 'application/json'
           }
    # Send the POST request with the payload
    response = requests.post('https://cdn.india.deltaex.org/v2/orders', json=payload, headers=headers)
    
    # Check if the request was successful
    if response.status_code == 200:
        message = f"😀New Order:\n" \
          f"Order Type: {payload['order_type']}\n" \
          f"Side: {payload['side']}\n" \
          f"Product ID: {payload['product_id']}\n" \
          f"Reduce Only: {'Yes' if payload['reduce_only'] else 'No'}\n" \
          f"Size: {payload['size']}😀"
        send_message(message)
        await place_target_order("market_order","sell",order_product_id,1,"take_profit_order",target_value )
    else:
        send_message(response)

async def fetch_position_data():
    while True:
        # Fetch data from REST API
       
        payload = ''
        method = 'GET'
        timestamp = get_time_stamp() 
        method = 'GET'
        endpoint = '/v2/positions/margined'
        signature, timestamp = generate_signature(method, endpoint, payload)

        headers = {
         'api-key': api_key,
         'timestamp': timestamp,
         'signature': signature,
         'User-Agent': 'rest-client',
         'Content-Type': 'application/json'
  }

        r = requests.get('https://cdn.india.deltaex.org/v2/positions/margined', headers=headers)
        position_data = r.json()  # Extract JSON data using .json() method
        #print("Position Data:", position_data)
        # Extract product_id and realized_pnl from each result
        # Extract data from each dictionary in the 'result' list
        for result in position_data["result"]:
           product_id = result["product_id"]
           product_symbol = result["product_symbol"]
           realized_cashflow = result["realized_cashflow"]
           realized_funding = result["realized_funding"]
           realized_pnl = result["realized_pnl"]
           size = result["size"]
           unrealized_pnl = result["unrealized_pnl"]
           updated_at = result["updated_at"]
           user_id = result["user_id"]
           entry_price = result["entry_price"]
           mark_price = result["mark_price"]
           # Print the extracted data
           

           print()  # Add an empty line for better readability between each dictionary's data

           # Percentage of entry price
           percentage = int(size)*.75 # Assuming 10% for demonstration purposes
           price_value = float(entry_price)-(float(entry_price) * (percentage / 100)) 
           tick_size = 0.05
           target = float(mark_price)*2/100+float(mark_price)
           target_value = round(target / tick_size) * tick_size
           print(price_value)
           
           message = f"Symbol: {product_symbol}\n" \
          f"Size: {size}\n" \
          f"Unrealized PnL: {round((float(unrealized_pnl) ), 2) }\n" \
          f"Entry Price: {round((float(entry_price) ), 2) }\n" \
          f"Next_Entry: {round((float(price_value) ), 2) }\n" \
          f"Mark Price: {round((float(mark_price) ), 2) }\n"
            
           send_message(message)
            # Add an empty line for better readability between each dictionary's data
           if (float(mark_price) < price_value) :
            
            print("ready to buy")
            print()  # Add an empty line for better readability between each dictionary's data
            await place_order("market_order","buy",product_id,1,0,target_value )  
            print()  # Add an empty line for better readability between each dictionary's data
   
        # Wait for 60 seconds before fetching again
        await asyncio.sleep(30)

        
def send_message(message):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    params = {'chat_id': CHAT_ID, 'text': message}

    response = requests.post(url, json=params)
    if response.status_code == 200:
        print('Message sent successfully!')
    else:
        print(f'Failed to send message. Error: {response.status_code} - {response.text}')

async def main():

    # Run profile data fetching coroutine
    profile_task = asyncio.create_task(fetch_profile_data())
    position_task = asyncio.create_task(fetch_position_data())
    # Wait for both tasks to complete
    await asyncio.gather(position_task, profile_task)
    

# Run the main coroutine
asyncio.run(main())
