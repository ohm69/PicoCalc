"""
ProxiScan Compact - BLE Scanner for PicoCalc
Based on ProxiScan 3.0 but with WiFiManager's clean interface
"""

import bluetooth
import time
import os

# Configuration
LOG_FILE = "/sd/logs/ble_scan_log.txt"
RSSI_AT_1M = -59
N_FACTOR = 2.0

class CompactBLEScanner:
    def __init__(self):
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.devices = {}
        self.scanning = False
        self.target_mac = None
        
        # Set up IRQ handler
        self.ble.irq(self.ble_irq)
        
    def ble_irq(self, event, data):
        """BLE interrupt handler"""
        if event == 5 and self.scanning:  # ADV received
            try:
                addr_type, addr, adv_type, rssi, adv_data = data
                mac = ':'.join(['%02X' % b for b in bytes(addr)])
                name = self.decode_name(adv_data)
                
                self.devices[mac] = {
                    'rssi': rssi,
                    'name': name,
                    'last_seen': time.time(),
                    'distance': self.rssi_to_distance(rssi)
                }
            except:
                pass
    
    def decode_name(self, adv_data):
        """Decode device name from advertisement data"""
        try:
            if isinstance(adv_data, memoryview):
                adv_data = bytes(adv_data)
            
            i = 0
            while i < len(adv_data):
                if i >= len(adv_data):
                    break
                length = adv_data[i]
                if length == 0 or i + length >= len(adv_data):
                    break
                type_ = adv_data[i + 1]
                if type_ == 0x09:  # Complete Local Name
                    try:
                        name_bytes = adv_data[i + 2:i + 1 + length]
                        return name_bytes.decode("utf-8")
                    except:
                        return "<Invalid UTF-8>"
                i += 1 + length
            return ""
        except:
            return ""
    
    def rssi_to_distance(self, rssi):
        """Convert RSSI to estimated distance in meters"""
        try:
            if rssi >= 0:
                return 0.1
            distance = 10 ** ((RSSI_AT_1M - rssi) / (10 * N_FACTOR))
            return round(distance, 1)
        except:
            return 999.9
    
    def scan_ble_devices(self, duration=10):
        """Scan for BLE devices"""
        print(f"\nScanning for BLE devices ({duration}s)...")
        self.devices.clear()
        self.scanning = True
        
        try:
            # Start scan
            self.ble.gap_scan(duration * 1000, 30000, 30000)
            
            # Wait for scan to complete
            start = time.time()
            while time.time() - start < duration:
                print(f"\rFound {len(self.devices)} devices...", end="")
                time.sleep(0.5)
            
            # Stop scan
            self.scanning = False
            self.ble.gap_scan(None)
            
        except Exception as e:
            print(f"\nScan error: {e}")
            self.scanning = False
            return []
        
        print(f"\n\nFound {len(self.devices)} BLE devices")
        return list(self.devices.items())
    
    def display_devices(self, compact=True):
        """Display scanned devices"""
        if not self.devices:
            print("No devices found")
            return
        
        # Sort by signal strength
        sorted_devices = sorted(self.devices.items(), 
                              key=lambda x: x[1]['rssi'], reverse=True)
        
        print("\n=== BLE Devices ===")
        
        if compact:
            print("    MAC Address      RSSI  Dist   Name")
            print("-" * 50)
            for i, (mac, data) in enumerate(sorted_devices[:15], 1):
                name = data['name'][:15] if data['name'] else "[No Name]"
                print(f"{i:2}. {mac[-8:]}  {data['rssi']:4}dBm {data['distance']:4.1f}m  {name}")
        else:
            for i, (mac, data) in enumerate(sorted_devices[:10], 1):
                print(f"\n{i}. {mac}")
                print(f"   Name: {data['name'] if data['name'] else '[No Name]'}")
                print(f"   RSSI: {data['rssi']} dBm")
                print(f"   Distance: ~{data['distance']}m")
    
    def monitor_device(self, mac_address):
        """Monitor a specific device"""
        print(f"\nMonitoring {mac_address}")
        print("Press Ctrl+C to stop\n")
        
        self.target_mac = mac_address
        self.scanning = True
        
        try:
            # Continuous scan
            self.ble.gap_scan(0, 30000, 30000)
            
            while True:
                if mac_address in self.devices:
                    data = self.devices[mac_address]
                    bars = "*" * min(4, max(1, (data['rssi'] + 100) // 10))
                    print(f"\r{data['rssi']:4}dBm {bars:<4} ~{data['distance']:4.1f}m", end="")
                else:
                    print(f"\rTarget not found...    ", end="")
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped")
        finally:
            self.scanning = False
            self.ble.gap_scan(None)
    
    def analyze_ble_devices(self):
        """Analyze BLE environment"""
        if not self.devices:
            print("No devices to analyze")
            return
        
        print("\n=== BLE Analysis ===")
        print(f"Total devices: {len(self.devices)}")
        
        # Device types
        named = sum(1 for d in self.devices.values() if d['name'])
        unnamed = len(self.devices) - named
        print(f"Named devices: {named}")
        print(f"Unnamed devices: {unnamed}")
        
        # Signal distribution
        excellent = sum(1 for d in self.devices.values() if d['rssi'] >= -60)
        good = sum(1 for d in self.devices.values() if -70 <= d['rssi'] < -60)
        fair = sum(1 for d in self.devices.values() if -80 <= d['rssi'] < -70)
        poor = sum(1 for d in self.devices.values() if d['rssi'] < -80)
        
        print(f"\nSignal Quality:")
        print(f"Excellent (>-60dBm): {excellent}")
        print(f"Good (-70 to -60dBm): {good}")
        print(f"Fair (-80 to -70dBm): {fair}")
        print(f"Poor (<-80dBm): {poor}")
        
        # Closest devices
        closest = sorted(self.devices.items(), key=lambda x: x[1]['distance'])[:3]
        print(f"\nClosest devices:")
        for mac, data in closest:
            name = data['name'] if data['name'] else "[No Name]"
            print(f"  {mac[-8:]} - {data['distance']}m - {name}")
    
    def log_scan_results(self):
        """Log scan results to file"""
        if not self.devices:
            print("No devices to log")
            return
        
        try:
            # Ensure log directory exists
            log_dir = "/sd/logs"
            try:
                os.listdir(log_dir)
            except OSError:
                os.mkdir(log_dir)
            
            with open(LOG_FILE, "a") as f:
                f.write(f"\n=== BLE Scan {time.time()} ===\n")
                for mac, data in sorted(self.devices.items(), 
                                       key=lambda x: x[1]['rssi'], reverse=True):
                    f.write(f"{mac} | {data['rssi']}dBm | {data['distance']}m | {data['name']}\n")
            
            print(f"Logged {len(self.devices)} devices to {LOG_FILE}")
            
        except Exception as e:
            print(f"Log error: {e}")
    
    def cleanup(self):
        """Cleanup BLE resources"""
        try:
            self.ble.gap_scan(None)
            self.ble.active(False)
        except:
            pass

def main_menu():
    """Main menu for BLE Scanner"""
    scanner = CompactBLEScanner()
    
    while True:
        print("\n" + "=" * 50)
        print("BLE Scanner (ProxiScan Compact)")
        print("=" * 50)
        
        print("\nOptions:")
        print("1. Quick scan (10s)")
        print("2. Long scan (30s)")
        print("3. Display last results")
        print("4. Monitor specific device")
        print("5. Analyze BLE environment")
        print("6. Log results")
        print("7. Exit")
        
        choice = input("\nEnter choice (1-7): ").strip()
        
        if choice == "1":
            devices = scanner.scan_ble_devices(10)
            scanner.display_devices(compact=True)
            
        elif choice == "2":
            devices = scanner.scan_ble_devices(30)
            scanner.display_devices(compact=True)
            
        elif choice == "3":
            scanner.display_devices(compact=False)
            
        elif choice == "4":
            if not scanner.devices:
                print("No devices found. Please scan first.")
                continue
            
            print("\nSelect device to monitor:")
            scanner.display_devices(compact=True)
            
            try:
                idx = int(input("\nEnter device number: ")) - 1
                devices = sorted(scanner.devices.items(), 
                               key=lambda x: x[1]['rssi'], reverse=True)
                if 0 <= idx < len(devices):
                    mac = devices[idx][0]
                    scanner.monitor_device(mac)
                else:
                    print("Invalid selection")
            except ValueError:
                print("Invalid input")
            
        elif choice == "5":
            scanner.analyze_ble_devices()
            input("\nPress Enter to continue...")
            
        elif choice == "6":
            scanner.log_scan_results()
            input("\nPress Enter to continue...")
            
        elif choice == "7":
            print("Goodbye!")
            scanner.cleanup()
            break
        else:
            print("Invalid choice")

def main():
    """Main entry point"""
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nBLE Scanner stopped")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()