@echo off
:: Check for admin privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo Starting Streamlit Application on port 5001...
echo.
echo The browser will open automatically in 10 seconds...
echo.
echo Installing Python dependencies...
echo.

python -m pip install --user streamlit plotly scikit-learn pandas numpy joblib paho-mqtt pymodbustcp requests streamlit-webrtc opencv-python av

echo.
echo Configuring Windows Firewall for rust-app...
netsh advfirewall firewall delete rule name="Rust App - Htier" >nul 2>&1
netsh advfirewall firewall add rule name="Rust App - Htier" dir=in action=allow program="%~dp0RUST\debug\rust-app.exe" enable=yes profile=any
echo Firewall rule added successfully!
echo.

echo Starting rust-app.exe...
start  "" %~dp0RUST\debug\rust-app.exe

echo Running Streamlit App!
start "Streamlit App" python -m streamlit run "%~dp0HtierApp\app.py" --server.port 5001

timeout /t 10 /nobreak

start http://localhost:5001