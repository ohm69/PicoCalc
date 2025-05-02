"""
Updated BLE Client for PicoCalc
Specifically modified to work with the fixed BLE File Transfer server
"""

import asyncio
import os
import sys
import struct
import time
from pathlib import Path
import platform
from typing import Optional, List, Dict, Any

try:
    from bleak import BleakClient, BleakScanner
    from bleak.exc import BleakError
    import bleak
except ImportError:
    print("Error: 'bleak' library not found.")
    print("Please install it using: pip install bleak")
    sys.exit(1)

# PicoCalc device name
DEVICE_NAME = "PicoCalc-BLE"  # Updated to match server's name

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
CMD_DELETE_DIR = 7  # New command for directory deletion

# Chunk size for file transfer
CHUNK_SIZE = 20  # Match server chunk size

class UpdatedBLEClient:
    def __init__(self):
        self.client = None
        self.device = None
        self.device_address = None
        self.current_path = "/sd"
        self.response_buffer = bytearray()
        self.response_event = asyncio.Event()
        self.last_cmd = CMD_NONE
        self.verbose = False  # Enable verbose logging
        
    async def extended_scan(self) -> Optional[str]:
        """Perform enhanced scanning with more efficient device selection"""
        print("Starting Bluetooth scan...")
        print(f"Running on: {platform.system()} {platform.release()}")
        
        # Store previously connected device address in a file
        last_device_file = "last_picocalc_device.txt"
        last_device_address = None

        # Try to load last connected device
        try:
            if os.path.exists(last_device_file):
                with open(last_device_file, "r") as f:
                    last_device_address = f.read().strip()
                    print(f"Found previous device: {last_device_address}")
                    
                    # Ask if user wants to connect to the same device
                    choice = input(f"Connect to previously used device? (y/n): ")
                    if choice.lower() == 'y':
                        self.device_address = last_device_address
                        return last_device_address
        except Exception as e:
            print(f"Could not read last device: {e}")
        
        # Single combined scan approach
        try:
            print("Scanning for all nearby Bluetooth devices (15s)...")
            devices = await BleakScanner.discover(timeout=15.0)
            
            # Filter devices to show known ones first
            known_devices = []
            picocalc_devices = []
            unknown_devices = []
            
            for device in devices:
                name = device.name or "Unknown"
                if name == DEVICE_NAME:
                    # Exact match for PicoCalc-BLE
                    picocalc_devices.insert(0, device)
                elif "PicoCalc" in name:
                    # Other PicoCalc devices
                    picocalc_devices.append(device)
                elif name != "Unknown":
                    # Any device with a name
                    known_devices.append(device)
                else:
                    # Unnamed devices
                    unknown_devices.append(device)
            
            # Combine all devices with known ones at the top
            all_devices = picocalc_devices + known_devices + unknown_devices
            
            if not all_devices:
                print("No Bluetooth devices found. Check if Bluetooth is enabled.")
                return None
            
            # Display all devices sorted by relevance
            print("\nAll nearby Bluetooth devices:")
            print("-" * 50)
            for i, device in enumerate(all_devices):
                name = device.name or "Unknown"
                addr = device.address
                
                # Highlight PicoCalc devices
                if "PicoCalc" in name:
                    print(f"{i+1}. \033[1m{name} - {addr}\033[0m  ← PicoCalc device")
                else:
                    print(f"{i+1}. {name} - {addr}")
            print("-" * 50)
            
            # Let user select a device
            while True:
                choice = input("\nSelect your PicoCalc device number or 'm' for manual address entry: ")
                if choice.lower() == 'm':
                    custom_addr = input("Enter the device address manually: ")
                    if custom_addr:
                        print(f"Using manual address: {custom_addr}")
                        self.device_address = custom_addr
                        
                        # Save this address for next time
                        with open(last_device_file, "w") as f:
                            f.write(custom_addr)
                            
                        return custom_addr
                else:
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(all_devices):
                            device = all_devices[idx]
                            print(f"Selected: {device.name or 'Unknown'} - {device.address}")
                            self.device = device
                            self.device_address = device.address
                            
                            # Save this address for next time
                            with open(last_device_file, "w") as f:
                                f.write(device.address)
                                
                            return device.address
                        else:
                            print("Invalid selection. Please try again.")
                    except ValueError:
                        print("Invalid input. Please enter a number or 'm'.")
                        
        except Exception as e:
            print(f"Scan error: {e}")
            
            # Fallback to manual entry if scan fails
            custom_addr = input("Enter the device address manually: ")
            if custom_addr:
                print(f"Using manual address: {custom_addr}")
                self.device_address = custom_addr
                return custom_addr
        
        print("\nUnable to find PicoCalc device.")
        return None
    
    async def connect(self, address: str) -> bool:
        """Connect to PicoCalc with enhanced error handling"""
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
            
            for service in self.client.services:
                if service.uuid.lower() == _NUS_UUID.lower():
                    for char in service.characteristics:
                        if char.uuid.lower() == _NUS_RX.lower():
                            self.tx_char = char.uuid
                            print(f"Using {char.uuid} for TX (write)")
                        
                        if char.uuid.lower() == _NUS_TX.lower():
                            self.rx_char = char.uuid
                            print(f"Using {char.uuid} for RX (notify)")
            
            # If we didn't find the NUS service, look for any suitable characteristics
            if not self.tx_char or not self.rx_char:
                print("Nordic UART Service not found. Looking for any suitable characteristics...")
                
                for service in self.client.services:
                    for char in service.characteristics:
                        if "write" in char.properties and not self.tx_char:
                            self.tx_char = char.uuid
                            print(f"Using {char.uuid} for TX (write)")
                        
                        if "notify" in char.properties and not self.rx_char:
                            self.rx_char = char.uuid
                            print(f"Using {char.uuid} for RX (notify)")
            
            # If we still didn't find anything, fail
            if not self.tx_char:
                print("Error: No suitable TX characteristic found")
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
    
    async def upload_file(self, source_path: str, dest_path: str) -> bool:
        """Upload file to PicoCalc"""
        try:
            # Ensure source file exists
            source = Path(source_path)
            if not source.exists():
                print(f"Error: Source file not found: {source_path}")
                return False
            
            # Get file size
            file_size = source.stat().st_size
            print(f"Uploading {source_path} ({file_size:,} bytes) to {dest_path}")
            
            # Start transfer
            response = await self.send_command(CMD_FILE_INFO, dest_path.encode('utf-8'))
            if not response or response[0] != CMD_FILE_INFO or response[1] != 0:
                print(f"Error: Failed to start transfer. Response: {response.hex() if response else 'None'}")
                return False
            
            # Open file and send in chunks
            with open(source_path, "rb") as f:
                bytes_sent = 0
                
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    # Send chunk
                    response = await self.send_command(CMD_FILE_DATA, chunk)
                    if not response or response[0] != CMD_FILE_DATA or response[1] != 0:
                        print(f"\nError: Failed to send data chunk at {bytes_sent} bytes")
                        print(f"Response: {response.hex() if response else 'None'}")
                        return False
                    
                    bytes_sent += len(chunk)
                    
                    # Calculate and show progress
                    progress = min(100, int(100 * bytes_sent / file_size))
                    progress_bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
                    print(f"\rProgress: [{progress_bar}] {progress}% ({bytes_sent:,}/{file_size:,} bytes)", end="")
                    
                    # Brief delay to prevent overwhelming the device
                    await asyncio.sleep(0.05)
            
            # End transfer
            response = await self.send_command(CMD_FILE_END)
            if not response or response[0] != CMD_FILE_END or response[1] != 0:
                print("\nError: Failed to end transfer")
                print(f"Response: {response.hex() if response else 'None'}")
                return False
            
            # If we have the byte count in the response, display it
            if len(response) >= 6:
                total_bytes = struct.unpack("<I", response[2:6])[0]
                print(f"\nTransfer complete: {total_bytes:,} bytes")
            else:
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
            response = await self.send_command(CMD_MKDIR, path.encode('utf-8'))
            
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
            choice = input("Enter file number to select, or 'c' to change directory: ")
            
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
    print("Modified to work with fixed BLE File Transfer server\n")
    client = UpdatedBLEClient()
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
        '5': ("Delete directory", delete_directory),  # New option for directory deletion
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
                result = await func(client, cur_dir)
                if isinstance(result, str):
                    cur_dir = result  # Updated dir from change_directory
            elif func:
                func(client)
        else:
            print("Invalid selection.")

    await client.disconnect()

async def upload_file(client, cur_dir):
    src = await client.select_local_file()
    if src:
        dst = input(f"Dest name [{src}]: ") or src
        await client.upload_file(src, f"{cur_dir}/{dst}")

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
        sel = input("File # to delete: ")
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

        choice = input(f"[In: {current_path}] Select subdirectory # or 'p' for parent or '0' for current: ")
        
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