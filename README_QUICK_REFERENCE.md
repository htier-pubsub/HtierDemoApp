# Live Streaming App - Dropdown Options & Rust Integration Quick Reference

To run the Htier Application, double click on run_app.bat,
This will run the Htier Application in the browser, 
So user can select the multiple protocols from the dropdown menus as shown below


## 📋 All Dropdown Options

### 1️⃣ Main Protocol Selector
**Where:** Top of the interface  
**Label:** "Choose streaming protocol:"

```
┌─────────────────────────────────────────────┐
│ Choose streaming protocol:                  │
│ ┌─────────────────────────────────────────┐ │
│ │ MQTT                               ▼    │ │
│ │ HTTP                                    │ │
│ │ Modbus                                  │ │
│ │ Video                                   │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

| Option | What It Does | When to Use |
|--------|--------------|-------------|
| **MQTT** | Connect to MQTT message brokers | IoT devices, sensor data, real-time messaging |
| **HTTP** | Poll REST API endpoints | **Rust server data**, web APIs, bridge script data |
| **Modbus** | Connect to industrial devices | PLCs, SCADA systems, factory equipment |
| **Video** | Stream live video | Webcams, IP cameras, RTSP feeds |

---

### 2️⃣ Video Stream Type Selector
**Where:** Video configuration panel  
**When Visible:** Only when "Video" protocol is selected  
**Label:** "Stream Type"

```
┌─────────────────────────────────────────────┐
│ Stream Type:                                │
│ ┌─────────────────────────────────────────┐ │
│ │ mjpeg                              ▼    │ │
│ │ rtsp                                    │ │
│ │ webcam                                  │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

| Option | What It Streams | Required Configuration |
|--------|-----------------|----------------------|
| **mjpeg** | HTTP MJPEG video (IP cameras) | MJPEG URL: `http://camera-ip/video.mjpg` |
| **rtsp** | RTSP video feeds (network cameras) | RTSP URL: `rtsp://camera-server/stream` |
| **webcam** | Local computer camera | None - uses browser camera |

**Default Selection:** mjpeg

---

## 🦀 Rust Server Integration

### What Is It?
The app can connect to a **Rust server** running on your computer to receive real-time data. The Rust server acts as a data hub that:
- Stores data sent from Python bridge scripts
- Serves data to the Streamlit web app via HTTP
- Optionally provides cryptographic operations

### How It Works

```
┌──────────────────┐
│ Modbus Device    │
│ (or data source) │
└────────┬─────────┘
         │
         ↓
┌──────────────────┐      HTTP POST      ┌──────────────────┐
│ Python Bridge    │─────────────────────→│   Rust Server    │
│ Script           │  /data/python_message│   localhost:5000 │
└──────────────────┘                      └─────────┬────────┘
                                                    │
                                                    │ HTTP GET
                                                    ↓
                                          ┌──────────────────┐
                                          │  Streamlit App   │
                                          │  (HTTP Protocol) │
                                          └──────────────────┘
```

### Required Rust Server Endpoints

Your Rust server must provide these HTTP endpoints:

#### 1. Health Check
```
GET http://localhost:5000/health
→ Returns: 200 OK
```

#### 2. Store Data (from Python bridge)
```
POST http://localhost:5000/data/{key}
Headers: Content-Type: text/plain
Body: <your data>
→ Returns: JSON confirmation
```

#### 3. Get Data (for Streamlit app)
```
GET http://localhost:5000/data/python_message
→ Returns: Latest stored data
```

#### 4. Crypto Operations (Optional)
```
POST http://localhost:5000/crypto
Headers: Content-Type: application/json
Body: {"operation": "random_hex", "length": 16}
→ Returns: {"success": true, "data": {"result": "abc123..."}}
```

### Quick Setup Steps

1. **Start your Rust server:**
   ```bash
   cd your-rust-app
   cargo run
   # Server must listen on port 5000
   ```

2. **Verify it's running:**
   ```bash
   curl http://localhost:5000/health
   # Should return 200 OK
   ```

3. **(Optional) Run Python bridge:**
   ```bash
   python attached_assets/stream_bridge_http_1757249928257.py
   # This sends Modbus data to Rust server
   ```

4. **Connect Streamlit app:**
   - Select **HTTP** from protocol dropdown
   - Enter:
     - Host: `localhost`
     - Port: `5000`
     - Poll Interval: `5` seconds
   - Click **Connect**

### Data Format from Bridge Script

The Python bridge sends data in this format:
```
[array_of_modbus_values]_timestamp
```

**Example:**
```
[45, 23, 78, 12, 0, 16256]_2025-10-05 14:30:22
```

The Streamlit app automatically parses this to show:
- **Modbus Registers:** `[45, 23, 78, 12, 0, 16256]`
- **Bridge Timestamp:** `2025-10-05 14:30:22`

### Troubleshooting Rust Connection

| Problem | Solution |
|---------|----------|
| "Rust server not running" | Make sure Rust server is started and listening on port 5000 |
| Python bridge exits immediately | Rust server must be running BEFORE starting bridge script |
| No data in Streamlit | 1. Check Rust server is running<br>2. Verify bridge script is sending data<br>3. Click "Refresh Messages" in Streamlit |
| Port 5000 already in use | Stop other applications using port 5000, or change Rust server port |

---

## 🎯 Common Usage Scenarios

### Scenario 1: View Rust Server Data
1. Protocol dropdown → Select **HTTP**
2. Configure: `localhost:5000`, poll interval `5`
3. Connect
4. Data appears automatically

### Scenario 2: Monitor IoT Devices
1. Protocol dropdown → Select **MQTT**
2. Configure broker: `broker.emqx.io:1883`
3. Connect
4. Subscribe to topic: `sensor/temperature`

### Scenario 3: View IP Camera
1. Protocol dropdown → Select **Video**
2. Stream Type dropdown → Select **mjpeg**
3. Enter camera URL: `http://192.168.1.100/video.mjpg`
4. Connect

### Scenario 4: Read Industrial Equipment
1. Protocol dropdown → Select **Modbus**
2. Configure: device IP, port `502`, registers `0-10`
3. Connect
4. View register values in real-time

---

## 📝 Dropdown Summary Table

| Dropdown Name | Options | Default | Purpose |
|--------------|---------|---------|---------|
| **Protocol Selector** | MQTT, HTTP, Modbus, Video | MQTT | Choose data source type |
| **Video Stream Type** | mjpeg, rtsp, webcam | mjpeg | Choose video source when Video protocol selected |

---

## 🔗 Related Files

- **Main App:** `app.py`
- **Bridge Script:** `attached_assets/stream_bridge_http_1757249928257.py`
- **Full Documentation:** `README.md`
- **Installation Guide:** `INSTALLATION_GUIDE.md`

---

**Quick Tip:** The HTTP protocol option is specifically designed for Rust server integration. Use it when you have a Rust backend serving data!
