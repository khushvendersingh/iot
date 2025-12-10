import streamlit as st
import os
from serial_utils import SerialDeviceDetector, FirmwareUploader

# Page configuration
st.set_page_config(
    page_title="IoT Device Firmware Uploader",
    page_icon="🔌",
    layout="wide"
)

# Initialize session state
if 'detected_device' not in st.session_state:
    st.session_state.detected_device = None
if 'upload_result' not in st.session_state:
    st.session_state.upload_result = None

# Title and description
st.title("🔌 IoT Device Firmware Uploader")
st.markdown("""
This application helps you detect and upload firmware to IoT microcontrollers 
(Arduino, ESP32, etc.) connected via serial/USB ports.
""")

# Sidebar for settings
st.sidebar.header("⚙️ Settings")
baud_rate = st.sidebar.selectbox(
    "Baud Rate",
    [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600],
    index=4  # Default to 115200
)

enable_handshake = st.sidebar.checkbox(
    "Enable Handshake Verification",
    value=True,
    help="Send PING command to verify device (requires firmware support)"
)

chunk_size = st.sidebar.slider(
    "Upload Chunk Size (bytes)",
    min_value=16,
    max_value=512,
    value=64,
    step=16
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
### 📝 Notes
- Your microcontroller should respond to `PING` with `PONG`
- Upload protocol: `UPLOAD_START`, data chunks, `UPLOAD_COMPLETE`
- For actual firmware flashing, use avrdude or esptool
""")

# Main content area with tabs
tab1, tab2, tab3 = st.tabs(["🔍 Detect Device", "📤 Upload Firmware", "📋 All Ports"])

# ============================================================================
# TAB 1: DETECT DEVICE
# ============================================================================
with tab1:
    st.header("Device Detection")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        if st.button("🔍 Scan for Devices", use_container_width=True):
            with st.spinner("Scanning serial ports..."):
                device = SerialDeviceDetector.detect_device(try_handshake=enable_handshake)
                st.session_state.detected_device = device
    
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.session_state.detected_device = None
            st.rerun()
    
    st.markdown("---")
    
    # Display detected device
    if st.session_state.detected_device:
        device = st.session_state.detected_device
        
        st.success("✅ Device Detected!")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Port", device['port'])
        
        with col2:
            st.metric("Device Type", device['device_type'])
        
        with col3:
            verified_status = "✅ Verified" if device.get('verified') else "⚠️ Not Verified"
            st.metric("Status", verified_status)
        
        # Device details
        with st.expander("📊 Device Details"):
            st.json(device)
    
    elif st.session_state.detected_device is None:
        st.info("👆 Click 'Scan for Devices' to detect connected microcontrollers")
    else:
        st.error("❌ No compatible device found. Please check your connection.")

# ============================================================================
# TAB 2: UPLOAD FIRMWARE
# ============================================================================
with tab2:
    st.header("Firmware Upload")
    
    # Port selection
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Option to use detected device or manual selection
        use_detected = st.checkbox(
            "Use Auto-Detected Device",
            value=True,
            disabled=st.session_state.detected_device is None
        )
        
        if use_detected and st.session_state.detected_device:
            selected_port = st.session_state.detected_device['port']
            st.info(f"Using detected port: **{selected_port}**")
        else:
            # Get all available ports for manual selection
            all_devices = SerialDeviceDetector.get_all_devices()
            if all_devices:
                port_options = [f"{d['port']} - {d['device_type']}" for d in all_devices]
                selected_option = st.selectbox("Select Port", port_options)
                selected_port = selected_option.split(' - ')[0]
            else:
                st.warning("No serial ports found")
                selected_port = None
    
    with col2:
        st.metric("Baud Rate", f"{baud_rate}")
    
    st.markdown("---")
    
    # File upload
    uploaded_file = st.file_uploader(
        "Choose firmware file",
        type=['hex', 'bin', 'ino', 'txt'],
        help="Upload your firmware file (.hex, .bin, etc.)"
    )
    
    # Alternative: file path input
    use_file_path = st.checkbox("Or specify file path manually")
    if use_file_path:
        firmware_path = st.text_input(
            "Firmware File Path",
            placeholder="/path/to/firmware.hex"
        )
    else:
        firmware_path = None
    
    st.markdown("---")
    
    # Upload button
    if st.button("📤 Upload Firmware", type="primary", use_container_width=True):
        
        # Validate port selection
        if not selected_port:
            st.error("❌ No port selected. Please detect a device or select manually.")
        else:
            # Handle file source
            if uploaded_file:
                # Save uploaded file temporarily
                temp_path = f"temp_{uploaded_file.name}"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                file_to_upload = temp_path
            elif firmware_path and os.path.exists(firmware_path):
                file_to_upload = firmware_path
            else:
                st.error("❌ Please upload a file or specify a valid file path.")
                file_to_upload = None
            
            if file_to_upload:
                # Create progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(progress, bytes_sent, total_bytes):
                    progress_bar.progress(progress)
                    status_text.text(f"Uploading: {bytes_sent}/{total_bytes} bytes ({progress}%)")
                
                # Upload firmware
                with st.spinner(f"Connecting to {selected_port}..."):
                    uploader = FirmwareUploader(selected_port, baud_rate)
                    
                    if uploader.open_connection():
                        try:
                            result = uploader.upload_firmware(
                                file_to_upload,
                                chunk_size=chunk_size,
                                progress_callback=update_progress
                            )
                            st.session_state.upload_result = result
                        finally:
                            uploader.close_connection()
                            # Clean up temporary file
                            if uploaded_file and os.path.exists(temp_path):
                                os.remove(temp_path)
                    else:
                        st.error(f"❌ Failed to connect to {selected_port}")
                        st.session_state.upload_result = {
                            'success': False,
                            'message': f'Could not open port {selected_port}'
                        }
    
    # Display upload result
    if st.session_state.upload_result:
        result = st.session_state.upload_result
        
        st.markdown("---")
        st.subheader("Upload Result")
        
        if result['success']:
            st.success(f"✅ {result['message']}")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Bytes Sent", result.get('bytes_sent', 'N/A'))
            with col2:
                st.metric("Status", "Success")
            
            if result.get('response'):
                with st.expander("📨 Device Response"):
                    st.code(result['response'])
        else:
            st.error(f"❌ {result['message']}")

# ============================================================================
# TAB 3: ALL PORTS
# ============================================================================
with tab3:
    st.header("All Available Serial Ports")
    
    if st.button("🔄 Refresh Port List", use_container_width=True):
        st.rerun()
    
    st.markdown("---")
    
    # Get and display all ports
    all_devices = SerialDeviceDetector.get_all_devices()
    
    if all_devices:
        st.success(f"Found {len(all_devices)} serial port(s)")
        
        # Display as table
        import pandas as pd
        df = pd.DataFrame(all_devices)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Display detailed cards
        st.markdown("### Port Details")
        for idx, device in enumerate(all_devices):
            with st.expander(f"📍 {device['port']} - {device['device_type']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Port:** {device['port']}")
                    st.write(f"**Device Type:** {device['device_type']}")
                    st.write(f"**Description:** {device['description']}")
                with col2:
                    st.write(f"**VID:** {device['vid']}")
                    st.write(f"**PID:** {device['pid']}")
    else:
        st.warning("⚠️ No serial ports found. Please connect a device.")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray;'>
    <small>IoT Device Firmware Uploader | Built with Streamlit & PySerial</small>
</div>
""", unsafe_allow_html=True)


# ============================================================================
# USAGE INSTRUCTIONS (as comment)
# ============================================================================

"""
SETUP AND USAGE:

1. Install dependencies:
   pip install -r requirements.txt

2. Create file structure:
   - app.py (main Streamlit app)
   - serial_utils.py (utility classes)
   - requirements.txt

3. Run the application:
   streamlit run app.py

4. Use the web interface:
   - Tab 1: Detect and identify connected devices
   - Tab 2: Upload firmware files to the device
   - Tab 3: View all available serial ports

5. Microcontroller firmware requirements:
   - Respond to PING command with PONG
   - Handle UPLOAD_START, data chunks, and UPLOAD_COMPLETE
   
6. For actual firmware flashing:
   - Arduino: Use avrdude command-line tool
   - ESP32: Use esptool.py
   - This app demonstrates serial data transfer
"""
