import requests
import asyncio
import json
import os

Authorization = os.environ['token','7ygBbjKWiBdB7XwblKVKnZfMFj1dnz458qNiizq10chfKU0Mhf1']
#'7ygBbjKWiBdB7XwblKVKnZfMFj1dnz458qNiizq10chfKU0Mhf1'

async def fetch_profile_data():
    while True:

        requests.post("https://ntfy.sh/buy_algo",
        data="Buy Algo Live😀".encode(encoding='utf-8'))
        await asyncio.sleep(300)

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
    print(payload)
    # Fetch data from REST API
    

    headers = {
      'Authorization': Authorization, 
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
      'Content-Type': 'application/json'
    }

    # Send the POST request with the payload
    response = requests.post('https://cdn.india.deltaex.org/v2/orders', json=payload, headers=headers)
    
    # Check if the request was successful
    if response.status_code == 200:
        print("Order placed successfully.")
        requests.post("https://ntfy.sh/buy_trade",
        data="order successful 😀".encode(encoding='utf-8'))
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
    

    headers = {
      'Authorization': Authorization, 
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
      'Content-Type': 'application/json'
    }

    # Send the POST request with the payload
    response = requests.post('https://cdn.india.deltaex.org/v2/orders', json=payload, headers=headers)
    
    # Check if the request was successful
    if response.status_code == 200:
        print("Order placed successfully.")
        requests.post("https://ntfy.sh/buy_trade",
        data="order successful 😀".encode(encoding='utf-8'))
        await place_target_order("market_order","sell",order_product_id,1,"take_profit_order",target_value )
    else:
        print("Failed to place order. Status code:", response.status_code)
      

async def fetch_position_data():
    while True:
        # Fetch data from REST API
       

        headers = {
          'Authorization': Authorization, 
          'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
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
           print("Product ID:", product_id, 
            "Product Symbol:", product_symbol, 
            "Realized Cashflow:", realized_cashflow, 
            "Realized Funding:", realized_funding, 
            "Realized PnL:", realized_pnl, 
            "Size:", size, 
            "Unrealized PnL:", unrealized_pnl, 
            "Updated At:", updated_at, 
            "User ID:", user_id, 
            "entry_price:", entry_price, 
            "mark_price:", mark_price)

           print()  # Add an empty line for better readability between each dictionary's data

           # Percentage of entry price
           percentage = int(size)*.75 # Assuming 10% for demonstration purposes
           price_value = float(entry_price)-(float(entry_price) * (percentage / 100)) 
           tick_size = 0.05
           target = float(entry_price)*2/100+float(entry_price)
           target_value = round(target / tick_size) * tick_size
           print(price_value)
           print(target_value)  # Add an empty line for better readability between each dictionary's data
           if (float(mark_price) < price_value) :

            print("ready to buy")
            print()  # Add an empty line for better readability between each dictionary's data
            await place_order("market_order","buy",product_id,1,0,target_value )  
            print()  # Add an empty line for better readability between each dictionary's data
   
        # Wait for 60 seconds before fetching again
        await asyncio.sleep(30)

async def main():

    # Run profile data fetching coroutine
    profile_task = asyncio.create_task(fetch_profile_data())
    position_task = asyncio.create_task(fetch_position_data())
    # Wait for both tasks to complete
    await asyncio.gather(position_task, profile_task)
    

# Run the main coroutine
asyncio.run(main())
