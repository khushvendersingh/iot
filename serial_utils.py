import serial
import serial.tools.list_ports
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common VID/PID combinations for popular IoT boards
KNOWN_DEVICES = {
    'Arduino Uno': {'vid': 0x2341, 'pid': 0x0043},
    'Arduino Mega': {'vid': 0x2341, 'pid': 0x0010},
    'ESP32': {'vid': 0x10C4, 'pid': 0xEA60},  # CP2102
    'ESP32_ALT': {'vid': 0x1A86, 'pid': 0x7523},  # CH340
    'Arduino Nano': {'vid': 0x1A86, 'pid': 0x7523},  # CH340
}

# Handshake command to verify device connectivity
HANDSHAKE_COMMAND = b"PING\n"
HANDSHAKE_RESPONSE = b"PONG"
HANDSHAKE_TIMEOUT = 2  # seconds


class SerialDeviceDetector:
    """Detects and identifies IoT microcontrollers on serial ports"""
    
    @staticmethod
    def list_all_ports():
        """
        Scan and list all available serial ports on the system.
        
        Returns:
            list: List of serial port objects with metadata
        """
        ports = serial.tools.list_ports.comports()
        logger.info(f"Found {len(ports)} serial ports")
        return ports
    
    @staticmethod
    def identify_by_vid_pid(port):
        """
        Identify device by Vendor ID and Product ID.
        
        Args:
            port: Serial port object from list_ports
            
        Returns:
            str or None: Device name if identified, None otherwise
        """
        if port.vid is None or port.pid is None:
            return None
            
        for device_name, ids in KNOWN_DEVICES.items():
            if port.vid == ids['vid'] and port.pid == ids['pid']:
                logger.info(f"Identified {device_name} on {port.device}")
                return device_name
        return None
    
    @staticmethod
    def verify_by_handshake(port_name, baud_rate=115200):
        """
        Verify device by sending a handshake command and checking response.
        
        This method attempts to communicate with the device to confirm
        it's the correct target. Your microcontroller firmware should
        respond to the PING command with PONG.
        
        Args:
            port_name (str): Serial port name (e.g., 'COM3' or '/dev/ttyUSB0')
            baud_rate (int): Baud rate for communication
            
        Returns:
            bool: True if handshake successful, False otherwise
        """
        try:
            with serial.Serial(port_name, baud_rate, timeout=HANDSHAKE_TIMEOUT) as ser:
                # Wait for device to initialize
                time.sleep(0.5)
                
                # Clear any existing data in buffer
                ser.reset_input_buffer()
                
                # Send handshake command
                ser.write(HANDSHAKE_COMMAND)
                time.sleep(0.1)
                
                # Read response
                response = ser.read(len(HANDSHAKE_RESPONSE))
                
                if HANDSHAKE_RESPONSE in response:
                    logger.info(f"Handshake successful on {port_name}")
                    return True
                else:
                    logger.debug(f"Handshake failed on {port_name}, got: {response}")
                    return False
                    
        except (serial.SerialException, OSError) as e:
            logger.debug(f"Cannot handshake with {port_name}: {e}")
            return False
    
    @classmethod
    def detect_device(cls, try_handshake=True):
        """
        Detect the IoT device by scanning ports and identifying the device.
        
        Strategy:
        1. List all available serial ports
        2. Try to identify by VID/PID
        3. Optionally verify with handshake
        
        Args:
            try_handshake (bool): Whether to verify device with handshake
            
        Returns:
            dict: Device information including port name and type, or None
        """
        ports = cls.list_all_ports()
        
        if not ports:
            logger.warning("No serial ports found")
            return None
        
        candidates = []
        
        for port in ports:
            device_type = cls.identify_by_vid_pid(port)
            
            if device_type:
                candidate = {
                    'port': port.device,
                    'device_type': device_type,
                    'description': port.description,
                    'vid': port.vid,
                    'pid': port.pid,
                    'verified': False
                }
                
                # Try handshake verification if enabled
                if try_handshake:
                    candidate['verified'] = cls.verify_by_handshake(port.device)
                else:
                    candidate['verified'] = True
                
                candidates.append(candidate)
        
        # Prefer verified devices
        verified = [c for c in candidates if c['verified']]
        if verified:
            logger.info(f"Found verified device: {verified[0]}")
            return verified[0]
        
        # Fall back to first candidate
        if candidates:
            logger.info(f"Using unverified device: {candidates[0]}")
            return candidates[0]
        
        # No known devices found, try handshake on all ports
        if try_handshake:
            logger.info("No known devices, trying handshake on all ports")
            for port in ports:
                if cls.verify_by_handshake(port.device):
                    return {
                        'port': port.device,
                        'device_type': 'Unknown',
                        'description': port.description,
                        'verified': True
                    }
        
        logger.warning("No suitable device found")
        return None
    
    @classmethod
    def get_all_devices(cls):
        """
        Get all available ports with identification info.
        
        Returns:
            list: List of dictionaries with port information
        """
        ports = cls.list_all_ports()
        devices = []
        
        for port in ports:
            device_type = cls.identify_by_vid_pid(port)
            devices.append({
                'port': port.device,
                'device_type': device_type or 'Unknown',
                'description': port.description,
                'vid': hex(port.vid) if port.vid else 'N/A',
                'pid': hex(port.pid) if port.pid else 'N/A',
            })
        
        return devices


class FirmwareUploader:
    """Handles firmware upload to microcontroller via serial"""
    
    def __init__(self, port, baud_rate=115200):
        """
        Initialize uploader with serial port configuration.
        
        Args:
            port (str): Serial port name
            baud_rate (int): Baud rate for communication
        """
        self.port = port
        self.baud_rate = baud_rate
        self.serial_conn = None
    
    def open_connection(self):
        """Open serial connection to the device"""
        try:
            self.serial_conn = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=5,
                write_timeout=5
            )
            time.sleep(2)  # Wait for device to reset/initialize
            logger.info(f"Opened serial connection to {self.port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            return False
    
    def close_connection(self):
        """Close serial connection"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("Serial connection closed")
    
    def upload_firmware(self, firmware_path, chunk_size=64, progress_callback=None):
        """
        Upload firmware file to microcontroller.
        
        This is a simplified upload that sends the file line by line.
        For actual firmware flashing (e.g., .hex or .bin files), you would
        typically use tools like avrdude (Arduino) or esptool.py (ESP32).
        
        This example demonstrates sending code/data over serial.
        
        Args:
            firmware_path (str): Path to firmware file
            chunk_size (int): Size of data chunks to send
            progress_callback (callable): Optional callback for progress updates
            
        Returns:
            dict: Upload result with success status and message
        """
        if not self.serial_conn or not self.serial_conn.is_open:
            return {
                'success': False,
                'message': 'Serial connection not open'
            }
        
        try:
            with open(firmware_path, 'rb') as f:
                file_size = f.seek(0, 2)  # Get file size
                f.seek(0)  # Reset to start
                
                logger.info(f"Uploading {file_size} bytes from {firmware_path}")
                
                # Clear buffers
                self.serial_conn.reset_input_buffer()
                self.serial_conn.reset_output_buffer()
                
                # Send upload start command (customize for your protocol)
                self.serial_conn.write(b"UPLOAD_START\n")
                time.sleep(0.5)
                
                bytes_sent = 0
                
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    self.serial_conn.write(chunk)
                    bytes_sent += len(chunk)
                    
                    # Call progress callback if provided
                    if progress_callback:
                        progress = int((bytes_sent / file_size) * 100)
                        progress_callback(progress, bytes_sent, file_size)
                    
                    time.sleep(0.01)  # Small delay between chunks
                
                # Send upload complete command
                self.serial_conn.write(b"\nUPLOAD_COMPLETE\n")
                time.sleep(0.5)
                
                # Check for success response
                response = self.serial_conn.read(100)
                
                logger.info(f"Upload complete: {bytes_sent} bytes sent")
                
                return {
                    'success': True,
                    'message': f'Successfully uploaded {bytes_sent} bytes',
                    'bytes_sent': bytes_sent,
                    'response': response.decode('utf-8', errors='ignore')
                }
                
        except FileNotFoundError:
            logger.error(f"Firmware file not found: {firmware_path}")
            return {
                'success': False,
                'message': f'Firmware file not found: {firmware_path}'
            }
        except serial.SerialException as e:
            logger.error(f"Serial error during upload: {e}")
            return {
                'success': False,
                'message': f'Serial communication error: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during upload: {e}")
            return {
                'success': False,
                'message': f'Upload failed: {str(e)}'
            }
