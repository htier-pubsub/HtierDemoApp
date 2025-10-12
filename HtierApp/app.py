import streamlit as st
import paho.mqtt.client as mqtt
import threading
import json
import time
from datetime import datetime
import queue
import os
import pickle
import requests
from pyModbusTCP.client import ModbusClient
from abc import ABC, abstractmethod

# Video streaming imports
try:
    from streamlit_webrtc import webrtc_streamer, WebRtcMode, RTCConfiguration
    import cv2
    import av
    VIDEO_STREAMING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Video streaming dependencies not available: {e}")
    VIDEO_STREAMING_AVAILABLE = False

# Global lock for thread safety
message_lock = threading.Lock()

# File-based storage for cross-thread communication (Htier for all protocols)
MESSAGE_FILE = "Htier_messages.pkl"
COUNTER_FILE = "message_counter.txt"

def save_message_to_file(message):
    """Save message to file for cross-thread access."""
    try:
        with message_lock:
            messages = []
            if os.path.exists(MESSAGE_FILE):
                with open(MESSAGE_FILE, 'rb') as f:
                    messages = pickle.load(f)
            
            messages.append(message)
            # Keep only last 100 messages
            if len(messages) > 100:
                messages = messages[-100:]
            
            with open(MESSAGE_FILE, 'wb') as f:
                pickle.dump(messages, f)
            
            #print(f"💾 SAVED: Message saved to file. Total in file: {len(messages)}")
    except Exception as e:
        print(f"❌ Error saving message to file: {e}")

def load_messages_from_file():
    """Load messages from file with thread-safe access."""
    try:
        with message_lock:
            if os.path.exists(MESSAGE_FILE):
                with open(MESSAGE_FILE, 'rb') as f:
                    messages = pickle.load(f)
                    return messages if messages else []
            else:
                # File doesn't exist, return empty list
                return []
    except Exception as e:
        print(f"❌ Error loading messages from file: {e}")
        # If there's an error reading, try to remove corrupted file
        try:
            with message_lock:
                if os.path.exists(MESSAGE_FILE):
                    os.remove(MESSAGE_FILE)
                    print("🗑️ Removed corrupted message file")
        except:
            pass
        return []

def increment_counter():
    """Increment message counter in file."""
    try:
        with message_lock:
            counter = 0
            if os.path.exists(COUNTER_FILE):
                with open(COUNTER_FILE, 'r') as f:
                    counter = int(f.read().strip())
            
            counter += 1
            with open(COUNTER_FILE, 'w') as f:
                f.write(str(counter))
            
            return counter
    except Exception as e:
        print(f"❌ Error updating counter: {e}")
        return 0

def get_counter():
    """Get current message counter from file."""
    try:
        if os.path.exists(COUNTER_FILE):
            with open(COUNTER_FILE, 'r') as f:
                return int(f.read().strip())
        return 0
    except Exception as e:
        return 0

def clear_ui_messages():
    """Clear messages from UI/session state only (keep saved file)."""
    try:
        # Force clear session state but keep files intact
        st.session_state.messages = []
        if 'last_processed_counter' in st.session_state:
            st.session_state.last_processed_counter = 0
        # Set flag to prevent immediate reloading
        st.session_state.messages_just_cleared = True
        #print("🗑️ Cleared UI session state messages (files preserved)")
        return True
    except Exception as e:
        print(f"❌ Error clearing UI messages: {e}")
        return False

def clear_all_messages():
    """Clear all messages from both file storage and session state."""
    try:
        with message_lock:
            # Clear message file
            if os.path.exists(MESSAGE_FILE):
                os.remove(MESSAGE_FILE)
                print("🗑️ Cleared message file")
            
            # Reset counter file
            if os.path.exists(COUNTER_FILE):
                os.remove(COUNTER_FILE)
                print("🗑️ Cleared counter file")
            
            # Force clear and reset all session state variables
            st.session_state.messages = []
            if 'last_processed_counter' in st.session_state:
                st.session_state.last_processed_counter = 0
            # Set flag to prevent immediate reloading
            st.session_state.messages_just_cleared = True
            print("🗑️ Cleared session state messages and reset counters")
                
            return True
    except Exception as e:
        print(f"❌ Error clearing messages: {e}")
        return False

def handle_protocol_change():
    """Handle protocol selection changes through selectbox on_change callback."""
    new_protocol = st.session_state.protocol_select
    old_protocol = st.session_state.active_protocol
    
    if new_protocol != old_protocol:
        print(f"🔄 PROTOCOL CHANGE: {old_protocol} -> {new_protocol}")
        
        # Step 1: Disconnect ALL protocols to prevent background messages
        for protocol_name, handler in st.session_state.protocol_handlers.items():
            if handler.status in ["Connected", "Connecting..."]:
                print(f"🔴 Disconnecting {protocol_name} (status: {handler.status})")
                handler.disconnect()
                print(f"✅ {protocol_name} disconnected")
        
        # Step 2: Clear UI messages for protocol switch (keep files)
        if clear_ui_messages():
            print(f"✅ UI messages cleared for protocol switch")
        else:
            print(f"❌ Failed to clear UI messages")
        
        # Step 3: Update active protocol
        st.session_state.active_protocol = new_protocol
        print(f"✅ Protocol change complete: Now using {new_protocol}")
        
        # No st.rerun() needed - selectbox change will trigger natural rerun

def force_refresh_messages():
    """Force refresh messages from file storage."""
    try:
        # Use force_reload=True to override messages_just_cleared flag
        messages_processed = process_message_queue(force_reload=True)
        print(f"🔄 Force refreshed: {len(st.session_state.messages)} messages loaded from file")
        return messages_processed
    except Exception as e:
        print(f"❌ Error force refreshing: {e}")
        return 0

# Initialize Htier session state variables
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Flag to prevent message reloading immediately after clearing
if 'messages_just_cleared' not in st.session_state:
    st.session_state.messages_just_cleared = False

# Legacy MQTT functions removed - now handled by MQTTHandler class

def process_message_queue(force_reload=False):
    """Load messages from file and update session state."""
    # Ensure messages list exists
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # Skip processing if messages were just cleared (prevent race condition)
    # BUT allow force_reload to override this (for user-initiated actions)
    if st.session_state.get('messages_just_cleared', False) and not force_reload:
        #print("🚫 Skipping message processing - messages were just cleared (use force_reload=True to override)")
        return 0
    
    # Load messages from file
    file_messages = load_messages_from_file()
    file_counter = get_counter()
    
    # If file is empty but session has messages, clear session (file was cleared)
    if len(file_messages) == 0 and len(st.session_state.messages) > 0:
        st.session_state.messages = []
        #print("🗑️ Session messages cleared - file was cleared")
        return 0
    
    # Filter messages to only show ones from current connection session (all protocols)
    connection_time = st.session_state.get('connection_time', None)
    if connection_time and file_messages:
        # Only show messages newer than connection time
        import datetime
        connection_dt = datetime.datetime.fromisoformat(connection_time)
        
        filtered_messages = []
        for msg in file_messages:
            if 'timestamp' in msg:
                try:
                    # Parse message timestamp - handle both formats
                    timestamp_str = msg['timestamp']
                    if 'T' in timestamp_str:
                        # ISO format: 2025-09-20T18:11:20.123
                        msg_time = datetime.datetime.fromisoformat(timestamp_str)
                    else:
                        # Standard format: 2025-09-20 18:11:20.123
                        msg_time = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                    
                    if msg_time >= connection_dt:
                        filtered_messages.append(msg)
                    #else:
                        #print(f"🕒 FILTERED OUT: {msg.get('protocol', 'Unknown')} message from {timestamp_str} (before connection)")
                except Exception as e:
                    # If timestamp parsing fails, include the message
                    print(f"⚠️ TIMESTAMP PARSE ERROR: {e} for timestamp '{msg.get('timestamp', 'None')}'")
                    filtered_messages.append(msg)
            else:
                # If no timestamp, include the message
                filtered_messages.append(msg)
        
        active_protocol = st.session_state.get('active_protocol', 'Unknown')
        #print(f"🕒 FILTERED: Showing {len(filtered_messages)} {active_protocol} messages since connection time {connection_time}")
        #print(f"🕒 FILTERED: Total messages in file: {len(file_messages)}")
        file_messages = filtered_messages
    
    # Update session state with filtered messages
    initial_count = len(st.session_state.messages)
    st.session_state.messages = file_messages
    current_count = len(st.session_state.messages)
    
    messages_processed = current_count - initial_count
    
    # Debug info
    #if file_counter > 0 or current_count > 0:
        #print(f"📊 STATS: File Counter: {file_counter}, File Messages: {len(file_messages)}, UI Display: {current_count}")
    
    return messages_processed

def get_filtered_messages(protocol_name):
    """Get messages filtered by current protocol."""
    all_messages = st.session_state.messages
    if not all_messages:
        return []
    
    # Filter messages by protocol
    filtered = [msg for msg in all_messages if msg.get('protocol', '').upper() == protocol_name.upper()]
    return filtered

# Legacy connection check removed - now handled by individual protocol handlers

# Abstract Protocol Handler Interface
class ProtocolHandler(ABC):
    """Abstract base class for all streaming protocol handlers."""
    
    def __init__(self, name):
        self.name = name
        self.status = "Disconnected"
        self.thread = None
        self.running = False
    
    @abstractmethod
    def connect(self, config) -> bool:
        """Connect to the data source."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the data source."""
        pass
    
    @abstractmethod
    def get_config_ui(self) -> dict:
        """Return Streamlit UI elements for configuration."""
        pass
    
    def save_message(self, message_data):
        """Save message using the Htier file system."""
        save_message_to_file(message_data)
        increment_counter()
        #print(f"📨 SAVED: Message saved to file for UI thread to load")

# MQTT Protocol Handler
class MQTTHandler(ProtocolHandler):
    def __init__(self):
        super().__init__("MQTT")
        self.client = None
        self.subscribed_topics = set()
    
    def connect(self, config):
        try:
            print(f"🔄 MQTT: Starting connection to {config['host']}:{config['port']}")
            self.client = mqtt.Client(client_id=config.get('client_id'), protocol=mqtt.MQTTv311)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            
            if config.get('username') and config.get('password'):
                print(f"🔑 MQTT: Using authentication for user: {config['username']}")
                self.client.username_pw_set(config['username'], config['password'])
            
            print(f"🌐 MQTT: Attempting to connect to {config['host']}:{config['port']}...")
            result = self.client.connect(config['host'], config['port'], config.get('keep_alive', 60))
            print(f"🔗 MQTT: Connection attempt result code: {result}")
            
            if result == 0:
                print(f"✅ MQTT: Starting client loop...")
                self.client.loop_start()
                self.status = "Connecting..."
                print(f"📡 MQTT: Status set to 'Connecting...', waiting for on_connect callback")
                return True
            else:
                print(f"❌ MQTT: Connection failed with result code: {result}")
                return False
        except Exception as e:
            print(f"❌ MQTT connection error: {e}")
            import traceback
            print(f"🔍 MQTT: Full error trace: {traceback.format_exc()}")
            return False
    
    def disconnect(self):
        if self.client:
            print(f"🔴 MQTT: Starting disconnect...")
            self.status = "Disconnecting"
            self.client.loop_stop()
            self.client.disconnect()
            # Wait a moment to ensure loop stops
            import time
            time.sleep(0.2)
            self.client = None
            self.status = "Disconnected"
            self.subscribed_topics.clear()
            # Clear connection time so next connection starts fresh
            if 'connection_time' in st.session_state:
                del st.session_state.connection_time
                print(f"🕒 {self.name}: Connection time cleared for fresh start")
            print(f"🔴 MQTT: Disconnect complete")
    
    def _on_connect(self, client, userdata, flags, rc):
        print(f"🎯 MQTT: on_connect callback triggered with result code: {rc}")
        if rc == 0:
            self.status = "Connected"
            print(f"✅ MQTT: Successfully connected! Status updated to 'Connected'")
        else:
            self.status = f"Failed (code {rc})"
            print(f"❌ MQTT: Connection failed with code {rc}. Status: {self.status}")
        print(f"📊 MQTT: Current status after callback: {self.status}")
    
    def _on_disconnect(self, client, userdata, rc):
        print(f"🔌 MQTT: on_disconnect callback triggered with result code: {rc}")
        self.status = "Disconnected"
        print(f"🔴 MQTT: Status updated to 'Disconnected'")
    
    def _on_message(self, client, userdata, msg):
        try:
            # Check if still connected before processing message
            if self.status not in ["Connected", "Connecting..."]:
                print(f"🚫 MQTT: Ignoring message - handler disconnected (status: {self.status})")
                return
                
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            try:
                parsed_payload = json.loads(payload)
            except json.JSONDecodeError:
                parsed_payload = payload
            
            message_data = {
                'protocol': 'MQTT',
                'timestamp': timestamp,
                'source': topic,
                'data': parsed_payload,
                'metadata': {'qos': msg.qos, 'retain': msg.retain}
            }
            
            self.save_message(message_data)
            print(f"📨 MQTT: {topic} -> {payload}")
        except Exception as e:
            print(f"❌ MQTT message error: {e}")
    
    def subscribe(self, topic):
        if self.client and self.status == "Connected":
            result, _ = self.client.subscribe(topic)
            if result == mqtt.MQTT_ERR_SUCCESS:
                self.subscribed_topics.add(topic)
                return True
        return False
    
    def publish(self, topic, message):
        if self.client and self.status == "Connected":
            result = self.client.publish(topic, message)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        return False
    
    def get_config_ui(self):
        config = {}
        config['host'] = st.text_input("MQTT Broker Host", value="broker.emqx.io")
        config['port'] = st.number_input("Port", value=1883, min_value=1, max_value=65535)
        config['client_id'] = st.text_input("Client ID", value=f"mqtt_{int(time.time())}")
        config['username'] = st.text_input("Username (optional)")
        config['password'] = st.text_input("Password (optional)", type="password")
        config['keep_alive'] = st.number_input("Keep Alive (seconds)", value=60)
        return config

# HTTP/Rust Server Handler  
class HTTPHandler(ProtocolHandler):
    def __init__(self):
        super().__init__("HTTP/Rust Server")
        self.base_url = ""
        self.poll_interval = 5
        self.last_data = None
    
    def connect(self, config):
        self.base_url = f"http://{config['host']}:{config['port']}"
        self.poll_interval = config.get('poll_interval', 5)
        
        # Test connection
        if self._check_health():
            self.running = True
            self.thread = threading.Thread(target=self._polling_loop)
            self.thread.daemon = True
            self.thread.start()
            self.status = "Connected"
            return True
        return False
    
    def disconnect(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.status = "Disconnected"
        # Clear connection time so next connection starts fresh
        if 'connection_time' in st.session_state:
            del st.session_state.connection_time
            print(f"🕒 {self.name}: Connection time cleared for fresh start")
    
    def _check_health(self):
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def _polling_loop(self):
        while self.running:
            try:
                # Poll for data from the Rust server
                response = requests.get(f"{self.base_url}/data/python_message", timeout=5)
                if response.status_code == 200:
                    data = response.text
                    if data != self.last_data:  # Only process new data
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        
                        # Parse the bridge script format: [array]_timestamp
                        try:
                            if '_' in data:
                                array_part, time_part = data.rsplit('_', 1)
                                # Try to parse the array part
                                if array_part.startswith('[') and array_part.endswith(']'):
                                    # Parse as array
                                    import ast
                                    parsed_array = ast.literal_eval(array_part)
                                    parsed_data = {
                                        'modbus_registers': parsed_array,
                                        'bridge_timestamp': time_part,
                                        'register_count': len(parsed_array) if isinstance(parsed_array, list) else 0
                                    }
                                else:
                                    parsed_data = {'raw_data': data, 'note': 'Could not parse as array'}
                            else:
                                parsed_data = {'raw_data': data}
                        except Exception as parse_error:
                            print(f"⚠️ HTTP parsing error: {parse_error}")
                            parsed_data = {'raw_data': data, 'parse_error': str(parse_error)}
                        
                        message_data = {
                            'protocol': 'HTTP',
                            'timestamp': timestamp,
                            'source': 'modbus_bridge_via_rust',
                            'data': parsed_data,
                            'metadata': {
                                'url': f"{self.base_url}/data/python_message",
                                'raw_response': data[:100] + '...' if len(data) > 100 else data
                            }
                        }
                        
                        self.save_message(message_data)
                        self.last_data = data
                        register_count = len(parsed_data.get('modbus_registers', []))
                        if 'modbus_registers' in parsed_data:
                            print(f"🌐 HTTP: modbus_bridge -> {register_count} registers: {parsed_data['modbus_registers'][:5]}...")
                        else:
                            print(f"🌐 HTTP: raw_data -> {data[:100]}")
                        print(f"🔍 HTTP DEBUG: Full response: {data[:200]}")
                
                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"❌ HTTP polling error: {e}")
                time.sleep(self.poll_interval)
    
    def get_config_ui(self):
        config = {}
        config['host'] = st.text_input("Rust Server Host", value="localhost")
        config['port'] = st.number_input("Rust Server Port", value=5000)
        config['poll_interval'] = st.number_input("Poll Interval (seconds)", value=2, min_value=1)
        st.info("💡 This connects to your Rust server that receives Modbus data from the bridge script.")
        return config

# Modbus Handler
class ModbusHandler(ProtocolHandler):
    def __init__(self):
        super().__init__("Modbus")
        self.client = None
        self.poll_interval = 2
        self.last_values = None
    
    def connect(self, config):
        try:
            self.client = ModbusClient(host=config['host'], port=config['port'])
            self.poll_interval = config.get('poll_interval', 2)
            
            if self.client.open():
                self.running = True
                self.thread = threading.Thread(target=self._polling_loop)
                self.thread.daemon = True
                self.thread.start()
                self.status = "Connected"
                return True
            return False
        except Exception as e:
            print(f"❌ Modbus connection error: {e}")
            return False
    
    def disconnect(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.client:
            self.client.close()
        self.status = "Disconnected"
    
    def _polling_loop(self):
        while self.running:
            try:
                if self.client:  # Check if client exists
                    # Read holding registers (adjust address and count as needed)
                    values = self.client.read_holding_registers(0, 10)  # Read 10 registers from address 0
                    
                    if values and values != self.last_values:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        
                        message_data = {
                            'protocol': 'Modbus',
                            'timestamp': timestamp,
                            'source': 'holding_registers',
                            'data': values,
                            'metadata': {'address': 0, 'count': 10}
                        }
                        
                        self.save_message(message_data)
                        self.last_values = values
                        print(f"⚡ Modbus: holding_registers -> {values}")
                else:
                    print("❌ Modbus client is None")
                    break
                
                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"❌ Modbus polling error: {e}")
                time.sleep(self.poll_interval)
    
    def get_config_ui(self):
        config = {}
        config['host'] = st.text_input("Modbus Host", value="127.0.0.1")
        config['port'] = st.number_input("Modbus Port", value=12345)
        config['poll_interval'] = st.number_input("Poll Interval (seconds)", value=2, min_value=1)
        return config


# Video Handler
class VideoHandler(ProtocolHandler):
    def __init__(self):
        super().__init__("Video Stream")
        self.stream_type = "webcam"
        self.stream_url = ""
        self.video_active = False
        self.frame_count = 0
        self.video_capture = None
        self.capture_thread = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()  # Thread-safe frame access
        
    def connect(self, config):
        try:
            if not VIDEO_STREAMING_AVAILABLE:
                print("❌ Video streaming dependencies not available")
                return False
                
            self.stream_type = config.get('stream_type', 'webcam')
            self.stream_url = config.get('stream_url', '')
            
            # For external video sources (MJPEG/RTSP), set up video capture
            if self.stream_type in ['mjpeg', 'rtsp']:
                if not self.stream_url:
                    print(f"❌ Video: No URL provided for {self.stream_type} stream")
                    return False
                    
                print(f"📹 Video: Attempting to connect to {self.stream_type} stream: {self.stream_url}")
                
                # Add timeout and better error handling
                self.video_capture = cv2.VideoCapture(self.stream_url)
                
                # Set capture timeout (5 seconds)
                self.video_capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                
                # Minimize buffering for smooth streaming
                self.video_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Check if capture opened successfully
                if not self.video_capture.isOpened():
                    print(f"❌ Video: Cannot open {self.stream_type} stream - URL may be invalid or unreachable: {self.stream_url}")
                    self.video_capture = None
                    return False
                
                # Test if the capture can read frames
                ret, frame = self.video_capture.read()
                if not ret:
                    print(f"❌ Video: Stream opened but cannot read frames from {self.stream_type}: {self.stream_url}")
                    print(f"    Possible reasons: Stream offline, wrong format, network timeout")
                    self.video_capture.release()
                    self.video_capture = None
                    return False
                
                print(f"✅ Video: Successfully connected to {self.stream_type} stream!")
                print(f"    Frame size: {frame.shape if frame is not None else 'Unknown'}")
                    
                # Start capture thread for external sources
                self.running = True
                self.capture_thread = threading.Thread(target=self._video_capture_loop)
                self.capture_thread.daemon = True
                self.capture_thread.start()
                
                print(f"📹 Video: {self.stream_type.upper()} stream connected successfully")
            
            self.status = "Connected"
            self.video_active = True
            st.session_state.video_active = True  # Centralized state
            
            # Log video stream activation
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            message_data = {
                'protocol': 'Video',
                'timestamp': timestamp,
                'source': f'{self.stream_type}_stream',
                'data': f'Video stream activated: {self.stream_type}',
                'metadata': {
                    'stream_type': self.stream_type,
                    'stream_url': self.stream_url if self.stream_url else 'webcam'
                }
            }
            self.save_message(message_data)
            
            print(f"📹 Video: Stream activated - {self.stream_type}")
            return True
            
        except Exception as e:
            self.video_active = False
            st.session_state.video_active = False  # Centralized state
            print(f"❌ Video connection error: {e}")
            return False
    
    def disconnect(self):
        # Stop video capture thread
        self.running = False
        self.video_active = False
        st.session_state.video_active = False  # Centralized state
        
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
            self.capture_thread = None
            
        if self.video_capture:
            self.video_capture.release()
            self.video_capture = None
            
        self.latest_frame = None
        self.status = "Disconnected"
        
        # Clear connection time so next connection starts fresh
        if 'connection_time' in st.session_state:
            del st.session_state.connection_time
            print(f"🕒 {self.name}: Connection time cleared for fresh start")
        
        # Clear UI messages to prevent old history from showing
        if clear_ui_messages():
            print(f"✅ Video: UI messages cleared after disconnect")
        else:
            print(f"❌ Video: Failed to clear UI messages after disconnect")
            
        # Log video stream deactivation (after clearing messages to prevent it showing immediately)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        message_data = {
            'protocol': 'Video',
            'timestamp': timestamp,
            'source': 'stream_control',
            'data': 'Video stream deactivated',
            'metadata': {'action': 'disconnect'}
        }
        self.save_message(message_data)
        
        print(f"📹 Video: Stream deactivated")
    
    def log_frame_processed(self):
        """Log frame processing for demonstration."""
        self.frame_count += 1
        if self.frame_count % 30 == 0:  # Log every 30 frames to avoid spam
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            message_data = {
                'protocol': 'Video',
                'timestamp': timestamp,
                'source': 'frame_processor',
                'data': f'Processed {self.frame_count} frames',
                'metadata': {
                    'total_frames': self.frame_count,
                    'stream_type': self.stream_type
                }
            }
            self.save_message(message_data)
    
    def _video_capture_loop(self):
        """Capture frames from external video sources (MJPEG/RTSP)."""
        while self.running and self.video_capture:
            try:
                ret, frame = self.video_capture.read()
                if ret:
                    # Convert to RGB immediately and store with thread safety
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    with self.frame_lock:
                        self.latest_frame = frame_rgb
                    self.log_frame_processed()
                else:
                    print(f"⚠️ Video: Failed to read frame from {self.stream_type} stream")
                    # Don't sleep in capture loop - let UI control display rate
                    
            except Exception as e:
                print(f"❌ Video capture error: {e}")
                time.sleep(1)  # Wait before retrying
    
    def get_config_ui(self):
        config = {}
        
        if not VIDEO_STREAMING_AVAILABLE:
            st.error("⚠️ Video streaming dependencies not installed.")
            st.info("📋 **Installation Instructions:**")
            st.code("pip install streamlit-webrtc opencv-python av", language="bash")
            st.write("After installing dependencies, restart the application.")
            # Still show basic config for testing
            st.write("**Video Stream Configuration** (Install dependencies to enable)")
            config['stream_type'] = st.selectbox(
                "Stream Type (Requires Dependencies)", 
                ["webcam", "mjpeg", "rtsp"],
                help="Install video dependencies to enable this feature",
                disabled=True
            )
            return config
        
        st.write("**Video Stream Configuration**")
        
        stream_options = ["mjpeg", "rtsp", "webcam"]  # Put mjpeg first as default
        config['stream_type'] = st.selectbox(
            "Stream Type", 
            stream_options,
            key="video_stream_type",
            help="Choose the type of video stream"
        )
        
        if config['stream_type'] in ["mjpeg", "rtsp"]:
            config['stream_url'] = st.text_input(
                "Stream URL", 
                value="",
                placeholder="e.g., http://camera-ip/video.mjpg or rtsp://camera-ip/stream",
                help="Enter the URL for your video stream"
            )
        
        # Additional configuration options
        with st.expander("Advanced Settings"):
            config['enable_processing'] = st.checkbox(
                "Enable Frame Processing", 
                value=True,
                help="Log frame processing information"
            )
            config['processing_interval'] = st.number_input(
                "Processing Log Interval (frames)", 
                value=30, 
                min_value=1,
                help="Log processing info every N frames"
            )
        
        return config


# Initialize protocol handlers
if 'protocol_handlers' not in st.session_state:
    st.session_state.protocol_handlers = {
        'MQTT': MQTTHandler(),
        'HTTP': HTTPHandler(), 
        'Modbus': ModbusHandler(),
        'Video': VideoHandler()
    }

if 'active_protocol' not in st.session_state:
    st.session_state.active_protocol = 'MQTT'

# Initialize protocol selector state (for event-driven switching)
if 'protocol_select' not in st.session_state:
    st.session_state.protocol_select = st.session_state.active_protocol

# Flag to prevent protocol switching during form submissions
if 'form_submission_in_progress' not in st.session_state:
    st.session_state.form_submission_in_progress = False

# Streamlit UI
st.set_page_config(page_title="Htier Live Streaming", page_icon="🌐", layout="wide")

st.title("🌐 Htier Live Streaming Hub")
st.caption("Connect to MQTT, HTTP/REST, or Modbus data sources")

# Do NOT auto-load messages on page load - keep right side empty by default
# Messages should only appear when:
# 1. User explicitly clicks Refresh button
# 2. New messages arrive from active connections  
# 3. User wants to see saved history
#print(f"📄 UI: Right side messages not auto-loaded (use Refresh to see saved messages)")

# Protocol selection
st.header("🔧 Protocol Selection")

# Add helpful guidance
st.info("💡 **Quick Guide:** Use **HTTP** to see bridge script data via Rust server, or **Modbus** for direct TCP connection")

# Protocol selector with event-driven switching (no more race conditions!)
st.selectbox(
    "Choose streaming protocol:",
    options=['MQTT', 'HTTP', 'Modbus', 'Video'],
    key='protocol_select',
    on_change=handle_protocol_change,
    help="HTTP = Bridge script data via Rust server | Modbus = Direct TCP connection | MQTT = IoT messaging | Video = Live video streaming"
)

# Get current active protocol (now managed entirely through on_change)
active_protocol = st.session_state.active_protocol
#print(f"📄 UI: Using {active_protocol} handler (active_protocol: {active_protocol})")

# Get current protocol handler - refresh to ensure correct handler after protocol switch
current_handler = st.session_state.protocol_handlers[st.session_state.active_protocol]
#print(f"📄 UI: Using {current_handler.name} handler (active_protocol: {st.session_state.active_protocol})")

# Create two columns for layout
col1, col2 = st.columns([1, 2])

with col1:
    st.header(f"📡 {current_handler.name} Configuration")
    
    # Get protocol-specific configuration UI  
    # Use unique form key to prevent state conflicts during protocol switching
    form_key = f"protocol_config_{st.session_state.active_protocol.lower()}"
    with st.form(form_key):
        config = current_handler.get_config_ui()
        
        col_connect, col_disconnect = st.columns(2)
        
        with col_connect:
            connect_clicked = st.form_submit_button("Connect", type="primary")
        
        with col_disconnect:
            disconnect_clicked = st.form_submit_button("Disconnect")
    
    # Handle connection/disconnection
    if connect_clicked:
        # Set flag to prevent protocol switching during form submission
        print(f"🔄 CONNECT START: Setting form_submission_in_progress=True")
        st.session_state.form_submission_in_progress = True
        
        # Use the active protocol (event-driven protocol switching prevents conflicts)
        target_protocol = st.session_state.active_protocol
        
        # Double-check we're working with the right protocol handler
        print(f"🔄 Connect clicked for {current_handler.name} (target_protocol: {target_protocol})")
        
        # Ensure we're using the correct handler for the target protocol
        correct_handler = st.session_state.protocol_handlers[target_protocol]
        
        if correct_handler.name != current_handler.name:
            print(f"⚠️ Handler mismatch detected! Expected {target_protocol}, got {current_handler.name}")
            correct_handler = st.session_state.protocol_handlers[target_protocol]
        
        correct_handler.disconnect()  # Disconnect first
        if correct_handler.connect(config):
            st.success(f"Connecting to {correct_handler.name}...")
            print(f"✅ {correct_handler.name} connection initiated successfully")
        else:
            st.error(f"Failed to connect to {correct_handler.name}")
            print(f"❌ {correct_handler.name} connection failed")
        
        # Reset flag after connection attempt
        print(f"🔄 CONNECT END: Setting form_submission_in_progress=False")
        st.session_state.form_submission_in_progress = False
    
    if disconnect_clicked:
        # Set flag to prevent protocol switching during form submission
        st.session_state.form_submission_in_progress = True
        
        # Ensure we're disconnecting the correct protocol handler
        active_protocol = st.session_state.active_protocol
        correct_handler = st.session_state.protocol_handlers[active_protocol]
        print(f"🔴 Disconnect clicked for {correct_handler.name} (active_protocol: {active_protocol})")
        correct_handler.disconnect()
        st.success(f"Disconnected {correct_handler.name} successfully")
        
        # Reset flag after disconnection
        st.session_state.form_submission_in_progress = False
    
    # Display connection status with automatic UI refresh on status change
    current_status = current_handler.status
    previous_status = st.session_state.get(f'previous_status_{st.session_state.active_protocol}', 'Unknown')
    
    # Check if status changed and trigger UI refresh
    if current_status != previous_status:
        print(f"🔄 Status changed from '{previous_status}' to '{current_status}' - refreshing UI")
        st.session_state[f'previous_status_{st.session_state.active_protocol}'] = current_status
        if current_status == "Connected" and previous_status in ["Connecting...", "Disconnected"]:
            print(f"✅ {st.session_state.active_protocol} connection completed successfully! UI updated.")
            # Record connection time in UI thread for message filtering (works for all protocols)
            import datetime
            connection_time = datetime.datetime.now().isoformat()
            st.session_state.connection_time = connection_time
            print(f"🕒 {st.session_state.active_protocol}: Connection time recorded in UI thread: {connection_time}")
            st.rerun()  # Refresh UI to show connected status
    
    status_color = "🟢" if current_status == "Connected" else "🔴"
    st.write(f"**Status:** {status_color} {current_status}")
    
    # Store current status for next comparison
    st.session_state[f'previous_status_{st.session_state.active_protocol}'] = current_status
    
    # Periodic refresh for connection status monitoring (especially for MQTT)
    if current_status == "Connecting...":
        print(f"🕒 Status is 'Connecting...' - checking for backend connection completion")
        import time
        time.sleep(1)  # Brief wait to allow callback to complete
        # Force check status again after a moment
        updated_status = current_handler.status
        if updated_status != current_status:
            print(f"🎯 Backend status changed to '{updated_status}' - triggering UI refresh")
            st.rerun()
    
    # Protocol-specific controls
    if current_handler.name == "MQTT" and current_handler.status == "Connected":
        st.markdown("---")
        st.subheader("📡 MQTT Controls")
        
        # Topic subscription
        with st.form("mqtt_topics"):
            topic = st.text_input("Topic", value="modtopic")
            col_sub, col_unsub, col_pub = st.columns(3)
            
            with col_sub:
                sub_clicked = st.form_submit_button("Subscribe")
            with col_unsub:
                unsub_clicked = st.form_submit_button("Unsubscribe") 
            with col_pub:
                pub_clicked = st.form_submit_button("Publish Test")
        
        if sub_clicked and topic:
            if current_handler.subscribe(topic):
                st.success(f"Subscribed to {topic}")
        
        if unsub_clicked and topic:
            st.info(f"Unsubscribed from {topic}")
        
        if pub_clicked and topic:
            test_message = '{"msg": "hello from Htier app"}'
            if current_handler.publish(topic, test_message):
                st.success(f"Published to {topic}")
        
        # Show subscribed topics
        if current_handler.subscribed_topics:
            st.write("**Active Subscriptions:**")
            for topic in current_handler.subscribed_topics:
                st.write(f"• {topic}")
    
    # Protocol information
    st.markdown("---")
    # Hide Protocol Info section during video streaming
    if not st.session_state.get('video_active', False):
        st.subheader("📋 Protocol Info")
        
        if current_handler.name == "MQTT":
            st.write("**Protocol:** Message Queuing Telemetry Transport")
            st.write("**Use Case:** IoT device communication, pub/sub messaging")
            st.write("**Data Flow:** Subscribe to topics, receive real-time messages")
        elif current_handler.name == "HTTP/Rust Server":
            st.write("**Protocol:** HTTP polling from Rust server")
            st.write("**Use Case:** Get Modbus data via bridge script")
            st.write("**Data Flow:** Bridge script -> Rust server -> Streamlit app")
            st.write("**Expected Format:** `[register_array]_timestamp`")
            st.success("💡 Use this to see your bridge script's rich register data!")
        elif current_handler.name == "Modbus":
            st.write("**Protocol:** Modbus TCP direct connection")
            st.write("**Use Case:** Direct Modbus server reading")
            st.write("**Data Flow:** Read holding registers directly from Modbus TCP server")
            st.info("ℹ️ This reads directly from Modbus server, not bridge script data")
        elif current_handler.name == "Video Stream":
            st.write("**Protocol:** Real-time Video Streaming")
            st.write("**Use Case:** Live video display and processing")
            st.write("**Data Flow:** Webcam/IP Camera → Real-time video feed")
            st.write("**Supported Sources:** Webcam, MJPEG streams, RTSP feeds")
            if VIDEO_STREAMING_AVAILABLE:
                st.success("📹 Video streaming ready! Connect to start viewing live video.")
            else:
                st.error("⚠️ Video streaming dependencies not available. Install streamlit-webrtc and opencv-python.")

with col2:
    # Video streaming panel (shown when Video protocol is active)
    if st.session_state.active_protocol == 'Video' and VIDEO_STREAMING_AVAILABLE:
        st.header("📹 Live Video Stream")
        
        video_handler = st.session_state.protocol_handlers['Video']
        
        if video_handler.status == "Connected" and video_handler.video_active:
            # Define video frame callback function
            def video_frame_callback(frame):
                img = frame.to_ndarray(format="bgr24")
                
                # Log frame processing if enabled
                config = video_handler.__dict__
                if config.get('enable_processing', True):
                    video_handler.log_frame_processed()
                
                # Basic frame processing (can be extended)
                # For now, just pass through the frame
                return av.VideoFrame.from_ndarray(img, format="bgr24")
            
            # Display video stream based on type
            if video_handler.stream_type == "webcam":
                st.write("**Source:** Webcam")
                webrtc_streamer(
                    key="webcam-stream",
                    mode=WebRtcMode.SENDRECV,
                    video_frame_callback=video_frame_callback,
                    rtc_configuration=RTCConfiguration({
                        "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
                    }),
                    media_stream_constraints={"video": True, "audio": False}
                )
            elif video_handler.stream_type == "mjpeg":
                st.write(f"**Source:** MJPEG Stream")
                st.write(f"**URL:** {video_handler.stream_url}")
                if video_handler.stream_url and video_handler.latest_frame is not None:
                    # Display live MJPEG stream
                    st.write("**Status:** 🟢 Streaming")
                    
                    # Thread-safe frame display (no blocking loops)
                    with video_handler.frame_lock:
                        current_frame = video_handler.latest_frame.copy()
                    
                    st.image(
                        current_frame, 
                        caption=f"MJPEG Stream - Frame #{video_handler.frame_count}",
                        use_column_width=True,
                        channels="RGB"
                    )
                    
                elif video_handler.stream_url:
                    st.write("**Status:** 🔄 Connecting...")
                    st.info("Attempting to connect to MJPEG stream. Please wait...")
                else:
                    st.warning("Please configure MJPEG stream URL")
                    
            elif video_handler.stream_type == "rtsp":
                st.write(f"**Source:** RTSP Stream")  
                st.write(f"**URL:** {video_handler.stream_url}")
                if video_handler.stream_url and video_handler.latest_frame is not None:
                    # Display live RTSP stream
                    st.write("**Status:** 🟢 Streaming")
                    
                    # Thread-safe frame display (no blocking loops)
                    with video_handler.frame_lock:
                        current_frame = video_handler.latest_frame.copy()
                    
                    st.image(
                        current_frame, 
                        caption=f"RTSP Stream - Frame #{video_handler.frame_count}",
                        use_column_width=True,
                        channels="RGB"
                    )
                    
                elif video_handler.stream_url:
                    st.write("**Status:** 🔄 Connecting...")
                    st.info("Attempting to connect to RTSP stream. Please wait...")
                else:
                    st.warning("Please configure RTSP stream URL")
            
            # Video stream controls
            # Hide Stream Stats during active video streaming for clean UI
            if not st.session_state.get('video_active', False):
                if st.button("📊 Stream Stats"):
                    st.info(f"Frames processed: {video_handler.frame_count}")  
        else:
            st.info("Click Connect to start video streaming")
            st.write("**Available stream types:**")
            st.write("• **Webcam:** Use your device's camera")
            st.write("• **MJPEG:** Connect to IP camera MJPEG stream")
            st.write("• **RTSP:** Connect to RTSP video feed")
        
        # Video mode - set auto_refresh to True but don't show controls
        auto_refresh = True
    else:    
       
        st.header("Live Messages")
        
        # Process any new messages from the queue (already done above)
        pass       
        
        auto_refresh = st.checkbox("Auto-refresh messages", value=True)
        
        col_refresh, col_clear = st.columns(2)
        with col_refresh:
            if st.button("🔄 Refresh"):
                # Reset the cleared flag and force reload messages
                st.session_state.messages_just_cleared = False
                message_count = force_refresh_messages()
                st.success(f"✅ Refreshed! Loaded {message_count} messages")
        
        with col_clear:
            if st.button("🗑️ Clear Messages"):
                if clear_ui_messages():
                    st.success("✅ All messages cleared!")
                    #print(f"🗑️ UI: Clear button pressed - all messages cleared")
                else:
                    st.error("❌ Failed to clear messages")
    
    
    # Debug info for message display (only load if not video streaming)
    if not st.session_state.get('video_active', False):
        file_counter = get_counter()
        file_messages = load_messages_from_file()
    else:
        file_counter = 0
        file_messages = []
    
    # First get the filtered messages
    current_protocol = st.session_state.active_protocol    
    if current_protocol == 'HTTP':
        protocol_filter = 'HTTP'
    else:
        protocol_filter = current_protocol
    
    # Show filter options (hide during video streaming)
    if not st.session_state.get('video_active', False) and current_protocol != 'Video':
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            show_all = st.checkbox("Show all protocols", value=False)
        with col_filter2:
            if not show_all:
                st.write(f"**Showing:** {protocol_filter} messages only")
    else:
        # During video streaming, default to show only video messages
        show_all = False
    
    # Get messages to display (only show if not video streaming or if inside expander)
    if show_all:
        messages_to_show = st.session_state.messages
        message_count = len(messages_to_show)
    else:
        messages_to_show = get_filtered_messages(protocol_filter)
        message_count = len(messages_to_show)
        total_count = len(st.session_state.messages)
        if total_count > message_count and not st.session_state.get('video_active', False):
            st.info(f"Showing {message_count} {protocol_filter} messages (Total: {total_count} from all protocols)")
    
    # Hide debug information during video streaming
    if not st.session_state.get('video_active', False) and current_protocol != 'Video':
        with st.expander("🔧 Debug Information", expanded=False):
            st.write(f"**File Counter:** {file_counter}")
            st.write(f"**File Messages:** {len(file_messages)}")
            st.write(f"**All Messages:** {len(st.session_state.messages)}")
            st.write(f"**Filtered Messages:** {len(messages_to_show)}")
            st.write(f"**Active Protocol:** {current_handler.name}")
            st.write(f"**Protocol Status:** {current_handler.status}")
        
        # Show protocol breakdown
        if st.session_state.messages:
            protocol_counts = {}
            for msg in st.session_state.messages:
                protocol = msg.get('protocol', 'Unknown')
                protocol_counts[protocol] = protocol_counts.get(protocol, 0) + 1
            st.write("**Messages by Protocol:**")
            for protocol, count in protocol_counts.items():
                st.write(f"  - {protocol}: {count}")
        
        # Show latest message info and raw data for debugging
        if messages_to_show:
            latest_msg = messages_to_show[-1]
            st.write(f"**Latest Filtered Message:** {latest_msg.get('timestamp', 'Unknown')} from {latest_msg.get('source', 'Unknown')}")
            
            # Show raw data structure for HTTP debugging
            if latest_msg.get('protocol') == 'HTTP':
                st.write("**HTTP Message Structure:**")
                st.json(latest_msg)
        elif st.session_state.messages:
            latest_msg = st.session_state.messages[-1]
            st.write(f"**Latest Any Message:** {latest_msg.get('timestamp', 'Unknown')} from {latest_msg.get('source', 'Unknown')}")
        else:
            st.write("**Latest Message:** None")
    
    # Messages are already filtered above
    
    # Hide message displays during video streaming
    if message_count > 0 and not st.session_state.get('video_active', False):
        st.success(f"🎉 **{message_count} Messages Received and Displayed!**")
        
        # Show messages in reverse order (newest first) - only if not video streaming
        if not st.session_state.get('video_active', False):
            for i, message in enumerate(reversed(messages_to_show)):
                # Htier message format
                protocol = message.get('protocol', 'Unknown')
                source = message.get('source', 'Unknown')
                timestamp = message.get('timestamp', 'Unknown')
                
                # Protocol-specific icons
                icon = "📨" if protocol == "MQTT" else "🌐" if protocol == "HTTP" else "⚡" if protocol == "Modbus" else "📡"
                
                with st.expander(f"{icon} {protocol}: {source} - {timestamp}", expanded=(i < 3)):
                    col_msg1, col_msg2 = st.columns([3, 1])
                    
                    with col_msg1:
                        st.write("**Protocol:**", protocol)
                        st.write("**Source:**", source)
                        st.write("**Timestamp:**", timestamp)
                        st.write("**Data:**")
                    
                        # Display data based on type
                        data_content = message.get('data')
                        if isinstance(data_content, dict):
                            # Special handling for HTTP modbus bridge data
                            if protocol == "HTTP" and 'modbus_registers' in data_content:
                                registers = data_content['modbus_registers']
                                st.write(f"**Modbus Registers ({len(registers)} values):**")
                                # Display registers in a more readable format
                                if len(registers) > 10:
                                    st.write(f"First 10: {registers[:10]}")
                                    st.write(f"Last 10: {registers[-10:]}")
                                    with st.expander("View all register values"):
                                        st.json(registers)
                                else:
                                    st.json(registers)
                                
                                # Show other fields too
                                if 'bridge_timestamp' in data_content:
                                    st.write(f"**Bridge Timestamp:** {data_content['bridge_timestamp']}")
                            else:
                                st.json(data_content)
                        elif isinstance(data_content, list):
                            st.write(f"Array with {len(data_content)} elements:")
                            st.json(data_content)
                        else:
                            st.code(str(data_content or 'No data'))
                    
                    with col_msg2:
                        st.write("**Metadata:**")
                        metadata = message.get('metadata', {})
                        if metadata:
                            for key, value in metadata.items():
                                st.write(f"**{key.title()}:** {value}")
                        else:
                            st.write("None")
    elif not st.session_state.get('video_active', False) and current_protocol != 'Video':
        total_messages = len(st.session_state.messages)
        if total_messages > 0 and not show_all:
            st.info(f"No {protocol_filter} messages yet. {total_messages} messages from other protocols. Check 'Show all protocols' to see them.")
        else:
            if current_handler.name == "MQTT":
                st.info("No messages received yet. Connect and subscribe to topics to start receiving messages.")
            elif current_handler.name == "HTTP/Rust Server": 
                st.info("No data received yet. Connect to start polling the Rust server for updates.")
            elif current_handler.name == "Modbus":
                st.info("No register data received yet. Connect to start reading Modbus holding registers.")
        
        # Show file status for troubleshooting
        file_counter = get_counter()
        file_messages = load_messages_from_file()
        
        if file_counter > 0:
            try:
                st.warning(f"⚠️ {file_counter} total messages received. Showing {len(messages_to_show)} {protocol_filter} messages.")
                if not show_all:
                    st.info("Enable 'Show all protocols' to see messages from other protocols.")
            except:
                st.warning(f"⚠️ {file_counter} total messages received.")
        
        # File vs session message count debugging (no auto-processing to prevent unwanted loading)
        if len(file_messages) > len(st.session_state.messages) and not st.session_state.get('messages_just_cleared', False):
            st.info(f"ℹ️ {len(file_messages)} messages saved in files. Use Refresh to load them.")
    
    # Auto-refresh functionality - use proper Streamlit auto-refresh
    if auto_refresh:
        # Faster refresh for video streaming, normal for other protocols
        video_handler = st.session_state.protocol_handlers.get('Video')
        # Use fragment-based auto-refresh to avoid infinite loops
        if not (video_handler and video_handler.video_active) and current_protocol != 'Video':
            st.write("🔄 Auto-refresh enabled (messages update automatically when received)")
        
        # If connected to any protocol, enable automatic UI refresh to pull new messages
        if current_handler and current_handler.status == "Connected":
            # Process messages on each UI refresh when connected
            process_message_queue()            
            
            if video_handler and video_handler.video_active:
                # Faster refresh for video streaming (0.5 seconds)
                import time
                time.sleep(0.5)
                st.rerun()
            else:
                # Auto-refresh the page every 2 seconds to check for new messages
                import time
                time.sleep(2)
                st.rerun()

# Footer
# Hide Htier Streaming Tips during video streaming
video_handler = st.session_state.protocol_handlers.get('Video')
if not (video_handler and video_handler.video_active):
    st.markdown("---")
    st.markdown("💡 **Htier Streaming Tips:**")
    
    if current_handler.name == "MQTT":
        st.markdown("- Use topics like `test/topic`, `sensor/temperature`, or `device/status`")
        st.markdown("- QoS 0 = at most once, QoS 1 = at least once, QoS 2 = exactly once")
    elif current_handler.name == "HTTP/Rust Server":
        st.markdown("- Make sure your Rust server is running on localhost:5000")
        st.markdown("- Data is polled from `/data/python_message` endpoint")
        st.markdown("- Only new/changed data triggers message updates")
    elif current_handler.name == "Modbus":
        st.markdown("- Connect to Modbus TCP server (default: 127.0.0.1:12345)")
        st.markdown("- Reads holding registers from address 0")
        st.markdown("- Only changed register values trigger updates")
    
    st.markdown("- Enable auto-refresh to see live messages")
    st.markdown("- All protocols use the same Htier message display format")

# Reset the messages_just_cleared flag at the very end of UI cycle
if st.session_state.get('messages_just_cleared', False):
    st.session_state.messages_just_cleared = False
    print("🔄 Reset messages_just_cleared flag at end of UI cycle")
