# Htier Live Streaming Hub - Comprehensive Documentation

To run the Htier Application, double click on run_app.bat,
This will run the Htier Application in the browser, 
So user can select the multiple protocols from the dropdown menu

## Table of Contents
1. [Application Overview](#application-overview)
2. [Dropdown Options Reference](#dropdown-options-reference)
3. [Rust Server Integration](#rust-server-integration)
4. [Protocol Configuration Guide](#protocol-configuration-guide)
5. [Setup Instructions](#setup-instructions)
6. [Troubleshooting](#troubleshooting)

---

## Application Overview

The **Htier Live Streaming Hub** is a Streamlit-based web application that provides a unified interface for connecting to multiple real-time data sources and live video streams. It supports four main protocols:

- **MQTT** - IoT messaging and real-time data streams
- **HTTP/REST** - Data polling from REST APIs (designed for Rust servers)
- **Modbus TCP** - Industrial device communication and PLC data
- **Video** - Live video streaming from webcams, MJPEG, and RTSP sources

### Key Features
- Multi-protocol support with seamless switching
- Real-time data streaming and visualization
- Live video streaming with WebRTC, MJPEG, and RTSP
- Cross-thread communication for non-blocking UI
- Htier message format for all protocols
- File-based message storage and history

---

## Dropdown Options Reference

### 1. Main Protocol Selection Dropdown

**Location:** Main interface header  
**Label:** "Choose streaming protocol:"

| Option | Description | Use Case |
|--------|-------------|----------|
| **MQTT** | IoT messaging protocol | Connect to MQTT brokers for real-time IoT data, sensor readings, and publish/subscribe messaging |
| **HTTP** | REST API polling | Connect to HTTP/REST servers (especially Rust servers) to poll data endpoints |
| **Modbus** | Industrial protocol | Connect to Modbus TCP devices, PLCs, and industrial equipment for register data |
| **Video** | Video streaming | Stream live video from webcams, IP cameras (MJPEG), or RTSP video feeds |

**Help Text:** "HTTP = Bridge script data via Rust server | Modbus = Direct TCP connection | MQTT = IoT messaging | Video = Live video streaming"

---

### 2. Video Stream Type Dropdown

**Location:** Video protocol configuration panel  
**Label:** "Stream Type"  
**Appears when:** Video protocol is selected

| Option | Description | Configuration Required |
|--------|-------------|----------------------|
| **mjpeg** | HTTP MJPEG stream | Requires MJPEG URL (e.g., `http://camera-ip/video.mjpg`) |
| **rtsp** | RTSP video feed | Requires RTSP URL (e.g., `rtsp://camera-server/stream`) |
| **webcam** | Local webcam via WebRTC | No URL required - uses browser webcam access |

**Help Text:** "Choose the type of video stream"

**Default:** mjpeg (first option)

---

### 3. Advanced Video Settings

**Location:** Video configuration panel, under "Advanced Settings" expander

#### Processing Log Interval
- **Type:** Number input (acts as value selector)
- **Default:** 30 frames
- **Range:** Minimum 1 frame
- **Description:** Log processing information every N frames
- **Help Text:** "Log processing info every N frames"

#### Enable Frame Processing
- **Type:** Checkbox
- **Default:** Enabled (True)
- **Description:** Enable/disable frame processing information logging
- **Help Text:** "Log frame processing information"

---

## Rust Server Integration

### Overview

The application includes integration with a **Rust server** through HTTP communication. While the Replit project contains the Python side of this integration, the Rust server itself is a separate application that must be running externally.

### Architecture

```
┌─────────────────────┐
│  Python Bridge      │
│  (stream_bridge_    │
│   http_*.py)        │
└──────────┬──────────┘
           │ HTTP POST/GET
           ↓
┌─────────────────────┐
│  Rust Server        │
│  (rust-app.exe)     │
│  Port: 5000         │
└─────────────────────┘
           ↑
           │ HTTP GET
┌──────────┴──────────┐
│  Streamlit App      │
│  (HTTP Handler)     │
└─────────────────────┘
```

### Rust Server Requirements

The Rust server must be running at **`http://localhost:5000`** and provide the following endpoints:

#### 1. Health Check Endpoint
```
GET /health
Response: 200 OK
```
Used by both the Python bridge and Streamlit app to verify server availability.

#### 2. Data Storage Endpoint
```
POST /data/{key}
Headers: Content-Type: text/plain
Body: <value>
Response: JSON confirmation
```
The Python bridge stores data with keys like "python_message".

#### 3. Data Retrieval Endpoint
```
GET /data/python_message
Response: <stored data>
```
The Streamlit app polls this endpoint to retrieve messages.

#### 4. Cryptographic Operations Endpoint (Optional)
```
POST /crypto
Headers: Content-Type: application/json
Body: {"operation": "random_hex|sha256", "data": "...", "length": ...}
Response: {"success": true, "data": {"result": "..."}}
```
Supports operations like random hex generation and SHA256 hashing.

### Python Bridge Script

**File:** `attached_assets/stream_bridge_http_1757249928257.py`

This script acts as a bridge between Modbus TCP data and the Rust server:

1. **Runs a Modbus TCP Server** on `127.0.0.1:12345`
2. **Generates random register values** (simulates industrial data)
3. **Sends data to Rust server** via HTTP POST to `/data/python_message`
4. **Formats data** as: `[array_of_values]_timestamp`

**Example Message Format:**
```
[45, 23, 78, 12, 0, 16256]_2025-10-05 14:30:22
```

### Setting Up Rust Integration

#### Step 1: Start the Rust Server
```bash
# Navigate to your Rust application directory
cd path/to/rust-app
cargo run
# Or run the compiled executable
./rust-app.exe
```

The server must be listening on **port 5000**.

#### Step 2: Verify Rust Server
```bash
curl http://localhost:5000/health
```
Should return `200 OK`.

#### Step 3: Run the Python Bridge (Optional)
```bash
python attached_assets/stream_bridge_http_1757249928257.py
```

This will:
- Check if Rust server is running
- Start Modbus server
- Begin sending data to Rust server every few seconds

#### Step 4: Connect Streamlit App to Rust Server
1. Select **HTTP** protocol in the dropdown
2. Configure:
   - Host: `localhost`
   - Port: `5000`
   - Poll Interval: `5` seconds (or desired interval)
3. Click **Connect**
4. Data from the Python bridge will appear in the message panel

### Rust Server Data Flow

1. **Python Bridge** → Reads Modbus data → Sends to Rust server (`/data/python_message`)
2. **Rust Server** → Stores the message in memory/database
3. **Streamlit HTTP Handler** → Polls Rust server (`/data/python_message`) → Displays in UI

### Expected Rust Server Behavior

- **Store and retrieve** data with key-value pairs
- **Handle concurrent requests** from both bridge script and Streamlit app
- **Return latest data** when polled
- **Optional:** Provide cryptographic operations for data processing

---

## Protocol Configuration Guide

### MQTT Configuration

| Field | Description | Example |
|-------|-------------|---------|
| **Broker Host** | MQTT broker address | `broker.emqx.io` |
| **Port** | MQTT broker port | `1883` |
| **Client ID** | Unique client identifier | `streamlit_client_123` |
| **Username** | Authentication username (optional) | `user` |
| **Password** | Authentication password (optional) | `pass` |
| **Keep Alive** | Connection keep-alive seconds | `60` |
| **Topic** | Topic to subscribe to | `sensor/temperature` |

**Connection Flow:**
1. Enter broker details
2. Click **Connect** - status shows "Connecting..."
3. Wait for "🟢 Connected" status
4. Enter topic name
5. Click **Subscribe** to receive messages

---

### HTTP/REST Configuration

| Field | Description | Example |
|-------|-------------|---------|
| **Server Host** | REST API server address | `localhost` |
| **Port** | Server port | `5000` |
| **Poll Interval** | Seconds between data polls | `5` |

**Recommended for:** Rust server integration, REST APIs, web services

**Data Retrieval:**
- Polls `/data/python_message` endpoint
- Parses bridge script format: `[array]_timestamp`
- Displays Modbus registers and timestamps

---

### Modbus TCP Configuration

| Field | Description | Example |
|-------|-------------|---------|
| **Modbus Host** | Device IP address | `127.0.0.1` |
| **Port** | Modbus TCP port | `12345` |
| **Unit ID** | Modbus unit/slave ID | `1` |
| **Start Address** | First register address | `0` |
| **Register Count** | Number of registers to read | `10` |
| **Poll Interval** | Seconds between polls | `2` |

**Use Cases:**
- Industrial PLCs
- SCADA systems
- Modbus-enabled sensors
- Test with Python bridge script (creates local Modbus server)

---

### Video Streaming Configuration

#### Webcam Stream
| Field | Description |
|-------|-------------|
| **Stream Type** | Select "webcam" |
| No additional configuration needed |

#### MJPEG Stream
| Field | Description | Example |
|-------|-------------|---------|
| **Stream Type** | Select "mjpeg" |
| **MJPEG URL** | Camera MJPEG endpoint | `http://192.168.1.100/video.mjpg` |

#### RTSP Stream
| Field | Description | Example |
|-------|-------------|---------|
| **Stream Type** | Select "rtsp" |
| **RTSP URL** | Camera RTSP feed | `rtsp://192.168.1.100:554/stream` |

**Advanced Settings:**
- **Enable Frame Processing:** Log frame statistics
- **Processing Log Interval:** Frames between logs (default: 30)

---

## Setup Instructions

### Prerequisites

**Python 3.7+** and the following packages:

```bash
pip install streamlit paho-mqtt pymodbustcp requests streamlit-webrtc opencv-python av
```

### Running the Application

#### On Replit
```bash
streamlit run app.py --server.port 5000
```

#### Locally
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`

### Configuration File

Create `.streamlit/config.toml`:

```toml
[server]
headless = true
address = "0.0.0.0"
port = 5000
```

### Complete Setup Example (with Rust Server)

1. **Start Rust Server:**
   ```bash
   cd rust-app
   cargo run
   ```

2. **Run Python Bridge (in new terminal):**
   ```bash
   python attached_assets/stream_bridge_http_1757249928257.py
   ```

3. **Run Streamlit App (in new terminal):**
   ```bash
   streamlit run app.py --server.port 5000
   ```

4. **Access Application:**
   Open `http://localhost:5000` in browser

5. **Connect to Rust Data:**
   - Select **HTTP** protocol
   - Host: `localhost`, Port: `5000`
   - Click **Connect**
   - View real-time Modbus data flowing through Rust server

---

## Troubleshooting

### Issue: "Video streaming dependencies not installed"
**Solution:**
```bash
pip install streamlit-webrtc opencv-python av
```
Restart the application.

### Issue: "Rust server is not running"
**Solution:**
1. Verify Rust server is running: `curl http://localhost:5000/health`
2. Check if another application is using port 5000
3. Start Rust server before running bridge script

### Issue: MQTT not connecting
**Solutions:**
- Verify internet connection
- Check broker address and port
- Ensure firewall allows MQTT traffic
- Try default broker: `broker.emqx.io:1883`

### Issue: Modbus connection failed
**Solutions:**
- Verify Modbus server is running
- Check IP address and port
- Ensure no firewall blocking
- Verify start address and register count are valid

### Issue: Video stream not loading
**Solutions:**
- **Webcam:** Allow browser camera permissions
- **MJPEG/RTSP:** Verify URL is accessible
- Check camera network connectivity
- Try different stream type

### Issue: No messages appearing
**Solutions:**
1. Click **Refresh Messages** button
2. Verify connection status shows "🟢 Connected"
3. For MQTT: Ensure topic is subscribed
4. Check that data source is sending data

### Issue: Messages cleared unexpectedly
**Solution:**
- Protocol switching clears messages automatically
- Use **Refresh Messages** to load history
- Messages are saved in `Htier_messages.pkl`

---

## System Architecture

### Frontend (Streamlit)
- Multi-protocol interface
- Real-time message display
- Video streaming panel
- Configuration forms

### Backend (Protocol Handlers)
- **MQTTHandler:** Paho MQTT library
- **HTTPHandler:** Requests library with polling
- **ModbusHandler:** PyModbusTCP library
- **VideoHandler:** Streamlit-WebRTC + OpenCV

### Data Flow
- Protocol handlers run in background threads
- Messages saved to files (`Htier_messages.pkl`)
- UI thread reads files for display
- Cross-thread communication via file system

---

## Additional Resources

### Tested Configurations

**MQTT:**
- Broker: `broker.emqx.io:1883`
- Topic: `mosttopic` or `sensor/#`

**HTTP (Rust Server):**
- URL: `http://localhost:5000`
- Endpoint: `/data/python_message`

**Modbus:**
- Server: `127.0.0.1:12345` (Python bridge)
- Registers: 0-9 (10 registers)

**Video:**
- Webcam: Built-in camera
- MJPEG: `http://camera-ip/video.mjpg`
- RTSP: `rtsp://camera-server/stream`

### File Structure

```
project/
├── app.py                          # Main Streamlit application
├── attached_assets/
│   └── stream_bridge_http_*.py     # Python-Rust bridge script
├── .streamlit/
│   └── config.toml                 # Server configuration
├── Htier_messages.pkl          # Message storage
├── message_counter.txt             # Message counter
└── replit.md                       # Project documentation
```

---

## Glossary

- **MQTT:** Message Queuing Telemetry Transport - lightweight IoT messaging protocol
- **Modbus TCP:** Industrial communication protocol for PLCs and SCADA systems
- **RTSP:** Real-Time Streaming Protocol for video feeds
- **MJPEG:** Motion JPEG - HTTP-based video streaming format
- **WebRTC:** Web Real-Time Communication for browser-based media streaming
- **PLC:** Programmable Logic Controller
- **SCADA:** Supervisory Control and Data Acquisition

---

## Support

For issues or questions:
1. Check this documentation
2. Review error messages in console
3. Verify all dependencies are installed
4. Ensure external services (Rust server, MQTT broker, Modbus devices) are running
5. Check firewall and network settings

**Last Updated:** October 2025
