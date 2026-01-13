import os
import time
import json
from typing import Dict, Optional
from delta_rest_client import DeltaRestClient, OrderType, TimeInForce
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import threading

# Load environment variables
load_dotenv()

class MultiSymbolDeltaTrader:
    def __init__(self, api_key: str = None, api_secret: str = None, testnet: bool = False):
        """Initialize the Multi-Symbol Delta Trader"""
        if api_key is None:
            api_key = os.environ.get('DELTA_API_KEY')
        if api_secret is None:
            api_secret = os.environ.get('DELTA_API_SECRET')
        
        if not api_key or not api_secret:
            raise ValueError("API key and secret must be provided")
        
        base_url = 'https://testnet-api.delta.exchange' if testnet else 'https://api.india.delta.exchange'
        
        self.delta_client = DeltaRestClient(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            raise_for_status=False
        )
        
        # Multi-symbol configuration
        self.config = {
            "BTCUSD": {
                "product_id": 27,
                "display_name": "Bitcoin",
                "base_qty": 1,
                "min_lot_size": 0.001,
                "target_percent": 1.0,
                "stop_loss_percent": 2.0,
                "averaging_trigger": 2.0,
                "max_average_orders": 8,
                "leverage": 200,
                "enabled": True
            },
            "ETHUSD": {
                "product_id": 3136,
                "display_name": "Ethereum",
                "base_qty": 1,
                "min_lot_size": 0.01,
                "target_percent": 1.0,
                "stop_loss_percent": 2.5,
                "averaging_trigger": 2.0,
                "max_average_orders": 8,
                "leverage": 200,
                "enabled": True
            },
            "XRPUSD": {
                "product_id":  14969,
                "display_name": "Ripple",
                "base_qty": 10,
                "min_lot_size": 1,
                "target_percent": 1.0,
                "stop_loss_percent": 3.0,
                "averaging_trigger": 2.0,
                "max_average_orders": 8,
                "leverage": 100,
                "enabled": True
            },
            "LTCUSD": {
                "product_id": 15040,
                "display_name": "Litecoin",
                "base_qty": 2,
                "min_lot_size": 0.1,
                "target_percent": 1.0,
                "stop_loss_percent": 2.5,
                "averaging_trigger": 2.0,
                "max_average_orders": 8,
                "leverage": 100,
                "enabled": True
            },
            "DOGEUSD": {
                "product_id": 14745,
                "display_name": "Dogecoin",
                "base_qty": 2,
                "min_lot_size": 100,
                "target_percent": 1.0,
                "stop_loss_percent": 3.0,
                "averaging_trigger": 2.0,
                "max_average_orders": 8,
                "leverage": 100,
                "enabled": True
            }
        }
        
        # Track averaging counts per symbol
        self.averaging_counts = {}
        
        # Trading statistics
        self.total_trades = 0
        self.successful_trades = 0
        
        # Home Assistant MQTT Configuration
        self.mqtt_enabled = os.environ.get('MQTT_ENABLED', 'false').lower() == 'true'
        self.mqtt_client = None
        self.ha_connected = False
        
        # MQTT Topics
        self.mqtt_base_topic = "delta_trader"
        self.sensor_topic = f"{self.mqtt_base_topic}/sensor"
        self.switch_topic = f"{self.mqtt_base_topic}/switch"
        self.command_topic = f"{self.mqtt_base_topic}/command"
        
        # Bot state
        self.bot_running = True
        self.last_update_time = time.time()
        
        # Initialize MQTT if enabled
        if self.mqtt_enabled:
            self.init_mqtt()
    
    def init_mqtt(self):
        """Initialize MQTT connection for Home Assistant"""
        try:
            mqtt_host = os.environ.get('MQTT_HOST', 'homeassistant.local')
            mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
            mqtt_user = os.environ.get('MQTT_USERNAME', '')
            mqtt_pass = os.environ.get('MQTT_PASSWORD', '')
            
            self.mqtt_client = mqtt.Client(client_id="delta_trader")
            
            if mqtt_user and mqtt_pass:
                self.mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
            
            # Set callbacks
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            self.mqtt_client.on_message = self.on_mqtt_message
            
            # Connect
            print(f"🔗 Connecting to MQTT broker at {mqtt_host}:{mqtt_port}...")
            self.mqtt_client.connect(mqtt_host, mqtt_port, 60)
            self.mqtt_client.loop_start()
            
            # Subscribe to command topic
            self.mqtt_client.subscribe(f"{self.command_topic}/#")
            
            # Send Home Assistant auto-discovery messages
            threading.Timer(2, self.send_ha_discovery).start()
            
        except Exception as e:
            print(f"❌ Error initializing MQTT: {e}")
    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            self.ha_connected = True
            print("✅ Connected to Home Assistant via MQTT")
            self.send_ha_discovery()
        else:
            print(f"❌ MQTT connection failed with code: {rc}")
    
    def on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        self.ha_connected = False
        print("❌ Disconnected from Home Assistant MQTT")
    
    def on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            
            print(f"📨 Received MQTT message: {topic} = {payload}")
            
            # Parse command
            if topic == f"{self.command_topic}/bot_power":
                if payload.lower() == "on":
                    self.bot_running = True
                    self.publish_state("bot_power", "ON")
                    print("✅ Bot enabled via Home Assistant")
                elif payload.lower() == "off":
                    self.bot_running = False
                    self.publish_state("bot_power", "OFF")
                    print("⏸️ Bot paused via Home Assistant")
            
            elif topic == f"{self.command_topic}/close_all":
                if payload.lower() == "on":
                    self.close_all_positions()
                    self.publish_state("close_all", "OFF")
            
            elif topic.startswith(f"{self.command_topic}/symbol_"):
                symbol = topic.split('/')[-1].replace('symbol_', '')
                if symbol in self.config:
                    if payload.lower() == "on":
                        self.config[symbol]["enabled"] = True
                        self.publish_state(f"symbol_{symbol}", "ON")
                        print(f"✅ {symbol} trading enabled via Home Assistant")
                    elif payload.lower() == "off":
                        self.config[symbol]["enabled"] = False
                        self.publish_state(f"symbol_{symbol}", "OFF")
                        print(f"⏸️ {symbol} trading disabled via Home Assistant")
            
            elif topic == f"{self.command_topic}/refresh":
                self.update_ha_sensors()
            
        except Exception as e:
            print(f"❌ Error handling MQTT message: {e}")
    
    def send_ha_discovery(self):
        """Send Home Assistant MQTT discovery messages"""
        if not self.ha_connected:
            return
        
        try:
            device_info = {
                "identifiers": ["delta_trader_bot"],
                "name": "Delta Trader Bot",
                "manufacturer": "Delta Exchange",
                "model": "Multi-Symbol Trader",
                "sw_version": "1.0"
            }
            
            # Bot Power Switch
            power_config = {
                "name": "Delta Trader Bot Power",
                "unique_id": "delta_trader_bot_power",
                "command_topic": f"{self.command_topic}/bot_power",
                "state_topic": f"{self.sensor_topic}/bot_power/state",
                "payload_on": "ON",
                "payload_off": "OFF",
                "device": device_info
            }
            self.mqtt_client.publish(
                f"homeassistant/switch/delta_trader/bot_power/config",
                json.dumps(power_config),
                retain=True
            )
            
            # Close All Positions Button
            close_config = {
                "name": "Close All Positions",
                "unique_id": "delta_trader_close_all",
                "command_topic": f"{self.command_topic}/close_all",
                "payload_press": "ON",
                "device": device_info
            }
            self.mqtt_client.publish(
                f"homeassistant/button/delta_trader/close_all/config",
                json.dumps(close_config),
                retain=True
            )
            
            # Refresh Data Button
            refresh_config = {
                "name": "Refresh Data",
                "unique_id": "delta_trader_refresh",
                "command_topic": f"{self.command_topic}/refresh",
                "payload_press": "ON",
                "device": device_info
            }
            self.mqtt_client.publish(
                f"homeassistant/button/delta_trader/refresh/config",
                json.dumps(refresh_config),
                retain=True
            )
            
            # Symbol switches
            for symbol, config in self.config.items():
                switch_config = {
                    "name": f"{config['display_name']} Trading",
                    "unique_id": f"delta_trader_symbol_{symbol}",
                    "command_topic": f"{self.command_topic}/symbol_{symbol}",
                    "state_topic": f"{self.sensor_topic}/symbol_{symbol}/state",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device": device_info
                }
                self.mqtt_client.publish(
                    f"homeassistant/switch/delta_trader/symbol_{symbol}/config",
                    json.dumps(switch_config),
                    retain=True
                )
            
            # Initial states
            self.publish_state("bot_power", "ON")
            for symbol in self.config:
                self.publish_state(f"symbol_{symbol}", "ON" if self.config[symbol]["enabled"] else "OFF")
            
            print("📡 Home Assistant discovery messages sent")
            
        except Exception as e:
            print(f"❌ Error sending HA discovery: {e}")
    
    def publish_state(self, entity: str, state: str):
        """Publish state to Home Assistant"""
        if self.ha_connected and self.mqtt_client:
            try:
                self.mqtt_client.publish(
                    f"{self.sensor_topic}/{entity}/state",
                    state,
                    retain=True
                )
            except Exception as e:
                print(f"❌ Error publishing state: {e}")
    
    def update_ha_sensors(self):
        """Update all Home Assistant sensors with current data"""
        if not self.ha_connected:
            return
        
        try:
            # Get account balance
            balance_info = self.get_account_balance()
            
            # Publish balance sensors
            self.publish_sensor("total_balance_usd", balance_info.get('total_balance_usd', 0), "USD")
            self.publish_sensor("total_balance_inr", balance_info.get('total_balance_inr', 0), "INR")
            self.publish_sensor("available_balance", balance_info.get('available_balance', 0), "USD")
            
            # Publish statistics
            self.publish_sensor("total_trades", self.total_trades, "trades")
            self.publish_sensor("successful_trades", self.successful_trades, "trades")
            
            success_rate = 0
            if self.total_trades > 0:
                success_rate = (self.successful_trades / self.total_trades) * 100
            self.publish_sensor("success_rate", round(success_rate, 1), "%")
            
            # Publish position data for each symbol
            for symbol in self.config:
                position = self.get_position(symbol)
                if position:
                    current_price = self.get_price(symbol)
                    if current_price:
                        # Calculate P&L
                        if position['side'] == 'long':
                            pnl = (current_price - position['entry_price']) * position['size']
                        else:
                            pnl = (position['entry_price'] - current_price) * abs(position['size'])
                        
                        pnl_percent = (pnl / (abs(position['size']) * position['entry_price'])) * 100
                        
                        # Publish position data
                        self.publish_sensor(f"{symbol}_size", position['size'], symbol)
                        self.publish_sensor(f"{symbol}_entry_price", round(position['entry_price'], 2), "USD")
                        self.publish_sensor(f"{symbol}_current_price", round(current_price, 2), "USD")
                        self.publish_sensor(f"{symbol}_pnl", round(pnl, 2), "USD")
                        self.publish_sensor(f"{symbol}_pnl_percent", round(pnl_percent, 2), "%")
                        self.publish_sensor(f"{symbol}_side", position['side'], "")
                        self.publish_sensor(f"{symbol}_averaging_count", self.averaging_counts.get(symbol, 0), "times")
                else:
                    # Clear position sensors
                    self.clear_sensor(f"{symbol}_size")
                    self.clear_sensor(f"{symbol}_entry_price")
                    self.clear_sensor(f"{symbol}_current_price")
                    self.clear_sensor(f"{symbol}_pnl")
                    self.clear_sensor(f"{symbol}_pnl_percent")
                    self.clear_sensor(f"{symbol}_side")
                    self.clear_sensor(f"{symbol}_averaging_count")
            
            print("📊 Updated Home Assistant sensors")
            
        except Exception as e:
            print(f"❌ Error updating HA sensors: {e}")
    
    def publish_sensor(self, name: str, value, unit: str = ""):
        """Publish sensor data to Home Assistant"""
        if self.ha_connected and self.mqtt_client:
            try:
                sensor_config = {
                    "name": name.replace('_', ' ').title(),
                    "unique_id": f"delta_trader_{name}",
                    "state_topic": f"{self.sensor_topic}/{name}/state",
                    "unit_of_measurement": unit,
                    "device_class": "monetary" if "balance" in name or "price" in name or "pnl" in name else None,
                    "state_class": "measurement",
                    "device": {
                        "identifiers": ["delta_trader_bot"],
                        "name": "Delta Trader Bot"
                    }
                }
                
                # Publish config
                self.mqtt_client.publish(
                    f"homeassistant/sensor/delta_trader/{name}/config",
                    json.dumps(sensor_config),
                    retain=True
                )
                
                # Publish state
                self.mqtt_client.publish(
                    f"{self.sensor_topic}/{name}/state",
                    str(value),
                    retain=True
                )
                
            except Exception as e:
                print(f"❌ Error publishing sensor {name}: {e}")
    
    def clear_sensor(self, name: str):
        """Clear sensor data in Home Assistant"""
        if self.ha_connected and self.mqtt_client:
            try:
                self.mqtt_client.publish(
                    f"{self.sensor_topic}/{name}/state",
                    "",
                    retain=True
                )
            except Exception as e:
                print(f"❌ Error clearing sensor {name}: {e}")
    
    def get_balance(self, asset_symbol: str = "USD"):
        """Get balance for a specific asset"""
        try:
            product = self.delta_client.get_product(27)
            balance = self.delta_client.get_balances(
                product['settling_asset']['id']
            )

            print(f"Fetching balance for asset: {balance}")

            if balance.get('asset_symbol') == asset_symbol:
                available = float(balance.get('available_balance', 0))
                print(available)
                return available

            return 0.0

        except Exception as e:
            print(f"Error getting balance for {asset_symbol}: {e}")
            return 0.0

    
    def get_margin_info(self):
        """Get margin information"""
        try:
            # Try to get account summary which includes margin info
            product = self.delta_client.get_product(27)
            account = self.delta_client.get_balances(product['settling_asset']['id'])
            
            if account and isinstance(account, dict):
                return {
                    'overall': {
                        'total_equity': float(account.get('balance_inr', 0)),
                        'used_margin': float(account.get('blocked_margin', 0))*85,  # Approximate conversion to inr
                        'available_balance': float(account.get('available_balance_inr', 0))
                    }
                }
            return None
        except Exception as e:
            print(f"Error getting margin info: {e}")
            return None
    
    def get_account_balance(self) -> Dict:
        """Get account balance information"""
        try:
            # Get all wallet balances
            product = self.delta_client.get_product(27)
            wallet_balances = self.delta_client.get_balances(product['settling_asset']['id'])
            
            print("\n" + "="*60)
            print("💰 ACCOUNT BALANCE")
            print("="*60)
            
            total_balance_usd = 0
            total_balance_inr = 0
            available_balance_usd = 0
            
            if isinstance(wallet_balances, list):
                for asset in wallet_balances:
                    symbol = asset.get('asset_symbol', 'Unknown')
                    available = float(asset.get('available_balance', 0))
                    total = float(asset.get('balance', 0))
                    blocked_margin = float(asset.get('blocked_margin', 0))
                    position_margin = float(asset.get('position_margin', 0))
                    
                    available_inr = float(asset.get('available_balance_inr', 0))
                    total_inr = float(asset.get('balance_inr', 0))
                    
                    if symbol == 'USD':
                        total_balance_usd = total
                        total_balance_inr = total_inr
                        available_balance_usd = available
                    
                    if total > 0 or blocked_margin > 0:
                        print(f"\n{symbol}:")
                        print(f"  Available: {available:.6f} ({available_inr:.2f} INR)")
                        print(f"  Total: {total:.6f} ({total_inr:.2f} INR)")
                        if blocked_margin > 0:
                            print(f"  Blocked Margin: {blocked_margin:.6f}")
                        if position_margin > 0:
                            print(f"  Position Margin: {position_margin:.6f}")
                        
            elif isinstance(wallet_balances, dict):
                # Handle single balance response
                symbol = wallet_balances.get('asset_symbol', 'Unknown')
                available = float(wallet_balances.get('available_balance', 0))
                total = float(wallet_balances.get('balance', 0))
                available_inr = float(wallet_balances.get('available_balance_inr', 0))
                total_inr = float(wallet_balances.get('balance_inr', 0))
                
                print(f"\n{symbol}:")
                print(f"  Available: {available:.6f} ({available_inr:.2f} INR)")
                print(f"  Total: {total:.6f} ({total_inr:.2f} INR)")
                
                if symbol == 'USD':
                    total_balance_usd = total
                    total_balance_inr = total_inr
                    available_balance_usd = available
            
            # Get margin info
            margin_info = self.get_margin_info()
            
            print("\n📊 Summary:")
            print(f"  💰 Total Balance: ${total_balance_usd:.2f} ({total_balance_inr:.2f} INR)")
            print(f"  💵 Available Balance: ${available_balance_usd:.2f}")
            
            if margin_info and 'overall' in margin_info:
                overall = margin_info['overall']
                print(f"  🏦 Total Equity: ${overall.get('total_equity', 0):.2f}")
                print(f"  🔒 Used Margin: ${overall.get('used_margin', 0):.2f}")
                print(f"  📈 Available Margin: ${overall.get('available_balance', 0):.2f}")
            
            print("="*60)
            
            return {
                'total_balance_usd': total_balance_usd,
                'total_balance_inr': total_balance_inr,
                'available_balance': available_balance_usd
            }
        except Exception as e:
            print(f"Error getting account balance: {e}")
            return {'total_balance_usd': 0, 'total_balance_inr': 0, 'available_balance': 0}
    
    def get_available_balance_for_trading(self, symbol: str):
        """Get available balance for trading a specific symbol"""
        try:
            # Get the product to know what asset is needed
            if symbol not in self.config:
                return 0
                
           
            product = self.delta_client.get_product(27)
            
            if not product:
                return 0
           
            # Get the settling asset for this product
            settling_asset = product.get('settling_asset', {})
            asset_symbol = settling_asset.get('symbol', 'USD')
            print(f"{symbol}: Settling asset is {asset_symbol}")
            # Get balance for this asset
            return self.get_balance(asset_symbol)
        except Exception as e:
            print(f"Error getting trading balance for {symbol}: {e}")
            return self.get_balance("USD")  # Fallback to USD
    
    def get_position(self, symbol: str):
        """Get current position for a symbol - Fresh fetch every time"""
        try:
            if symbol not in self.config:
                return None
            
            product_id = self.config[symbol]["product_id"]
            
            # Always fetch fresh position data
            position = None
            
            # Method 1: Try to get specific product position
            try:
                position = self.delta_client.get_position(product_id)
                if position and float(position.get('size', 0)) == 0:
                    position = None
            except:
                pass
            
            # Method 2: Get all positions and filter
            if not position:
                try:
                    positions = self.delta_client.get_positions()
                    if isinstance(positions, list):
                        for pos in positions:
                            if str(pos.get('product_id')) == str(product_id):
                                if float(pos.get('size', 0)) != 0:
                                    position = pos
                                    break
                except:
                    pass
            
            if position:
                size = float(position.get('size', 0))
                entry_price = float(position.get('entry_price', 0))
                mark_price = float(position.get('mark_price', 0))
                unrealized_pnl = float(position.get('unrealized_pnl', 0))
                
                return {
                    'size': size,
                    'entry_price': entry_price,
                    'side': 'long' if size > 0 else 'short',
                    'mark_price': mark_price,
                    'unrealized_pnl': unrealized_pnl,
                    'product_id': product_id,
                    'symbol': symbol
                }
            
            # If no position found, clear averaging count
            if symbol in self.averaging_counts:
                del self.averaging_counts[symbol]
            
            return None
        except Exception as e:
            print(f"Error getting position for {symbol}: {e}")
            return None
    
    def get_price(self, symbol: str):
        """Get current price"""
        try:
            ticker = self.delta_client.get_ticker(symbol)
            if ticker:
                if 'close' in ticker:
                    return float(ticker['close'])
                elif 'spot_price' in ticker:
                    return float(ticker['spot_price'])
                elif 'mark_price' in ticker:
                    return float(ticker['mark_price'])
                elif 'last' in ticker:
                    return float(ticker['last'])
            
            # Fallback to position mark price
            position = self.get_position(symbol)
            if position and position.get('mark_price', 0) > 0:
                return position.get('mark_price')
            
            return None
        except Exception as e:
            print(f"Error getting price for {symbol}: {e}")
            return None
    
    def get_all_open_orders(self):
        """Get all open orders for all symbols"""
        try:
            orders = self.delta_client.get_live_orders(
                query={'states': 'open'}
            )
            
            if isinstance(orders, list):
                return orders
            return []
        except Exception as e:
            print(f"Error getting open orders: {e}")
            return []
    
    def get_target_orders(self, symbol: str):
        """Get open target orders for a specific symbol"""
        try:
            if symbol not in self.config:
                return []
            
            position = self.get_position(symbol)
            if not position:
                return []
            
            product_id = self.config[symbol]["product_id"]
            
            # Get all open orders
            all_orders = self.get_all_open_orders()
            if not all_orders:
                return []
            
            target_orders = []
            position_side = position.get('side', 'long')
            
            for order in all_orders:
                if str(order.get('product_id')) == str(product_id):
                    order_side = order.get('side', '')
                    # For long positions, target orders are sell orders
                    # For short positions, target orders are buy orders
                    if (position_side == 'long' and order_side == 'sell') or \
                       (position_side == 'short' and order_side == 'buy'):
                        target_orders.append(order)
            
            return target_orders
        except Exception as e:
            print(f"Error getting target orders for {symbol}: {e}")
            return []
    
    def get_lowest_target_price(self, symbol: str):
        """Get lowest target price from all open targets"""
        try:
            target_orders = self.get_target_orders(symbol)
            if not target_orders:
                return None
            
            position = self.get_position(symbol)
            if not position:
                return None
            
            position_side = position.get('side', 'long')
            
            if position_side == 'long':
                # For long positions, find lowest sell price
                lowest_price = min(float(order.get('limit_price', 0)) for order in target_orders)
                return lowest_price
            else:
                # For short positions, find highest buy price
                highest_price = max(float(order.get('limit_price', 0)) for order in target_orders)
                return highest_price
        except Exception as e:
            print(f"Error getting lowest target price for {symbol}: {e}")
            return None
    
    def cancel_all_orders_for_symbol(self, symbol: str):
        """Cancel all open orders for a symbol"""
        try:
            if symbol not in self.config:
                return False
            
            product_id = self.config[symbol]["product_id"]
            
            # Get all open orders for this product
            orders = self.delta_client.get_live_orders(
                query={'product_ids': product_id, 'states': 'open'}
            )
            
            if isinstance(orders, list):
                for order in orders:
                    try:
                        self.delta_client.cancel_order(order['id'])
                        print(f"Cancelled order {order['id']} for {symbol}")
                    except Exception as e:
                        print(f"Error cancelling order {order['id']}: {e}")
            
            return True
        except Exception as e:
            print(f"Error cancelling orders for {symbol}: {e}")
            return False
    
    def place_market_order(self, symbol: str, side: str, qty: float):
        """Place market order"""
        try:
            if symbol not in self.config:
                print(f"Symbol {symbol} not in config")
                return None
            
            product_id = self.config[symbol]["product_id"]
            
            order = self.delta_client.place_order(
                product_id=product_id,
                size=qty,
                side=side,
                order_type=OrderType.MARKET
            )
            
            self.total_trades += 1
            print(f"✅ Market {side} order placed: {qty} {symbol}")
            return order
        except Exception as e:
            print(f"Error placing market order for {symbol}: {e}")
            return None
    
    def place_limit_order(self, symbol: str, side: str, qty: float, price: float):
        """Place limit order"""
        try:
            if symbol not in self.config:
                print(f"Symbol {symbol} not in config")
                return None
            
            product_id = self.config[symbol]["product_id"]
            
            order = self.delta_client.place_order(
                product_id=product_id,
                size=qty,
                side=side,
                limit_price=price,
                time_in_force=TimeInForce.GTC
            )
            
            print(f"✅ Limit {side} order placed: {qty} {symbol} @ ${price:.2f}")
            return order
        except Exception as e:
            print(f"Error placing limit order for {symbol}: {e}")
            return None
    
    def place_stop_loss(self, symbol: str, entry_price: float, position_size: float):
        """Place stop loss order"""
        try:
            if symbol not in self.config:
                return False
            
            stop_loss_percent = self.config[symbol]["stop_loss_percent"]
            product_id = self.config[symbol]["product_id"]
            
            # Calculate stop loss price
            if position_size > 0:  # Long position
                stop_loss_price = entry_price * (1 - stop_loss_percent / 100)
            else:  # Short position
                stop_loss_price = entry_price * (1 + stop_loss_percent / 100)
            
            # Place stop market order
            order = self.delta_client.place_order(
                product_id=product_id,
                size=abs(position_size),
                side='sell' if position_size > 0 else 'buy',
                stop_price=stop_loss_price,
                order_type=OrderType.STOP_MARKET
            )
            
            print(f"✅ Stop loss placed @ ${stop_loss_price:.2f} for {symbol}")
            return True
        except Exception as e:
            print(f"Error placing stop loss for {symbol}: {e}")
            return False
    
    def place_initial_target(self, symbol: str, entry_price: float, position_size: float):
        """Place initial target order"""
        try:
            if symbol not in self.config:
                return False
            
            config = self.config[symbol]
            base_qty = config["base_qty"]
            target_percent = config["target_percent"]
            
            # Calculate target price
            if position_size > 0:  # Long position
                target_price = entry_price * (1 + target_percent / 100)
                side = 'sell'
            else:  # Short position
                target_price = entry_price * (1 - target_percent / 100)
                side = 'buy'
            
            # Use the actual position size or base_qty, whichever is smaller
            order_qty = min(abs(position_size), base_qty)
            
            # Place limit order
            self.place_limit_order(symbol, side, order_qty, target_price)
            
            direction = "profit" if position_size > 0 else "cover"
            print(f"🎯 Initial target for {symbol}: ${entry_price:.2f} → ${target_price:.2f} ({target_percent}% {direction})")
            return True
        except Exception as e:
            print(f"Error placing initial target for {symbol}: {e}")
            return False
    
    def check_and_enter_position(self, symbol: str):
        """Check if we should enter a new position"""
        # Check if already have position
        position = self.get_position(symbol)
        if position:
            print(f"{symbol}: Already have position: {position['size']} @ ${position['entry_price']:.2f}")
            return False
        
        # Check if symbol is enabled
        if not self.config[symbol]["enabled"]:
            print(f"{symbol}: Trading disabled")
            return False
        
        # Check balance for this specific symbol
        balance = self.get_available_balance_for_trading(symbol)
        if balance < 10:  # Minimum $10 to trade
            print(f"{symbol}: Insufficient balance: ${balance:.2f}")
            return False
        
        # Get current price
        current_price = self.get_price(symbol)
        if not current_price:
            print(f"{symbol}: Could not get price")
            return False
        
        config = self.config[symbol]
        base_qty = config["base_qty"]
        
        print(f"\n📈 {symbol}: Entering position")
        print(f"  Name: {config['display_name']}")
        print(f"  Price: ${current_price:.2f}")
        print(f"  Qty: {base_qty}")
        print(f"  Target: {config['target_percent']}%")
        print(f"  Stop Loss: {config['stop_loss_percent']}%")
        print(f"  Available balance: ${balance:.2f}")
        
        # Calculate cost and check if we have enough
        cost = current_price * base_qty * config['min_lot_size'] / config['leverage']
        print(f"  Estimated cost (with {config['leverage']}x leverage): ${cost:.2f}")
        if balance < cost:
            print(f"❌ {symbol}: Insufficient funds. Need ${cost:.2f}, have ${balance:.2f}")
            return False
        
        # Place market buy order
        order = self.place_market_order(symbol, 'buy', base_qty)
        if not order:
            return False
        
        # Wait for order to fill
        time.sleep(2)
        
        # Check if position was opened
        position = self.get_position(symbol)
        if position:
            print(f"✅ {symbol}: Position opened: {position['size']} @ ${position['entry_price']:.2f}")
            
            # Place target order
            self.place_initial_target(symbol, position['entry_price'], position['size'])
            
            # Place stop loss (optional - commented out for safety)
            # self.place_stop_loss(symbol, position['entry_price'], position['size'])
            
            # Initialize averaging count
            self.averaging_counts[symbol] = 0
            
            return True
        else:
            print(f"❌ {symbol}: Position not opened")
            return False
    
    def check_averaging(self, symbol: str):
        """Check if we should average down"""
        position = self.get_position(symbol)
        if not position:
            return False
        
        # Initialize averaging count if not exists
        if symbol not in self.averaging_counts:
            self.averaging_counts[symbol] = 0
        
        # Check if max averaging reached
        max_average = self.config[symbol]["max_average_orders"]
        if self.averaging_counts[symbol] >= max_average:
            print(f"{symbol}: Max averaging reached: {self.averaging_counts[symbol]}/{max_average}")
            return False
        
        # Get lowest target price
        lowest_target = self.get_lowest_target_price(symbol)
        if not lowest_target:
            print(f"{symbol}: No target orders found")
            return False
        
        # Get current price
        current_price = self.get_price(symbol)
        if not current_price:
            return False
        
        # Calculate percentage below target (for long positions)
        if position['side'] == 'long':
            price_diff_percent = ((lowest_target - current_price) / lowest_target) * 100
        else:  # For short positions
            price_diff_percent = ((current_price - lowest_target) / lowest_target) * 100
        
        trigger_percent = self.config[symbol]["averaging_trigger"]
        
        print(f"  {symbol}: Current price: ${current_price:.2f}")
        print(f"  {symbol}: Lowest target: ${lowest_target:.2f}")
        print(f"  {symbol}: Below target: {price_diff_percent:.2f}% (trigger: {trigger_percent}%)")
        
        if price_diff_percent >= trigger_percent:
            print(f"⚠️ {symbol}: Averaging condition met!")
            
            config = self.config[symbol]
            averaging_qty = config["base_qty"]
            
            # Check balance for averaging
            balance = self.get_available_balance_for_trading(symbol)
            cost = current_price * averaging_qty
            
            if balance < cost:
                print(f"❌ {symbol}: Insufficient funds for averaging. Need ${cost:.2f}, have ${balance:.2f}")
                return False
            
            # Place averaging order
            if position['side'] == 'long':
                order = self.place_market_order(symbol, 'buy', averaging_qty)
            else:
                order = self.place_market_order(symbol, 'sell', averaging_qty)
                
            if order:
                self.averaging_counts[symbol] += 1
                
                # Wait for order to fill
                time.sleep(2)
                
                # Get new position data
                position = self.get_position(symbol)
                if position:
                    # Place target for this averaging order
                    target_percent = config["target_percent"]
                    
                    if position['side'] == 'long':
                        target_price = current_price * (1 + target_percent / 100)
                        side = 'sell'
                    else:
                        target_price = current_price * (1 - target_percent / 100)
                        side = 'buy'
                    
                    self.place_limit_order(symbol, side, averaging_qty, target_price)
                    print(f"✅ {symbol}: Averaging order #{self.averaging_counts[symbol]} placed")
                    return True
        
        return False

    def check_and_manage_position(self, symbol: str):
        """Check and manage existing position"""
        print(f"\n🔍 Checking {symbol} ({self.config[symbol]['display_name']}):")
        
        position = self.get_position(symbol)
        if position:
            current_price = self.get_price(symbol)
            if current_price:
                # Calculate P&L
                if position['side'] == 'long':
                    pnl = (current_price - position['entry_price']) * position['size']
                else:  # short position
                    pnl = (position['entry_price'] - current_price) * abs(position['size'])
                
                pnl_percent = (pnl / (abs(position['size']) * position['entry_price'])) * 100
                
                print(f"  Position: {position['size']} {symbol} @ ${position['entry_price']:.2f} ({position['side']})")
                print(f"  Current: ${current_price:.2f}")
                print(f"  P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")
                print(f"  Unrealized P&L: ${position['unrealized_pnl']:.2f}")
                print(f"  Averaging count: {self.averaging_counts.get(symbol, 0)}/{self.config[symbol]['max_average_orders']}")
                
                # Check for averaging
                self.check_averaging(symbol)
            else:
                print(f"  {symbol}: Could not get current price")
        else:
            print(f"  {symbol}: No position")
            # Try to enter new position if enabled
            if self.config[symbol]["enabled"]:
                self.check_and_enter_position(symbol)
    
    def close_position(self, symbol: str):
        """Close position"""
        position = self.get_position(symbol)
        if not position:
            print(f"{symbol}: No position to close")
            return False
        
        size = position['size']
        side = 'sell' if size > 0 else 'buy'
        
        print(f"\n🛑 Closing {symbol} position:")
        print(f"  Size: {size}")
        print(f"  Side: {side}")
        
        # Cancel all open orders first
        self.cancel_all_orders_for_symbol(symbol)
        time.sleep(1)
        
        # Place market order to close
        order = self.place_market_order(symbol, side, abs(size))
        if order:
            print(f"✅ {symbol}: Position closed")
            
            # Clear averaging count
            if symbol in self.averaging_counts:
                del self.averaging_counts[symbol]
            
            self.successful_trades += 1
            return True
        
        return False
    
    def close_all_positions(self):
        """Close all positions for all symbols"""
        print("\n🛑 Closing all positions...")
        
        for symbol in self.config:
            position = self.get_position(symbol)
            if position:
                self.close_position(symbol)
                time.sleep(1)
        
        print("✅ All positions closed")
        
        # Update Home Assistant after closing positions
        if self.mqtt_enabled:
            self.update_ha_sensors()
    
    def show_summary(self):
        """Show trading summary"""
        print("\n" + "="*60)
        print("📊 TRADING SUMMARY")
        print("="*60)
        
        # Show all balances
        print("\n💰 BALANCES:")
        try:
            product = self.delta_client.get_product(27)
            wallet = self.delta_client.get_balances(product['settling_asset']['id'])
            
            if isinstance(wallet, list):
                for asset in wallet:
                    symbol = asset.get('asset_symbol', 'UNKNOWN')
                    available = float(asset.get('available_balance', 0))
                    total = float(asset.get('balance', 0))
                    if available > 0 or total > 0:
                        print(f"  {symbol}: Available=${available:.2f}, Total=${total:.2f}")
        except Exception as e:
            print(f"  Error getting balances: {e}")
        
        # Show positions
        print("\n📈 ACTIVE POSITIONS:")
        any_active = False
        for symbol in self.config:
            position = self.get_position(symbol)
            if position:
                any_active = True
                current_price = self.get_price(symbol)
                if current_price:
                    if position['side'] == 'long':
                        pnl = (current_price - position['entry_price']) * position['size']
                    else:
                        pnl = (position['entry_price'] - current_price) * abs(position['size'])
                    
                    print(f"  {symbol}: {position['size']} @ ${position['entry_price']:.2f} "
                          f"({position['side']}) | P&L: ${pnl:.2f}")
        
        if not any_active:
            print("  No active positions")
        
        # Show statistics
        print(f"\n📊 STATISTICS:")
        print(f"  Total trades placed: {self.total_trades}")
        print(f"  Successful trades: {self.successful_trades}")
        if self.total_trades > 0:
            success_rate = (self.successful_trades / self.total_trades) * 100
            print(f"  Success rate: {success_rate:.1f}%")
        
        print("="*60)
    
    def run_multi_symbol_trading(self, interval: int = 30):
        """Run multi-symbol trading bot with Home Assistant integration"""
        print("\n" + "="*60)
        print("🤖 MULTI-SYMBOL DELTA TRADING BOT")
        print("="*60)
        print("Strategy: Buy, set target, average down below target")
        
        # Home Assistant status
        if self.mqtt_enabled:
            print(f"🏠 Home Assistant: {'✅ CONNECTED' if self.ha_connected else '❌ DISCONNECTED'}")
        
        print("\n📊 CONFIGURED SYMBOLS:")
        
        # Display all configured symbols
        for symbol, config in self.config.items():
            status = "✅ ENABLED" if config["enabled"] else "❌ DISABLED"
            print(f"  {symbol}: {config['display_name']} | {status}")
            print(f"     Target: {config['target_percent']}% | Stop: {config['stop_loss_percent']}%")
            print(f"     Avg Trigger: {config['averaging_trigger']}% | Max Avg: {config['max_average_orders']}")
        
        print(f"\n⏰ Check interval: {interval} seconds")
        print("="*60)
        
        # Show initial balances
        print("\n💰 INITIAL BALANCES:")
        try:
            product = self.delta_client.get_product(27)
            wallet = self.delta_client.get_balances(product['settling_asset']['id'])
            
            if isinstance(wallet, list):
                for asset in wallet:
                    symbol = asset.get('asset_symbol', 'UNKNOWN')
                    available = float(asset.get('available_balance', 0))
                    total = float(asset.get('balance', 0))
                    if available > 0 or total > 0:
                        print(f"  {symbol}: Available=${available:.2f}, Total=${total:.2f}")
        except Exception as e:
            print(f"  Error getting initial balances: {e}")
        
        cycle = 0
        try:
            while True:
                cycle += 1
                print(f"\n🔄 CYCLE #{cycle} - {time.strftime('%H:%M:%S')}")
                
                # Only run trading if bot is enabled
                if self.bot_running:
                    # Check each enabled symbol
                    for symbol in self.config:
                        if self.config[symbol]["enabled"]:
                            self.check_and_manage_position(symbol)
                            time.sleep(1)  # Small delay between symbols
                else:
                    print("⏸️ Bot is paused (check Home Assistant)")
                
                # Update Home Assistant sensors every cycle
                if self.mqtt_enabled and cycle % 2 == 0:  # Update every 2 cycles to reduce load
                    self.update_ha_sensors()
                
                # Show summary every 5 cycles
                if cycle % 5 == 0:
                    self.show_summary()
                
                # Wait for next cycle
                print(f"\n⏳ Next check in {interval} seconds...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Bot stopped by user")
            
            # Ask user if they want to close positions
            response = input("\nDo you want to close all positions? (y/N): ").strip().lower()
            if response == 'y':
                self.close_all_positions()
            
            # Update Home Assistant one last time
            if self.mqtt_enabled:
                self.update_ha_sensors()
            
            print("\n📊 FINAL SUMMARY:")
            self.show_summary()
            print("\n👋 Goodbye!")


# Simple execution
if __name__ == "__main__":
    # Load API keys
    API_KEY = os.environ.get('DELTA_API_KEY', 'EKbuTUhExAsxWmRumQpxsc2iYPj00q')
    API_SECRET = os.environ.get('DELTA_API_SECRET', 'koTpMmIyYHmYWw5WxUfa2p9POsFACbgZGzQuChq6oTYkUnWPDoV1zFBAYj93')
    
    # Create trader
    trader = MultiSymbolDeltaTrader(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=False
    )
    
    # Run bot
    trader.run_multi_symbol_trading(interval=10)
