"""
Enhanced BLE Client for PicoCalc
Modified to work with multiple PicoCalc devices and supports both MAC and UUID device identifiers
Updated to fix Bleak deprecation warnings
"""

import asyncio
import os
import sys
import struct
import time
from pathlib import Path
import platform
from typing import Optional, List, Dict, Any, Tuple
import json
import re

try:
    from bleak import BleakClient, BleakScanner
    from bleak.exc import BleakError
    import bleak
except ImportError:
    print("Error: 'bleak' library not found.")
    print("Please install it using: pip install bleak")
    sys.exit(1)

# Default device name patterns to look for
DEVICE_NAME_PATTERNS = ["PicoCalc", "PicoCalc-BLE", "PicoCalc-Test"]

# UUIDs for Nordic UART Service
_NUS_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
_NUS_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
_NUS_TX = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# Command codes (must match server)
CMD_NONE = 0
CMD_LIST_DIR = 1
CMD_FILE_INFO = 2
CMD_FILE_DATA = 3
CMD_FILE_END = 4
CMD_MKDIR = 5
CMD_DELETE = 6
CMD_DELETE_DIR = 7  # Command for directory deletion

# Chunk size for file transfer
CHUNK_SIZE = 20  # Match server chunk size
MAX_DEST_PATH_LENGTH = 64

# Config file for storing device preferences
CONFIG_FILE = "picocalc_client_config.json"

class DeviceInfo:
    """Class to store device information"""
    def __init__(self, address: str, name: str = "Unknown", rssi: int = 0, uuids: List[str] = None):
        self.address = address
        self.name = name
        self.rssi = rssi
        self.uuids = uuids or []
        self.last_connected = 0  # Timestamp of last connection
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "address": self.address,
            "name": self.name,
            "rssi": self.rssi,
            "uuids": self.uuids,
            "last_connected": self.last_connected
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeviceInfo':
        """Create from dictionary"""
        device = cls(
            address=data["address"],
            name=data.get("name", "Unknown"),
            rssi=data.get("rssi", 0),
            uuids=data.get("uuids", [])
        )
        device.last_connected = data.get("last_connected", 0)
        return device
    
def get_safe_filename(original_filename, max_length=6):
    """
    Create a safe filename that won't exceed the BLE packet limits
    - Preserves the file extension
    - Shortens the name part if needed
    - Returns a filename that's safe to use
    """
    # Split the filename and extension
    if '.' in original_filename:
        name_part, ext_part = original_filename.rsplit('.', 1)
        ext_part = '.' + ext_part  # Add the dot back
    else:
        name_part = original_filename
        ext_part = ""
    
    # Calculate available length for the name part
    # Allow space for the extension plus a separator
    available_length = max_length - len(ext_part)
    
    # If the name is already short enough, use it as is
    if len(name_part) <= available_length:
        return original_filename
    
    # Otherwise, truncate the name part
    # Options:
    # 1. Simple truncation:
    shortened_name = name_part[:available_length]
    
    # 2. Or use a middle ellipsis approach:
    # half_length = (available_length - 3) // 2  # -3 for the "..."
    # shortened_name = name_part[:half_length] + "..." + name_part[-half_length:]
    
    return shortened_name + ext_part

class EnhancedBLEClient:
    def __init__(self):
        self.client = None
        self.device = None
        self.device_address = None
        self.current_path = "/sd"
        self.response_buffer = bytearray()
        self.response_event = asyncio.Event()
        self.last_cmd = CMD_NONE
        self.verbose = False  # Enable verbose logging
        self.known_devices = self.load_known_devices()
        self.scan_timeout = 15.0  # Scan timeout in seconds
        
    def load_known_devices(self) -> Dict[str, DeviceInfo]:
        """Load known devices from config file"""
        devices = {}
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    for addr, dev_data in data.items():
                        devices[addr] = DeviceInfo.from_dict(dev_data)
                print(f"Loaded {len(devices)} known devices from config")
        except Exception as e:
            print(f"Error loading known devices: {e}")
        return devices
    
    def save_known_devices(self):
        """Save known devices to config file"""
        try:
            data = {addr: dev.to_dict() for addr, dev in self.known_devices.items()}
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved {len(self.known_devices)} known devices to config")
        except Exception as e:
            print(f"Error saving known devices: {e}")
            
    def add_known_device(self, device: DeviceInfo):
        """Add or update a known device"""
        self.known_devices[device.address] = device
        self.save_known_devices()
    
    def is_valid_uuid(self, address: str) -> bool:
        """Check if the address is a valid UUID"""
        # Simple UUID pattern check (8-4-4-4-12 hex digits)
        uuid_pattern = re.compile(r'^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$', re.IGNORECASE)
        return bool(uuid_pattern.match(address))
    
    def is_valid_mac(self, address: str) -> bool:
        """Check if the address is a valid MAC address"""
        # MAC address pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
        mac_pattern = re.compile(r'^([0-9A-F]{2}[:-]){5}([0-9A-F]{2})$', re.IGNORECASE)
        return bool(mac_pattern.match(address))
    
    def is_valid_address(self, address: str) -> bool:
        """Check if the address is valid (either MAC or UUID)"""
        return self.is_valid_mac(address) or self.is_valid_uuid(address)
    
    async def scan_for_specific_device(self, address: str) -> Optional[bleak.BLEDevice]:
        """Scan for a specific device by address"""
        print(f"Looking for device with address: {address}")
        try:
            # For UUID format identifiers, we need a different approach
            if self.is_valid_uuid(address):
                # Scan for all devices and find the one with matching UUID
                devices_with_adverts = []
                def _device_detection_callback(device, advertisement_data):
                    devices_with_adverts.append((device, advertisement_data))
                
                scanner = BleakScanner(detection_callback=_device_detection_callback)
                await scanner.start()
                await asyncio.sleep(3.0)  # Scan for 5 seconds
                await scanner.stop()
                
                for device, adv_data in devices_with_adverts:
                    if device.address.upper() == address.upper():
                        return device
                    
                    # Check service UUIDs
                    if hasattr(adv_data, 'service_uuids'):
                        if any(address.upper() in str(uuid).upper() for uuid in adv_data.service_uuids):
                            return device
                return None
            else:
                # Standard MAC address lookup
                return await BleakScanner.find_device_by_address(address, timeout=10.0)
        except Exception as e:
            print(f"Error scanning for specific device: {e}")
            return None
    
    async def extended_scan(self) -> Optional[str]:
            """Perform enhanced scanning with device deduplication"""
            print("Starting Bluetooth scan...")
            print(f"Running on: {platform.system()} {platform.release()}")
            
            # Initialize choice variable
            choice = ""
            
            # Handle recent devices first
            if self.known_devices:
                # Sort known devices by last connection time (most recent first)
                recent_devices = sorted(
                    self.known_devices.values(), 
                    key=lambda d: d.last_connected, 
                    reverse=True
                )
                
                print("\nRecently connected devices:")
                for i, device in enumerate(recent_devices[:5]):  # Show up to 5 recent devices
                    # Calculate time since last connection
                    time_ago = "Never" if device.last_connected == 0 else self.get_time_ago(device.last_connected)
                    print(f"{i+1}. {device.name} - {device.address} (Last used: {time_ago})")
                    
                choice = input("Connect to a recent device? (enter number, or 's' to scan, or 'c' for custom address): ")
                
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(recent_devices):
                        # Try to find the device
                        device = await self.scan_for_specific_device(recent_devices[idx].address)
                        if device:
                            print(f"Found device: {device.name or 'Unknown'} ({device.address})")
                            self.device = device
                            self.device_address = device.address
                            return device.address
                        else:
                            print(f"Device {recent_devices[idx].name} not found. Proceeding to full scan.")
                elif choice.lower() == 'c':
                    custom_addr = input("Enter the device address (MAC or UUID): ")
                    if custom_addr:
                        self.device_address = custom_addr
                        return custom_addr
                        
            # Perform full scan
            if choice.lower() != 's' and choice.lower() != 'c' and not choice.isdigit():
                print("\nPerforming full scan for PicoCalc devices...")
            
            # Perform full scan
            try:
                print(f"Scanning for Bluetooth devices ({self.scan_timeout}s)...")
                
                # Dictionary to store unique devices by address
                discovered_devices = {}
                
                def _device_detection_callback(device, advertisement_data):
                    # Keep track of signal strength and update if stronger signal found
                    if device.address not in discovered_devices:
                        discovered_devices[device.address] = {
                            'device': device,
                            'adv_data': advertisement_data,
                            'best_rssi': advertisement_data.rssi if hasattr(advertisement_data, 'rssi') else 0,
                            'scan_count': 1
                        }
                    else:
                        # Update best RSSI if this signal is stronger
                        current_rssi = advertisement_data.rssi if hasattr(advertisement_data, 'rssi') else 0
                        if current_rssi > discovered_devices[device.address]['best_rssi']:
                            discovered_devices[device.address]['best_rssi'] = current_rssi
                            discovered_devices[device.address]['adv_data'] = advertisement_data
                        discovered_devices[device.address]['scan_count'] += 1
                
                scanner = BleakScanner(detection_callback=_device_detection_callback)
                await scanner.start()
                await asyncio.sleep(self.scan_timeout)
                await scanner.stop()
                
                # Group devices by relevance
                picocalc_devices = []  # Exact matches to any PicoCalc patterns
                named_devices = []     # Any device with a name
                unnamed_devices = []   # Devices without names
                
                for addr, dev_info in discovered_devices.items():
                    device = dev_info['device']
                    adv_data = dev_info['adv_data']
                    best_rssi = dev_info['best_rssi']
                    scan_count = dev_info['scan_count']
                    
                    name = device.name or "Unknown"
                    
                    # Check if device name matches any of our patterns
                    is_picocalc = any(pattern in name for pattern in DEVICE_NAME_PATTERNS)
                    
                    # Get UUIDs from advertisement data
                    uuids = []
                    if hasattr(adv_data, 'service_uuids'):
                        uuids = adv_data.service_uuids
                    
                    # Store device info for later
                    device_info = DeviceInfo(
                        address=addr,
                        name=name,
                        rssi=best_rssi,
                        uuids=uuids
                    )
                    
                    # Add to appropriate list with all data
                    device_data = (device, device_info, adv_data, scan_count)
                    
                    if is_picocalc:
                        picocalc_devices.append(device_data)
                    elif name != "Unknown":
                        named_devices.append(device_data)
                    else:
                        unnamed_devices.append(device_data)
                        
                    # Add to known devices
                    self.known_devices[device.address] = device_info
                
                # Save discovered devices
                self.save_known_devices()
                
                # Combine all devices with relevant ones at the top
                all_devices = picocalc_devices + named_devices + unnamed_devices
                
                if not all_devices:
                    print("No Bluetooth devices found. Check if Bluetooth is enabled.")
                    
                    # Offer manual entry as a fallback
                    custom_addr = input("Enter device address manually (MAC or UUID): ")
                    if custom_addr:
                        self.device_address = custom_addr
                        return custom_addr
                    return None
                
                # Display all devices sorted by relevance
                print("\nAll nearby Bluetooth devices:")
                print("-" * 90)
                print(f"{'#':<3} {'Device Name':<25} {'Address/UUID':<40} {'Signal':<10} {'Scans':<8}")
                print("-" * 90)
                
                for i, (device, info, adv_data, scan_count) in enumerate(all_devices):
                    name = device.name or "Unknown"
                    addr = device.address
                    
                    # Get signal strength from advertisement data
                    signal = f"{info.rssi} dBm" if info.rssi else "N/A"
                    
                    # Get UUIDs (for detecting if it has Nordic UART Service)
                    has_nus = False
                    if hasattr(adv_data, 'service_uuids'):
                        has_nus = any(_NUS_UUID.lower() in str(uuid).lower() for uuid in adv_data.service_uuids)
                    
                    # Determine if the device is likely a PicoCalc
                    is_likely_picocalc = has_nus or any(pattern in name for pattern in DEVICE_NAME_PATTERNS)
                    
                    # Limit address length for display
                    display_addr = addr
                    if len(addr) > 38:
                        display_addr = addr[:18] + "..." + addr[-17:]
                    
                    # Highlight PicoCalc devices
                    if is_likely_picocalc:
                        print(f"{i+1:<3} \033[1m{name:<25} {display_addr:<40} {signal:<10} {scan_count:<8}\033[0m")
                    else:
                        print(f"{i+1:<3} {name:<25} {display_addr:<40} {signal:<10} {scan_count:<8}")
                
                print("-" * 90)
                
                # Let user select a device
                while True:
                    choice = input(
                        "\nSelect device #, 'm' manual entry,\n"
                        " 'f' for more details,\n"
                        " 's' longer scan, or 'b' to cancel: "
                    ).strip().lower()

                    if choice == 'b':
                        print("Device selection cancelled.")
                        return None
                    
                    if choice.lower() == 'm':
                        custom_addr = input("Enter the device address manually (MAC or UUID): ")
                        if custom_addr:
                            print(f"Using address: {custom_addr}")
                            self.device_address = custom_addr
                            
                            # Save this address as a known device
                            device_info = DeviceInfo(address=custom_addr, name="Manual Entry")
                            device_info.last_connected = int(time.time())
                            self.add_known_device(device_info)
                            
                            return custom_addr
                            
                    elif choice.lower() == 'f':
                        # Show more details about devices
                        self.show_detailed_device_info(all_devices)
                        
                    elif choice.lower() == 's':
                        # Scan again with longer timeout
                        self.scan_timeout += 10.0
                        print(f"Scanning again with {self.scan_timeout}s timeout...")
                        return await self.extended_scan()
                        
                    else:
                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(all_devices):
                                device, device_info, _, _ = all_devices[idx]
                                print(f"Selected: {device.name or 'Unknown'} - {device.address}")
                                
                                # Update last connected time
                                device_info.last_connected = int(time.time())
                                self.add_known_device(device_info)
                                
                                self.device = device
                                self.device_address = device.address
                                return device.address
                            else:
                                print("Invalid selection. Please try again.")
                        except ValueError:
                            print("Invalid input. Please enter a number or 'm' or 'f' or 's'.")
                            
            except Exception as e:
                print(f"Scan error: {e}")
                
                # Fallback to manual entry if scan fails
                custom_addr = input("Enter the device address manually (MAC or UUID): ")
                if custom_addr:
                    print(f"Using address: {custom_addr}")
                    self.device_address = custom_addr
                    
                    # Save this address as a known device
                    device_info = DeviceInfo(address=custom_addr, name="Manual Entry")
                    device_info.last_connected = int(time.time())
                    self.add_known_device(device_info)
                    
                    return custom_addr
            
            print("\nUnable to find a suitable device.")
            return None

    def show_detailed_device_info(self, devices: List[Tuple[bleak.BLEDevice, DeviceInfo, Any, int]]):
        """Show detailed information about each device"""
        print("\nDetailed Device Information:")
        print("=" * 80)
        
        for i, (device, info, adv_data, scan_count) in enumerate(devices):
            name = device.name or "Unknown"
            addr = device.address
            print(f"Device #{i+1}: {name}")
            print(f"  Address/UUID: {addr}")
            print(f"  Signal Strength: {info.rssi if info.rssi else 'N/A'} dBm")
            print(f"  Detected {scan_count} times during scan")
            
            # Show UUIDs if available
            if hasattr(adv_data, 'service_uuids') and adv_data.service_uuids:
                uuids = adv_data.service_uuids
                print("  Services:")
                for uuid in uuids:
                    # Highlight Nordic UART Service
                    if _NUS_UUID.lower() in str(uuid).lower():
                        print(f"    \033[1m{uuid} (Nordic UART Service)\033[0m")
                    else:
                        print(f"    {uuid}")
            
            # Show any other advertisement data properties
            # Display local name if different from device name
            if hasattr(adv_data, 'local_name') and adv_data.local_name and adv_data.local_name != name:
                print(f"  Advertised Name: {adv_data.local_name}")
                
            # Display manufacturer data if available
            if hasattr(adv_data, 'manufacturer_data') and adv_data.manufacturer_data:
                print("  Manufacturer Data:")
                for company_id, data in adv_data.manufacturer_data.items():
                    print(f"    Company ID: {company_id}, Data: {data.hex()}")
            
            # Show previous connection info if available
            if info.last_connected > 0:
                time_ago = self.get_time_ago(info.last_connected)
                print(f"  Last connected: {time_ago}")
                
            print("-" * 80)
        
        input("Press Enter to continue...")


    def get_time_ago(self, timestamp: int) -> str:
        """Convert timestamp to human-readable time ago"""
        now = int(time.time())
        diff = now - timestamp
        
        if diff < 60:
            return f"{diff} seconds ago"
        elif diff < 3600:
            return f"{diff // 60} minutes ago"
        elif diff < 86400:
            return f"{diff // 3600} hours ago"
        else:
            return f"{diff // 86400} days ago"
    
    async def connect(self, address: str) -> bool:
        """Connect to PicoCalc with enhanced error handling for both MAC and UUID addresses"""
        try:
            print(f"Connecting to: {address}")
            
            # Use longer timeout for initial connection
            self.client = BleakClient(address, timeout=15.0)
            
            # Connect with extended timeout
            connected = await self.client.connect()
            if not connected:
                print("Failed to connect - BleakClient returned False")
                return False
                
            print(f"Connected to {address}")
            
            # Print all services and characteristics for debugging
            print("\nDiscovering services and characteristics...")
            for service in self.client.services:
                print(f"Service: {service.uuid}")
                for char in service.characteristics:
                    print(f"  Characteristic: {char.uuid}")
                    print(f"    Properties: {', '.join(char.properties)}")
                    print(f"    Handle: {char.handle}")
            
            # Find the Nordic UART Service characteristics
            self.tx_char = None  # We write to this (RX on the server side)
            self.rx_char = None  # We read from this (TX on the server side)
            
            # First try to find the Nordic UART Service
            for service in self.client.services:
                if service.uuid.lower() == _NUS_UUID.lower():
                    print(f"Found Nordic UART Service: {service.uuid}")
                    for char in service.characteristics:
                        if char.uuid.lower() == _NUS_RX.lower():
                            self.tx_char = char.uuid
                            print(f"Found RX characteristic: {char.uuid}")
                        
                        if char.uuid.lower() == _NUS_TX.lower():
                            self.rx_char = char.uuid
                            print(f"Found TX characteristic: {char.uuid}")
            
            # If we didn't find the NUS service, look for any suitable characteristics
            if not self.tx_char or not self.rx_char:
                print("Nordic UART Service not found completely. Looking for any suitable characteristics...")
                
                # First, try to find characteristics with known UUIDs
                for service in self.client.services:
                    for char in service.characteristics:
                        # Check for RX (write) characteristic
                        if not self.tx_char and char.uuid.lower() == _NUS_RX.lower():
                            self.tx_char = char.uuid
                            print(f"Found RX characteristic outside NUS: {char.uuid}")
                        
                        # Check for TX (notify) characteristic
                        if not self.rx_char and char.uuid.lower() == _NUS_TX.lower():
                            self.rx_char = char.uuid
                            print(f"Found TX characteristic outside NUS: {char.uuid}")
                
                # If still not found, look for any suitable characteristics by properties
                if not self.tx_char or not self.rx_char:
                    print("Looking for characteristics by properties...")
                    for service in self.client.services:
                        for char in service.characteristics:
                            if not self.tx_char and ("write" in char.properties or "write-without-response" in char.properties):
                                self.tx_char = char.uuid
                                print(f"Using {char.uuid} for TX (write) based on properties")
                            
                            if not self.rx_char and "notify" in char.properties:
                                self.rx_char = char.uuid
                                print(f"Using {char.uuid} for RX (notify) based on properties")
            
            # If we still didn't find a TX characteristic, fail
            if not self.tx_char:
                print("Error: No suitable TX characteristic found for sending commands")
                await self.client.disconnect()
                return False
            
            # Set up notification handler for RX characteristic
            if self.rx_char:
                print(f"Setting up notifications for {self.rx_char}")
                try:
                    await self.client.start_notify(self.rx_char, self.notification_handler)
                    print(f"Notifications enabled on {self.rx_char}")
                except Exception as e:
                    print(f"Warning: Could not enable notifications: {e}")
                    print("Will continue without notifications - some features may not work")
            else:
                print("Warning: No suitable RX characteristic found")
                print("Will continue without notifications - some features may not work")
            
            print("Connection and setup complete")
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
            return False
    
    def notification_handler(self, sender, data):
        """Handle notifications (responses from PicoCalc)"""
        if self.verbose:
            print(f"Received notification: {data.hex()}")
        
        # Add data to buffer
        self.response_buffer.extend(data)
        
        # Set event to indicate response received
        self.response_event.set()
    
    async def send_command(self, command: int, data: bytes = b'') -> bytearray:
        """Send command and wait for response with enhanced error handling"""
        try:
            if self.verbose:
                print(f"Sending command: {command}, data: {data.hex() if data else 'None'}")
            
            # Reset response buffer and event
            self.response_buffer = bytearray()
            self.response_event.clear()
            self.last_cmd = command
            
            # Prepare and send command
            cmd_data = bytearray([command]) + data
            
            # Check if we have a valid TX characteristic
            if not self.tx_char:
                print("Error: No TX characteristic available")
                return bytearray()
            
            # Send the command
            await self.client.write_gatt_char(self.tx_char, cmd_data, response=True)
            
            # Wait for response if we have notifications enabled
            if self.rx_char:
                try:
                    # Wait longer for responses, especially for directory listing
                    timeout = 10.0 if command == CMD_LIST_DIR else 5.0
                    await asyncio.wait_for(self.response_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    print("Timeout waiting for response")
                    return bytearray()
                    
                # Process different types of responses
                if command == CMD_LIST_DIR:
                    # We need to wait a bit longer for all chunks to arrive
                    # The server sends directory listing in chunks
                    await asyncio.sleep(0.5)
            else:
                # If we don't have notifications, just wait a bit
                await asyncio.sleep(0.5)
                
            # Return response
            return self.response_buffer
            
        except Exception as e:
            print(f"Error sending command: {e}")
            return bytearray()
    
    async def list_directory(self, path: str = "/sd") -> dict:
        """List directory contents"""
        print(f"Listing directory: {path}")
        
        try:
            # Send command
            response = await self.send_command(CMD_LIST_DIR, path.encode('utf-8'))
            
            if not response:
                print("No response received")
                return {}
                
            if self.verbose:
                print(f"Raw response: {response.hex()}")
                
            if not response or response[0] != CMD_LIST_DIR:
                print(f"Error: Invalid response code: {response[0] if response else 'None'}")
                return {}
                
            # Parse response
            # Format: CMD_LIST_DIR + path + '\0' + entries
            # Each entry: type (1 byte) + size (4 bytes) + name + '\0'
            
            # Skip command byte
            pos = 1
            
            # Extract path
            path_end = response.find(0, pos)
            if path_end < 0:
                print("Error: Invalid response format - no path terminator")
                return {}
                
            resp_path = response[pos:path_end].decode('utf-8')
            pos = path_end + 1
            
            # Extract entries
            entries = []
            while pos < len(response):
                # Check if we have enough data for an entry
                if pos + 5 >= len(response):
                    break
                    
                # Extract type
                entry_type = response[pos]
                pos += 1
                
                # Extract size
                size = struct.unpack("<I", response[pos:pos+4])[0]
                pos += 4
                
                # Extract name
                name_end = response.find(0, pos)
                if name_end < 0:
                    break
                    
                name = response[pos:name_end].decode('utf-8')
                pos = name_end + 1
                
                # Add entry
                entries.append({
                    "name": name,
                    "type": "directory" if entry_type == 1 else "file",
                    "size": size
                })
            
            # Print directory listing
            print(f"\nContents of {resp_path}:")
            print("-" * 50)
            print(f"{'Name':<30} {'Type':<10} {'Size':<10}")
            print("-" * 50)
            
            for entry in entries:
                size_str = f"{entry['size']:,}" if entry['type'] == "file" else ""
                print(f"{entry['name']:<30} {entry['type']:<10} {size_str:<10}")
            
            print()
            return {"path": resp_path, "entries": entries}
            
        except Exception as e:
            print(f"Error listing directory: {e}")
            return {}
    

    #
    async def upload_file(self, source_path: str, dest_path: str) -> bool:
        """
        Simplified upload_file:
        - Uses get_safe_filename() to generate a safe short name
        - Avoids creating temporary files
        - Uploads directly using the original file
        """
        try:
            source = Path(source_path)
            if not source.exists():
                print(f"Error: Source file not found: {source_path}")
                return False

            original_filename = os.path.basename(dest_path)
            safe_filename = get_safe_filename(original_filename, max_length=16)

            if safe_filename != original_filename:
                print(f"Long filename detected. Using safe filename '{safe_filename}'")

            upload_dest_path = f"{self.current_path}/{safe_filename}"

            if len(upload_dest_path.encode('utf-8')) > MAX_DEST_PATH_LENGTH:
                print(f"Error: Full destination path too long ({len(upload_dest_path)} chars)")
                print("Try uploading to a directory with a shorter path or shorten the filename.")
                return False

            file_size = source.stat().st_size
            print(f"Uploading {source} ({file_size:,} bytes) to {upload_dest_path}")

            # Start transfer
            response = await self.send_command(CMD_FILE_INFO, upload_dest_path.encode('utf-8'))
            if not response or response[0] != CMD_FILE_INFO or response[1] != 0:
                print(f"Error: Failed to start transfer. Response: {response.hex() if response else 'None'}")
                return False

            with open(source, "rb") as f:
                bytes_sent = 0
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    response = await self.send_command(CMD_FILE_DATA, chunk)
                    if not response or response[0] != CMD_FILE_DATA or response[1] != 0:
                        print(f"\nError: Failed to send data chunk at {bytes_sent} bytes")
                        return False
                    bytes_sent += len(chunk)
                    progress = min(100, int(100 * bytes_sent / file_size))
                    bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
                    print(f"\rProgress: [{bar}] {progress}% ({bytes_sent:,}/{file_size:,} bytes)", end="")
                    await asyncio.sleep(0.05)

            response = await self.send_command(CMD_FILE_END)
            if not response or response[0] != CMD_FILE_END or response[1] != 0:
                print("\nError: Failed to end transfer")
                return False

            print("\nTransfer complete!")
            return True

        except Exception as e:
            print(f"\nError uploading file: {e}")
            return False

    
    async def make_directory(self, path: str) -> bool:
        """Create a directory"""
        print(f"Creating directory: {path}")
        
        try:
            # Send command

            response = await self.send_command(
                CMD_MKDIR,
                path.encode('utf-8')
            )
            
            if not response or response[0] != CMD_MKDIR or response[1] != 0:
                print("Error: Failed to create directory")
                print(f"Response: {response.hex() if response else 'None'}")
                return False
                
            print(f"Created directory: {path}")
            return True
            
        except Exception as e:
            print(f"Error creating directory: {e}")
            return False
    
    async def delete_file(self, path: str) -> bool:
        """Delete a file"""
        print(f"Deleting file: {path}")
        
        try:
            # Send command
            response = await self.send_command(CMD_DELETE, path.encode('utf-8'))
            
            if not response or response[0] != CMD_DELETE or response[1] != 0:
                print("Error: Failed to delete file")
                print(f"Response: {response.hex() if response else 'None'}")
                return False
                
            print(f"Deleted file: {path}")
            return True
            
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    async def delete_directory(self, path: str) -> bool:
        """Delete a directory"""
        print(f"Deleting directory: {path}")
        
        try:
            # Send command
            response = await self.send_command(CMD_DELETE_DIR, path.encode('utf-8'))
            
            if not response or response[0] != CMD_DELETE_DIR or response[1] != 0:
                print("Error: Failed to delete directory")
                print(f"Response: {response.hex() if response else 'None'}")
                return False
                
            print(f"Deleted directory: {path}")
            return True
            
        except Exception as e:
            print(f"Error deleting directory: {e}")
            return False
            
    async def list_local_directory(self, path: str = ".") -> list:
        """List files in the local directory for selection"""
        try:
            # Get all files (not directories) in the specified path
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            
            if not files:
                print(f"No files found in {os.path.abspath(path)}")
                return []
                
            # Print files with numbers for selection
            print(f"\nFiles in {os.path.abspath(path)}:")
            print("-" * 50)
            for i, file in enumerate(files):
                file_size = os.path.getsize(os.path.join(path, file))
                print(f"{i+1}. {file} ({file_size:,} bytes)")
            print("-" * 50)
            
            return files
        except Exception as e:
            print(f"Error listing local directory: {e}")
            return []

    async def select_local_file(self) -> str:
        """Allow user to select a file from the current directory"""
        # First list files in current directory
        files = await self.list_local_directory()
        if not files:
            return ""
            
        while True:
            choice = input("Enter file number, 'c' to change dir, or 'b' to go back: ").strip().lower()

            if choice == 'b':
                return ""              # signal “no file picked” → back to main menu
            
            if choice.lower() == 'c':
                # Option to change local directory
                new_dir = input("Enter local directory path: ")
                if os.path.isdir(new_dir):
                    os.chdir(new_dir)
                    files = await self.list_local_directory()
                    if not files:
                        return ""
                else:
                    print(f"Invalid directory: {new_dir}")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(files):
                        selected_file = files[idx]
                        print(f"Selected: {selected_file}")
                        return selected_file
                    else:
                        print("Invalid selection. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter a number or 'c'.")

    async def change_remote_directory(self) -> str:
        """Navigate directories on the PicoCalc"""
        current_path = "/sd"
        
        while True:
            # List current directory
            dir_info = await self.list_directory(current_path)
            if not dir_info or "entries" not in dir_info:
                print(f"Could not list directory: {current_path}")
                return current_path
            
            # Extract only the directories
            directories = [entry for entry in dir_info["entries"] if entry["type"] == "directory"]
            
            # Show available directories with numbers
            if directories:
                print("\nAvailable directories:")
                for i, dir_entry in enumerate(directories):
                    print(f"{i+1}. {dir_entry['name']}")
            
            # Show navigation options
            print("\nNavigation options:")
            print("0. Select current directory")
            if current_path != "/sd":
                print("p. Go to parent directory")
            
            choice = input("\nEnter choice (number, 'p' for parent, or '0' for current): ")
            
            if choice == "0":
                # Select current directory
                return current_path
            elif choice.lower() == "p" and current_path != "/sd":
                # Go to parent directory
                parent_path = "/".join(current_path.split("/")[:-1])
                if not parent_path:
                    parent_path = "/sd"
                current_path = parent_path
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(directories):
                        # Navigate to selected directory
                        selected_dir = directories[idx]["name"]
                        current_path = f"{current_path}/{selected_dir}"
                    else:
                        print("Invalid selection. Please try again.")
                except ValueError:
                    print("Invalid input. Please enter a valid option.")
    
    async def disconnect(self):
        """Disconnect from PicoCalc"""
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
                print("Disconnected from PicoCalc")
            except Exception as e:
                print(f"Error disconnecting: {e}")


async def main():
    print("=== PicoCalc BLE File Transfer ===")
    print("Enhanced with better device discovery\n")
    client = EnhancedBLEClient()
    print(f"OS: {platform.system()} {platform.release()} | Python: {platform.python_version()}\n")

    # Connect to device
    addr = await client.extended_scan()
    if not addr:
        print("Device not found.")
        return
    if not await client.connect(addr):
        print("Connect failed.")
        return

    cur_dir = "/sd"
    menu = {
        '1': ("Upload file", upload_file),
        '2': ("List directory", list_directory),
        '3': ("Create directory", make_directory),
        '4': ("Delete file", delete_file),
        '5': ("Delete directory", delete_directory),  # Make sure this is the async function
        '6': ("Change directory", change_directory),
        '7': ("Toggle verbose", toggle_verbose),
        'q': ("Quit", None)
    }

    while True:
        print(f"\n[PicoCalc:{cur_dir}] Menu:")
        for k, (desc, _) in menu.items():
            print(f" {k}. {desc}")
        ch = input("Select option: ").lower()
        if ch == 'q':
            break
        action = menu.get(ch)
        if action:
            label, func = action
            if asyncio.iscoroutinefunction(func):
                # Fixed: using correct variable 'cur_dir' not 'current_path'
                result = await func(client, cur_dir)
                if isinstance(result, str):
                    cur_dir = result  # Updated dir from change_directory
            elif func:
                func(client)
        else:
            print("Invalid selection.")

    await client.disconnect()

# Make sure your delete_directory function is defined as async:
async def delete_directory(client, cur_dir):
    info = await client.list_directory(cur_dir)
    dirs = [d for d in info.get('entries', []) if d['type'] == 'directory']
    if dirs:
        for i, d in enumerate(dirs, 1):
            print(f" {i}. {d['name']}")
        sel = input("Directory # to delete: ")
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(dirs):
                dn = dirs[idx]['name']
                confirm = input(f"Delete directory {dn} and ALL its contents? (y/n): ")
                if confirm.lower() == 'y':
                    await client.delete_directory(f"{cur_dir}/{dn}")
            else:
                print("Invalid selection.")
    else:
        print("No directories found in this directory.")

        
async def upload_file(client, cur_dir):
    src = await client.select_local_file()
    if not src:
        return

    dst = src
    print(f"Uploading {src} to {cur_dir}/{dst}")
    success = await client.upload_file(src, f"{cur_dir}/{dst}")
    if not success:
        print("Upload failed.")

async def list_directory(client, cur_dir):
    await client.list_directory(cur_dir)

async def make_directory(client, cur_dir):
    name = input("Directory name: ")
    if name:
        await client.make_directory(f"{cur_dir}/{name}")

async def delete_file(client, cur_dir):
    info = await client.list_directory(cur_dir)
    files = [f for f in info.get('entries', []) if f['type'] == 'file']
    if files:
        for i, f in enumerate(files, 1):
            print(f" {i}. {f['name']}")
        sel = input("File # to delete, or 'b' to cancel: ").strip().lower()
        if sel == 'b':
            print("Delete cancelled.")
            return
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(files):
                fn = files[idx]['name']
                confirm = input(f"Delete {fn}? (y/n): ")
                if confirm.lower() == 'y':
                    await client.delete_file(f"{cur_dir}/{fn}")
            else:
                print("Invalid selection.")
    else:
        print("No files found in this directory.")

async def delete_directory(client, cur_dir):
    info = await client.list_directory(cur_dir)
    dirs = [d for d in info.get('entries', []) if d['type'] == 'directory']
    if dirs:
        for i, d in enumerate(dirs, 1):
            print(f" {i}. {d['name']}")
        sel = input("Directory # to delete: ")
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(dirs):
                dn = dirs[idx]['name']
                confirm = input(f"Delete directory {dn} and ALL its contents? (y/n): ")
                if confirm.lower() == 'y':
                    await client.delete_directory(f"{cur_dir}/{dn}")
            else:
                print("Invalid selection.")
    else:
        print("No directories found in this directory.")

async def change_directory(client, _):
    current_path = "/sd"

    while True:
        dir_info = await client.list_directory(current_path)
        if not dir_info or "entries" not in dir_info:
            print(f"Could not list directory: {current_path}")
            return current_path

        directories = [entry for entry in dir_info["entries"] if entry["type"] == "directory"]

        if not directories:
            print("No subdirectories found.")
            return current_path

        print("\nSubdirectories:")
        for i, entry in enumerate(directories):
            print(f" {i+1}. {entry['name']}")

        print("\nNavigation:")
        print("  0. Use current directory")
        if current_path != "/sd":
            print("  p. Go to parent directory")

        choice = input(f"[In: {current_path}] # to enter, 'p' parent, '0' current, or 'b' back: ").strip().lower()

        if choice == 'b':
            return current_path    # back up one level → main menu’s cur_dir stays the same
        
        if choice == '0':
            return current_path
        elif choice.lower() == "p" and current_path != "/sd":
            parts = current_path.rstrip("/").split("/")
            current_path = "/".join(parts[:-1]) if len(parts) > 1 else "/sd"
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(directories):
                current_path = f"{current_path}/{directories[idx]['name']}"
            else:
                print("Invalid number.")
        else:
            print("Invalid input. Please enter a number, '0', or 'p'.")


def toggle_verbose(client):
    client.verbose = not client.verbose
    print("Verbose mode", "on" if client.verbose else "off")

if __name__ == '__main__':
    asyncio.run(main())