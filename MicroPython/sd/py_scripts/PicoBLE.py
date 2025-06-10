"""
Fixed BLE File Transfer for PicoCalc RP2350
With improved exit handling and clean shutdown
"""

import picocalc
import time
import os
import gc
import struct
from micropython import const

from picocalc import PicoKeyboard   # ← pull in the keyboard API

# create one global keyboard instance
kbd = PicoKeyboard()

# Import necessary BLE modules
try:
    import bluetooth
except ImportError:
    print("Bluetooth module not found")
    raise ImportError("Bluetooth module not found")

# Configuration settings
DEBUG_MODE = True   # Enable for transfer debugging
CHUNK_SIZE = 200    # Maximum BLE packet size for optimal performance
MAX_RETRIES = 5     # Number of retries for operations
ACK_TIMEOUT_MS = 1000  # Timeout for waiting for acknowledgments
FLOW_CONTROL_DELAY_MS = 10  # Delay between chunks to prevent overflow
MAX_PENDING_CHUNKS = 3  # Maximum chunks to send before requiring ACK

# Define constants for BLE operation
def get_device_name():
    mac = bluetooth.BLE().config('mac')[1]
    suffix = ''.join('%02X' % b for b in mac[-2:])
    return f"PicoCalc_{suffix}"

_ADV_INTERVAL_MS = const(250)


# Command codes
CMD_NONE = const(0)
CMD_LIST_DIR = const(1)
CMD_FILE_INFO = const(2)
CMD_FILE_DATA = const(3)
CMD_FILE_END = const(4)
CMD_MKDIR = const(5)
CMD_DELETE = const(6)
CMD_DELETE_DIR = const(7)
CMD_ACK = const(8)  # Acknowledgment command
CMD_NACK = const(9) # Negative acknowledgment
CMD_FLOW_CONTROL = const(10) # Flow control command

# IRQ event codes
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

# UUIDs for the Nordic UART Service (NUS)
_NUS_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_NUS_RX = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")
_NUS_TX = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E")

# Flags for the characteristics
_FLAG_READ = const(0x0002)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)

# Global state
is_connected = False
conn_handle = None
ble = None
services = None
rx_handle = None
tx_handle = None
shutdown_requested = False  # Flag to indicate shutdown

# File transfer state
current_file = None
current_path = ""
bytes_received = 0

# Default upload directory for Python scripts
DEFAULT_SCRIPT_DIR = "/sd/py_scripts"

# Color definitions (4-bit grayscale for PicoCalc display)
COLOR_BLACK = 0
COLOR_DARK_GRAY = 4
COLOR_GRAY = 8
COLOR_LIGHT_GRAY = 12
COLOR_WHITE = 15

# BLE status colors
COLOR_CONNECTED = COLOR_WHITE
COLOR_TRANSFER = COLOR_LIGHT_GRAY
COLOR_SUCCESS = COLOR_WHITE
COLOR_ERROR = COLOR_GRAY

# Activity indicator
activity_dots = 0
activity_color = COLOR_SUCCESS
next_activity_update = 0

# Exit flag for keyboard interrupt
want_exit = False

# artsy bouncing-square + breathing-bar idle indicator
idle_frame = 0
def show_idle():
    global idle_frame
    d = picocalc.display
    if not d or shutdown_requested:
        return
    d.fill(COLOR_BLACK)
    # 1) Bouncing red square across the top
    span = 200
    x = idle_frame % (span * 2)
    if x > span:
        x = 2 * span - x
    d.fill_rect(10 + x, 20, 12, 12, COLOR_LIGHT_GRAY)
    # 2) Breathing cyan bar underneath
    bar_w = ((idle_frame % 20) * 4) + 4
    d.fill_rect(10, 50, bar_w, 4, COLOR_GRAY)
    # 3) Flickering “Ready” text that swaps red/green
    col = COLOR_WHITE if (idle_frame % 10) < 5 else COLOR_LIGHT_GRAY
    d.text("Ready", 10, 100, col)
    d.show()
    idle_frame += 1

def debug_print(message):
    """Print debug messages only if DEBUG_MODE is enabled"""
    if DEBUG_MODE and not shutdown_requested:
        print("[DEBUG] " + message)

def get_activity_indicator():
    """Get activity indicator string"""
    global activity_dots
    if activity_dots == 0:
        return "..."
    elif activity_dots == 1:
        return ". ."
    elif activity_dots == 2:
        return ".. "
    elif activity_dots == 3:
        return ".  "
    else:
        return "  ."

def update_activity():
    """Update activity indicator"""
    global activity_dots, next_activity_update
    now = time.ticks_ms()
    if time.ticks_diff(now, next_activity_update) > 0:
        next_activity_update = now + 200  # Update every 200ms
        activity_dots = (activity_dots + 1) % 4

def update_display(message, color=None, show_activity=False, clear=True):
    """Update display with status message and visual feedback"""
    global activity_color
    
    if not picocalc.display or shutdown_requested:
        return
        
    if clear:
        # Clear display
        picocalc.display.fill(COLOR_BLACK)
    
    # Update activity if needed
    if show_activity:
        update_activity()
    
    # Title with activity indicator
    if show_activity:
        if color:
            activity_color = color
        indicator = get_activity_indicator()
        picocalc.display.text(f"BLE File Transfer {indicator}", 10, 10, activity_color)
    else:
        picocalc.display.text("BLE File Transfer", 10, 10, COLOR_WHITE)
    
    # Split message lines
    if message:
        lines = message.split('\n')
        y = 40
        for line in lines:
            display_color = color if color else COLOR_WHITE
            picocalc.display.text(line, 20, y, display_color)
            y += 20
    
    # Show info
    if is_connected:
        picocalc.display.text("Status: Connected", 10, 240, COLOR_SUCCESS)
    else:
        picocalc.display.text("Status: Waiting for connection", 10, 240, COLOR_TRANSFER)
    
    # Memory info
    free_mem = gc.mem_free()
    picocalc.display.text(f"Memory: {free_mem // 1024}K free", 10, 260, COLOR_GRAY)
    
    # Instructions
    picocalc.display.text("Press ESC to exit", 10, 280, COLOR_ERROR)
    
    # Show the display
    picocalc.display.show()

def update_display_progress():
    """Update display with progress bar"""
    if not picocalc.display or shutdown_requested:
        return
    
    # Clear display
    picocalc.display.fill(COLOR_BLACK)
    
    # Title with activity indicator
    update_activity()
    indicator = get_activity_indicator()
    picocalc.display.text(f"File Transfer {indicator}", 10, 10, COLOR_TRANSFER)
    
    # File info
    filename = current_path.split('/')[-1]
    picocalc.display.text(f"File: {filename[:20]}", 10, 40, COLOR_WHITE)
    picocalc.display.text(f"Bytes: {bytes_received}", 10, 60, COLOR_WHITE)
    
    # Progress bar
    bar_x = 20
    bar_y = 100
    bar_width = 280
    bar_height = 30
    
    # Draw border
    picocalc.display.rect(bar_x, bar_y, bar_width, bar_height, COLOR_WHITE)
    
    # Draw progress (adapt max visual based on file size)
    max_visual = max(100 * 1024, bytes_received * 1.2)  # Dynamic scale based on current size
    progress = min(1.0, bytes_received / max_visual)
    fill_width = int(progress * (bar_width - 4))
    if fill_width > 0:
        picocalc.display.fill_rect(bar_x + 2, bar_y + 2, fill_width, bar_height - 4, COLOR_SUCCESS)
    
    # Progress percentage
    percent = min(100, int(progress * 100))
    picocalc.display.text(f"{percent}%", bar_x + bar_width // 2 - 10, bar_y + bar_height + 10, COLOR_WHITE)
    
    # Memory info
    free_mem = gc.mem_free()
    picocalc.display.text(f"Memory: {free_mem // 1024}K free", 10, 180, COLOR_GRAY)
    
    # Instructions
    picocalc.display.text("Press ESC to cancel", 10, 280, COLOR_ERROR)
    
    # Show target directory
    if current_path.startswith(DEFAULT_SCRIPT_DIR):
        picocalc.display.text("Target: py_scripts", 10, 200, COLOR_SUCCESS)
    
    # Show the display
    picocalc.display.show()

def ensure_directory_exists(path):
    """Ensure all directories in path exist (but not the file itself)"""
    # Extract directory part - everything except the filename
    directory_path = '/'.join(path.split('/')[:-1])
    
    # If no directory part, nothing to create
    if not directory_path or directory_path == path:
        return
    
    # Make sure it starts with /sd
    if not directory_path.startswith("/sd"):
        directory_path = "/sd/" + directory_path.lstrip('/')
    
    # Create directory structure
    parts = directory_path.split('/')
    current = ""
    for part in parts:
        if not part:  # Skip empty parts (like after initial /)
            continue
        
        current = current + "/" + part if current else "/" + part
        
        # Skip if this is sd (already exists)
        if current == "/sd":
            continue
            
        try:
            os.stat(current)  # Check if exists
        except OSError:
            try:
                os.mkdir(current)
                debug_print(f"Created directory: {current}")
            except Exception as e:
                debug_print(f"Error creating directory {current}: {e}")
                raise

def cleanup_transfer():
    """Clean up file transfer state"""
    global current_file, current_path, bytes_received
    
    if current_file:
        try:
            current_file.close()
        except:
            pass
        current_file = None
    
    current_path = ""
    bytes_received = 0
    current_file = None
    
    # Run garbage collection to free memory
    gc.collect()

def send_error_response(command, message=""):
    """Utility function to send error responses"""
    global conn_handle, tx_handle
    
    debug_print(f"Error response for command {command}: {message}")
    response = bytearray([command, 0xFF])  # Error
    try:
        ble.gatts_notify(conn_handle, tx_handle, response)
    except Exception as e:
        debug_print(f"Failed to send error response: {e}")

def list_directory(path):
    """List directory contents"""
    global conn_handle, tx_handle
    
    debug_print(f"Listing directory: {path}")
    
    try:
        # Ensure path starts with /sd
        if not path.startswith("/sd"):
            path = "/sd/" + path.lstrip('/')
            
        # List directory
        contents = os.listdir(path)
        
        # Build response
        response = bytearray([CMD_LIST_DIR])  # Command echo
        
        # Add path
        response.extend(path.encode('utf-8'))
        response.extend(b'\0')  # Null terminator
        
        # Add entries
        for entry in contents:
            # Check if directory
            try:
                full_path = f"{path}/{entry}"
                stat = os.stat(full_path)
                is_dir = (stat[0] & 0x4000) != 0
                size = stat[6]
                
                # Add entry type (1=dir, 0=file)
                response.append(1 if is_dir else 0)
                
                # Add size (4 bytes, little endian)
                response.extend(struct.pack("<I", size))
                
                # Add name
                response.extend(entry.encode('utf-8'))
                response.append(0)  # Null terminator
                
            except Exception as e:
                debug_print(f"Error adding entry {entry}: {e}")
        
        # Send response in chunks
        send_chunked_data(response)
        update_display(f"Listed directory: {path}", color=COLOR_SUCCESS, show_activity=True)
        
    except Exception as e:
        debug_print(f"Error listing directory: {e}")
        send_error_response(CMD_LIST_DIR)

def send_chunked_data(data):
    """Send response in chunks without sequence numbers for non-file transfers"""
    global conn_handle, tx_handle
    
    debug_print(f"Sending {len(data)} bytes in chunks of {CHUNK_SIZE}")
    
    for i in range(0, len(data), CHUNK_SIZE):
        chunk = data[i:i+CHUNK_SIZE]
        retry_count = 0
        
        while retry_count < MAX_RETRIES:
            try:
                debug_print(f"Sending chunk {i//CHUNK_SIZE + 1}/{(len(data) + CHUNK_SIZE - 1)//CHUNK_SIZE}")
                ble.gatts_notify(conn_handle, tx_handle, chunk)
                # Small delay between chunks
                time.sleep_ms(10)
                break  # Success, exit retry loop
            except Exception as e:
                retry_count += 1
                debug_print(f"Error sending chunk (attempt {retry_count}): {e}")
                if retry_count >= MAX_RETRIES:
                    debug_print("Max retries exceeded, giving up")
                    return
                time.sleep_ms(100 * retry_count)  # Exponential backoff

def start_file_transfer(path):
    """Start receiving a file"""
    global current_file, current_path, bytes_received, conn_handle, tx_handle
    
    # If path is just a filename (no directory), use default script directory
    if '/' not in path or path.startswith('/'):
        # Extract just the filename
        filename = path.split('/')[-1] if '/' in path else path
        # Use default directory
        path = f"{DEFAULT_SCRIPT_DIR}/{filename}"
        debug_print(f"Using default directory: {DEFAULT_SCRIPT_DIR}")
    
    debug_print(f"Starting file transfer to: {path}")

    try:
        # Check if a transfer is already in progress
        if current_file:
            debug_print(f"Error: Transfer already in progress with {current_file} and {path}")
            send_error_response(CMD_FILE_INFO, "Transfer already in progress")
            return
        
        # Ensure path starts with /sd
        if not path.startswith("/sd"):
            path = "/sd/" + path.lstrip('/')
        
        # Check for existing file/directory and handle appropriately
        try:
            stat_result = os.stat(path)
            is_dir = (stat_result[0] & 0x4000) != 0
            
            if is_dir:
                debug_print(f"Error: Path exists as directory: {path}")
                send_error_response(CMD_FILE_INFO, "Path is a directory")
                return
            else:
                file_size = stat_result[6]  # Size is at index 6
                debug_print(f"Found existing file: {path}, size: {file_size} bytes")
                try:
                    os.remove(path)
                    debug_print(f"Successfully removed existing file: {path}")
                except OSError as e:
                    debug_print(f"Could not remove existing file ({e}), continuing...")
        except OSError:
            debug_print(f"No existing file at {path}")
            
        # Ensure directory exists
        ensure_directory_exists(path)
        
        # Open file for writing
        current_file = open(path, "wb")
        current_path = path
        bytes_received = 0
        
        # Send response
        response = bytearray([CMD_FILE_INFO, 0])  # Success
        ble.gatts_notify(conn_handle, tx_handle, response)
        
        update_display(f"Receiving file:\n{path.split('/')[-1]}", color=COLOR_TRANSFER, show_activity=True)
        
    except Exception as e:
        debug_print(f"Error starting file transfer: {e}")
        cleanup_transfer()
        send_error_response(CMD_FILE_INFO)

def receive_file_data(data):
    """Receive a chunk of file data"""
    global current_file, bytes_received, conn_handle, tx_handle
    
    try:
        if not current_file:
            debug_print("Error: No file transfer in progress")
            send_error_response(CMD_FILE_DATA)
            return
            
        # Write data to file (no sequence extraction for now)
        bytes_written = current_file.write(data)
        current_file.flush()  # Force write to storage immediately
        bytes_received += len(data)
        
        debug_print(f"Received {len(data)} bytes, wrote {bytes_written}, total: {bytes_received}")
        
        # Send simple ACK response
        response = bytearray([CMD_FILE_DATA, 0])  # Success
        ble.gatts_notify(conn_handle, tx_handle, response)
        
        # Update display periodically (less frequently for better performance)
        if bytes_received % (CHUNK_SIZE * 10) == 0:  # Update every ~2400 bytes
            update_display_progress()
            
    except Exception as e:
        debug_print(f"Error receiving file data: {e}")
        send_error_response(CMD_FILE_DATA)
        cleanup_transfer()

def end_file_transfer(original_filename_data=b''):
    """End file transfer and optionally rename to original filename"""
    global current_file, current_path, bytes_received, conn_handle, tx_handle
    
    try:
        if not current_file:
            debug_print("Error: No file transfer in progress")
            send_error_response(CMD_FILE_END)
            return
            
        # Close file
        current_file.close()
        
        # Handle rename if original filename provided
        final_path = current_path
        if original_filename_data:
            try:
                original_filename = original_filename_data.decode('utf-8')
                # Get directory from current path
                directory = '/'.join(current_path.split('/')[:-1])
                new_path = f"{directory}/{original_filename}"
                
                debug_print(f"Renaming {current_path} to {new_path}")
                
                # Remove existing file with same name if it exists
                try:
                    os.remove(new_path)
                    debug_print(f"Removed existing file: {new_path}")
                except OSError:
                    pass  # File doesn't exist, which is fine
                
                # Rename the file
                os.rename(current_path, new_path)
                final_path = new_path
                debug_print(f"File renamed to original filename: {original_filename}")
                
            except Exception as e:
                debug_print(f"Warning: Could not rename to original filename: {e}")
                # Continue with temp filename
        
        # Send response
        response = bytearray([CMD_FILE_END, 0])  # Success
        response.extend(struct.pack("<I", bytes_received))  # Total bytes
        ble.gatts_notify(conn_handle, tx_handle, response)
        
        debug_print(f"Transfer complete: {bytes_received} bytes")
        # Show full path if not in default directory, otherwise just filename
        display_path = final_path
        if final_path.startswith(DEFAULT_SCRIPT_DIR):
            display_path = final_path.split('/')[-1]
        
        update_display(f"Transfer complete:\n{display_path}\n{bytes_received} bytes", color=COLOR_SUCCESS, show_activity=False)
        
        # Clean up
        cleanup_transfer()
        
    except Exception as e:
        debug_print(f"Error ending transfer: {e}")
        send_error_response(CMD_FILE_END)
        cleanup_transfer()

def make_directory(path):
    """Create a directory"""
    global conn_handle, tx_handle
    
    debug_print(f"Creating directory: {path}")
    
    try:
        # Ensure path starts with /sd
        if not path.startswith("/sd"):
            path = "/sd/" + path.lstrip('/')
            
        # Create directory
        ensure_directory_exists(path)
        
        # Send response
        response = bytearray([CMD_MKDIR, 0])  # Success
        ble.gatts_notify(conn_handle, tx_handle, response)
        
        update_display(f"Created directory: {path}", color=COLOR_SUCCESS, show_activity=True)
        
    except Exception as e:
        debug_print(f"Error creating directory: {e}")
        send_error_response(CMD_MKDIR)

def delete_directory(path):
    """Delete a directory recursively"""
    global conn_handle, tx_handle
    
    debug_print(f"Deleting directory: {path}")
    
    try:
        # Ensure path starts with /sd
        if not path.startswith("/sd"):
            path = "/sd/" + path.lstrip('/')
            
        # Remove directory recursively
        import os
        def rmdir_recursive(directory):
            for file in os.listdir(directory):
                full_path = directory + "/" + file
                stat = os.stat(full_path)
                if stat[0] & 0x4000:  # Directory
                    rmdir_recursive(full_path)
                else:  # File
                    os.remove(full_path)
            os.rmdir(directory)
        
        rmdir_recursive(path)
        
        # Send response
        response = bytearray([CMD_DELETE_DIR, 0])  # Success
        ble.gatts_notify(conn_handle, tx_handle, response)
        
        update_display(f"Deleted directory: {path}", color=COLOR_ERROR, show_activity=True)
        
    except Exception as e:
        debug_print(f"Error deleting directory: {e}")
        send_error_response(CMD_DELETE_DIR)

def delete_file(path):
    """Delete a file"""
    global conn_handle, tx_handle
    
    debug_print(f"Deleting file: {path}")
    
    try:
        # Ensure path starts with /sd
        if not path.startswith("/sd"):
            path = "/sd/" + path.lstrip('/')
        
        # Check if path exists and is a file
        try:
            stat_result = os.stat(path)
            is_dir = (stat_result[0] & 0x4000) != 0
            
            if is_dir:
                debug_print(f"Error: Path is a directory, not a file: {path}")
                send_error_response(CMD_DELETE, "Path is a directory")
                return
        except OSError:
            debug_print(f"Error: File not found: {path}")
            send_error_response(CMD_DELETE, "File not found")
            return
            
        # Delete file
        os.remove(path)
        
        # Send response
        response = bytearray([CMD_DELETE, 0])  # Success
        ble.gatts_notify(conn_handle, tx_handle, response)
        
        update_display(f"Deleted file: {path}", color=COLOR_ERROR, show_activity=True)
        
    except Exception as e:
        debug_print(f"Error deleting file: {e}")
        send_error_response(CMD_DELETE)

def ble_irq(event, data):
    """Handle BLE IRQ events"""
    global is_connected, conn_handle, ble, rx_handle, shutdown_requested
    
    # Ignore events during shutdown
    if shutdown_requested:
        return
        
    debug_print(f"BLE event: {event}, data: {data}")
    
    if event == _IRQ_CENTRAL_CONNECT:
        # Store just the first value as conn_handle
        conn_handle = data[0]  # This should work regardless of tuple structure
        is_connected = True
        debug_print(f"Connected, handle: {conn_handle}")
        update_display(f"Connected", color=COLOR_SUCCESS, show_activity=False)
        
    elif event == _IRQ_CENTRAL_DISCONNECT:
        is_connected = False
        debug_print("Disconnected")
        cleanup_transfer()
        update_display("Disconnected. Ready.", color=COLOR_TRANSFER, show_activity=False)
        
        # Only restart advertising if not shutting down
        if not shutdown_requested:
            try:
                debug_print("Restarting advertising")
                ble.gap_advertise(100000, adv_data=get_adv_payload(device_name))
            except Exception as e:
                debug_print(f"Failed to restart advertising: {e}")
        
    elif event == _IRQ_GATTS_WRITE:
        # Handle a client write to a characteristic
        if len(data) >= 2:  # Ensure we have at least 2 items in data
            value_handle = data[1]
            debug_print(f"Write to handle: {value_handle}, rx_handle: {rx_handle}")
            
            # Check if the write is to the RX characteristic
            if value_handle == rx_handle:
                # Read the data
                data_bytes = ble.gatts_read(rx_handle)
                if data_bytes and len(data_bytes) > 0:
                    debug_print(f"Received data: {bytes(data_bytes).hex()}")
                    process_command(data_bytes)

def process_command(data):
    """Process incoming command"""
    if not data or len(data) < 1 or shutdown_requested:
        return
        
    # First byte is the command
    command = data[0]
    debug_print(f"Processing command: {command}")
    
    # Process commands
    if command == CMD_LIST_DIR:
        # List directory
        if len(data) > 1:
            path = data[1:].decode('utf-8')
            list_directory(path)
        else:
            # Default to py_scripts directory
            list_directory(DEFAULT_SCRIPT_DIR)
            
    elif command == CMD_FILE_INFO:
        # Start file transfer
        if len(data) > 1:
            path = data[1:].decode('utf-8')
            start_file_transfer(path)
            
    elif command == CMD_FILE_DATA:
        # File data chunk
        if len(data) > 1:
            receive_file_data(data[1:])
            
    elif command == CMD_FILE_END:
        # End file transfer
        if len(data) > 1:
            # Original filename provided for rename
            original_filename_data = data[1:]
            end_file_transfer(original_filename_data)
        else:
            # No original filename provided
            end_file_transfer()
            
    elif command == CMD_MKDIR:
        # Make directory
        if len(data) > 1:
            path = data[1:].decode('utf-8')
            make_directory(path)
            
    elif command == CMD_DELETE:
        # Delete file
        if len(data) > 1:
            path = data[1:].decode('utf-8')
            delete_file(path)
            
    elif command == CMD_DELETE_DIR:
        # Delete directory
        if len(data) > 1:
            path = data[1:].decode('utf-8')
            delete_directory(path)
    else:
        debug_print(f"Unknown command: {command}")

def get_adv_payload(name):
    """Generate a BLE advertisement payload for the Nordic UART Service"""
    # Helper function for simple advertising
    def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
        payload = bytearray()

        def _append(adv_type, value):
            nonlocal payload
            payload += struct.pack("BB", len(value) + 1, adv_type) + value

        _append(0x01, struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)))

        if name:
            _append(0x09, name.encode())

        if services:
            for uuid in services:
                b = bytes(uuid)
                if len(b) == 2:
                    _append(0x02, b)
                elif len(b) == 4:
                    _append(0x04, b)
                elif len(b) == 16:
                    _append(0x06, b)

        if appearance:
            _append(0x19, struct.pack("<h", appearance))

        return payload
    
    return advertising_payload(name=name, services=[_NUS_UUID])

def check_sd_card():
    """Check if SD card is properly mounted"""
    try:
        os.stat("/sd")
        return True
    except OSError:
        return False

def init_bluetooth():
    """Initialize Bluetooth with the Nordic UART Service"""
    global ble, rx_handle, tx_handle
    
    try:
        debug_print("Initializing Bluetooth...")
        
        # Create BLE instance
        ble = bluetooth.BLE()
        ble.active(True)
        global device_name
        # Dynamically generate device name from MAC address
        mac = ble.config('mac')[1]
        suffix = ''.join('%02X' % b for b in mac[-2:])
        device_name = f"PicoCalc_{suffix}"
        ble.config(gap_name=device_name)

        
        # Register services
        # Nordic UART Service (NUS)
        rx_char = (_NUS_RX, _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
        tx_char = (_NUS_TX, _FLAG_NOTIFY)
        nus = (_NUS_UUID, (tx_char, rx_char))
        
        # Register service
        services = (nus,)
        
        try:
            # This is the standard way to register services
            ((tx_handle, rx_handle),) = ble.gatts_register_services(services)
            debug_print(f"Services registered: TX handle: {tx_handle}, RX handle: {rx_handle}")
        except Exception as e:
            debug_print(f"Error registering services: {e}")
            raise
        
        # Set up BLE event handler
        ble.irq(ble_irq)
        
        # Start advertising
        try:
            # This is the standard way to advertise
            ble.gap_advertise(100000, adv_data=get_adv_payload(device_name))
            debug_print(f"Advertising as {device_name}")
        except Exception as e:
            debug_print(f"Error starting advertising: {e}")
            raise
        
        return True
        
    except Exception as e:
        debug_print(f"Error initializing Bluetooth: {e}")
        return False

def check_keyboard_exit():
    """
    Poll the PicoCalc’s keyboard for an ESC press.
    Uses the PicoKeyboard.readinto() API to grab raw bytes.
    """
    try:
        buf = bytearray(1)
        n = kbd.readinto(buf)              # readinto returns number of bytes read
        if n and buf[0] == 27:             # 27 == ESC
            return True
    except Exception as e:
        debug_print(f"Keyboard check error: {e}")
        # if this still fails, dump the available API so you can pick the right one:
        debug_print(f"Available PicoKeyboard methods: {dir(kbd)}")
    return False

def check_for_exit():
    """Check for ESC to exit"""
    global want_exit
    
    # If some other part of the code already flagged exit, honour it
    if want_exit:
        return True

    # Otherwise poll the keyboard
    if check_keyboard_exit():
        want_exit = True
        return True

    return False

def main():
    """Main function with improved exit handling"""
    global shutdown_requested, want_exit
    
    # Force garbage collection before starting
    gc.collect()
    
    # Initialize want_exit flag
    want_exit = False
    
    # Check if SD card is mounted
    if not check_sd_card():
        print("ERROR: SD card not mounted at /sd.")
        print("Please ensure SD card is properly inserted.")
        if picocalc.display:
            picocalc.display.fill(0)
            picocalc.display.text("ERROR: SD card not mounted", 10, 10, 0xF800)  # Red
            picocalc.display.text("Insert SD card and restart", 10, 30, 0xF800)
            picocalc.display.show()
        time.sleep(3)
        return
    
    try:
        # Print memory information
        free = gc.mem_free()
        if DEBUG_MODE:
            print(f"Free memory: {free} bytes")
        
        # Initialize Bluetooth
        if not init_bluetooth():
            print("Failed to initialize Bluetooth")
            return
            
        # Update display
        update_display("Ready for connection", color=0x001F)

        if DEBUG_MODE:
            print("BLE File Transfer running.")
            print("Press ESC to exit.")
        
        try:
            # Main loop - wait for ESC to exit
            while not shutdown_requested:
                # Check for exit conditions
                if check_for_exit():
                    print("\nExit requested - Shutting down...")
                    shutdown_requested = True
                    break
                
                # Brief delay to prevent tight loop
                time.sleep_ms(50)
                
                # Update display periodically
                if is_connected and not current_file:
                    update_display("Connected", color=0x07E0, show_activity=True)
                elif not is_connected:
                    show_idle()
                
                # Periodic memory cleanup to prevent fragmentation
                if not is_connected and not current_file:
                    gc.collect()
        
        except KeyboardInterrupt:
            print("\nKeyboard interrupt detected")
            shutdown_requested = True
            want_exit = True
        except Exception as e:
            print(f"\nMain loop error: {e}")
            shutdown_requested = True
        
        # Shutdown sequence
        shutdown_requested = True
        print("Shutting down...")
        
        # Clean up - stop processing new commands
        cleanup_transfer()
        
        # Stop BLE properly
        if ble:
            try:
                # Disconnect any active connection
                if is_connected and conn_handle:
                    try:
                        ble.gap_disconnect(conn_handle)
                    except:
                        pass
                
                # Disable BLE
                ble.active(False)
                print("Bluetooth stopped")
            except Exception as e:
                print(f"Error stopping Bluetooth: {e}")
        
        # Clear display
        if picocalc.display:
            picocalc.display.fill(0)
            picocalc.display.text("BLE Service Stopped", 10, 10, 0xF800)  # Red
            picocalc.display.text("Exiting...", 10, 40, 1)
            picocalc.display.show()
            time.sleep(1)
            
        print("Exit complete")
        
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.print_exception(e)
        if picocalc.display:
            picocalc.display.fill(0)
            picocalc.display.text("Error occurred", 10, 10, 0xF800)
            picocalc.display.text("Check console", 10, 40, 1)
            picocalc.display.show()
            time.sleep(3)

# For direct execution
if __name__ == "__main__":
    main()