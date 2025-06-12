"""
Fox Hunt Lite - Lightweight BLE Direction Finding Scanner
Text-based interface optimized for PicoCalc
"""

import bluetooth
import time
import math
import os
from machine import Pin, PWM

# Configuration
LOG_FILE = "/sd/logs/foxhunt_log.txt"
RSSI_AT_1M = -59
N_FACTOR = 2.0
AUDIO_PIN = 28

class FoxHuntLite:
    def __init__(self):
        # BLE setup
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.ble_irq)
        
        # Audio setup (optional)
        try:
            self.audio = PWM(Pin(AUDIO_PIN))
            self.audio_enabled = True
        except:
            self.audio = None
            self.audio_enabled = False
        
        # Scanner state
        self.mode = "SCAN"
        self.scanning = False
        self.devices = {}
        self.target_mac = None
        self.target_name = ""
        self.target_history = []
        
        # Simulated bearing (for demo purposes)
        self.bearing = 0
        self.last_rssi = -100
        
        print("Fox Hunt Lite initialized")
        print("Audio:", "Enabled" if self.audio_enabled else "Disabled")
    
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
                
                # Update target if tracking
                if self.mode == "HUNT" and mac == self.target_mac:
                    self.update_target(rssi)
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
                        return adv_data[i + 2:i + 1 + length].decode("utf-8")
                    except:
                        return ""
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
    
    def update_target(self, rssi):
        """Update target tracking data"""
        self.last_rssi = rssi
        
        # Simple bearing simulation based on signal change
        if len(self.target_history) > 0:
            rssi_diff = rssi - self.target_history[-1]['rssi']
            # Stronger signal = likely getting closer from current bearing
            # Weaker signal = likely moving away
            self.bearing = (self.bearing + rssi_diff * 5) % 360
        
        # Add to history
        self.target_history.append({
            'time': time.time(),
            'rssi': rssi,
            'distance': self.rssi_to_distance(rssi),
            'bearing': self.bearing
        })
        
        # Keep history limited
        if len(self.target_history) > 20:
            self.target_history.pop(0)
        
        # Audio feedback if enabled
        if self.audio_enabled:
            self.play_tone(rssi)
    
    def play_tone(self, rssi):
        """Play audio tone based on signal strength"""
        if not self.audio:
            return
        
        try:
            # Higher RSSI = higher pitch
            freq = max(200, min(2000, (rssi + 100) * 20))
            self.audio.freq(int(freq))
            self.audio.duty_u16(16384)  # 25% duty
            time.sleep_ms(50)
            self.audio.duty_u16(0)
        except:
            pass
    
    def start_scan(self):
        """Start continuous BLE scanning"""
        try:
            self.scanning = True
            self.ble.gap_scan(0, 30000, 30000)  # Continuous scan
            print("Scanning started...")
        except Exception as e:
            print(f"Scan error: {e}")
            self.scanning = False
    
    def stop_scan(self):
        """Stop BLE scanning"""
        try:
            self.scanning = False
            self.ble.gap_scan(None)
            # Force stop
            self.ble.active(False)
            time.sleep_ms(50)
            self.ble.active(True)
            time.sleep_ms(50)
        except:
            pass
    
    def show_scan_results(self):
        """Display scan results in text mode"""
        if not self.devices:
            print("No devices found")
            return
        
        print(f"\n=== Found {len(self.devices)} devices ===")
        print("    MAC        RSSI  Dist   Name")
        print("-" * 45)
        
        # Sort by signal strength
        sorted_devs = sorted(self.devices.items(), 
                           key=lambda x: x[1]['rssi'], reverse=True)
        
        for i, (mac, data) in enumerate(sorted_devs[:10], 1):
            name = data['name'][:12] if data['name'] else "[No name]"
            # Highlight strongest with asterisk
            mark = "*" if i == 1 else " "
            print(f"{i:2}{mark} {mac[-8:]}  {data['rssi']:3}dBm {data['distance']:4.1f}m  {name}")
    
    def select_target(self):
        """Select target for tracking"""
        if not self.devices:
            print("No devices to track")
            return False
        
        self.show_scan_results()
        
        try:
            choice = input("\nSelect device to track (1-10, 0=cancel): ").strip()
            if choice == "0":
                return False
            
            idx = int(choice) - 1
            sorted_devs = sorted(self.devices.items(), 
                               key=lambda x: x[1]['rssi'], reverse=True)
            
            if 0 <= idx < len(sorted_devs) and idx < 10:
                self.target_mac = sorted_devs[idx][0]
                self.target_name = sorted_devs[idx][1]['name']
                self.mode = "HUNT"
                self.target_history.clear()
                print(f"\nTracking: {self.target_mac}")
                return True
        except:
            pass
        
        print("Invalid selection")
        return False
    
    def show_hunt_display(self):
        """Show hunting mode display"""
        print("\n" + "=" * 45)
        print(f"HUNTING: {self.target_name or self.target_mac[-8:]}")
        print("=" * 45)
        
        if self.target_mac in self.devices:
            data = self.devices[self.target_mac]
            
            # Signal strength bar
            signal_pct = max(0, min(100, (data['rssi'] + 100) * 2))
            bar_len = signal_pct // 5
            signal_bar = "#" * bar_len + "-" * (20 - bar_len)
            
            print(f"Signal: [{signal_bar}] {data['rssi']}dBm")
            print(f"Distance: ~{data['distance']:.1f} meters")
            
            # Direction indicator (simple compass)
            directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            dir_idx = int((self.bearing + 22.5) % 360 / 45)
            print(f"Direction: {directions[dir_idx]} ({int(self.bearing)}°)")
            
            # Trend indicator
            if len(self.target_history) >= 2:
                trend = self.target_history[-1]['rssi'] - self.target_history[-2]['rssi']
                if trend > 1:
                    print("Trend: Getting STRONGER +++")
                elif trend < -1:
                    print("Trend: Getting WEAKER ---")
                else:
                    print("Trend: Stable ===")
            
            # Audio feedback indicator
            if self.audio_enabled:
                print("Audio: ON (higher pitch = stronger signal)")
        else:
            print("Target lost - searching...")
        
        print("\nControls: S=Stop hunt, A=Toggle audio, Q=Quit")
    
    def run_scan_mode(self):
        """Run scanning mode"""
        self.mode = "SCAN"
        self.devices.clear()
        
        print("\n=== SCAN MODE ===")
        print("Scanning for BLE devices...")
        print("Controls: H=Hunt strongest, R=Rescan, Q=Quit")
        
        self.start_scan()
        
        start_time = time.time()
        last_update = 0
        
        while self.mode == "SCAN":
            # Update display every 2 seconds
            if time.time() - last_update > 2:
                print(f"\rFound {len(self.devices)} devices... ", end="")
                last_update = time.time()
            
            # Auto-show results after 10 seconds
            if time.time() - start_time > 10 and len(self.devices) > 0:
                self.show_scan_results()
                break
            
            # Check for key press (non-blocking would be better)
            # For now, we'll use a timeout
            time.sleep(0.1)
        
        self.stop_scan()
    
    def run_hunt_mode(self):
        """Run hunting mode"""
        if not self.target_mac:
            print("No target selected")
            return
        
        print(f"\nStarting hunt for {self.target_name or self.target_mac}")
        self.start_scan()
        
        last_display = 0
        
        while self.mode == "HUNT":
            # Update display every second
            if time.time() - last_display > 1:
                # Clear screen (simple method)
                print("\n" * 50)
                self.show_hunt_display()
                last_display = time.time()
            
            time.sleep(0.1)
        
        self.stop_scan()
    
    def toggle_audio(self):
        """Toggle audio feedback"""
        if self.audio:
            self.audio_enabled = not self.audio_enabled
            if not self.audio_enabled:
                self.audio.duty_u16(0)
            print(f"Audio {'enabled' if self.audio_enabled else 'disabled'}")
        else:
            print("Audio not available")
    
    def log_results(self):
        """Log scan results"""
        try:
            # Ensure log directory exists
            try:
                os.listdir("/sd/logs")
            except:
                os.mkdir("/sd/logs")
            
            with open(LOG_FILE, "a") as f:
                f.write(f"\n=== Fox Hunt Log {time.time()} ===\n")
                
                if self.target_mac and self.target_history:
                    latest = self.target_history[-1]
                    f.write(f"Target: {self.target_name} ({self.target_mac})\n")
                    f.write(f"Last RSSI: {latest['rssi']}dBm\n")
                    f.write(f"Distance: {latest['distance']}m\n")
                    f.write(f"Bearing: {latest['bearing']}°\n")
                    f.write(f"History points: {len(self.target_history)}\n")
                else:
                    f.write(f"Devices found: {len(self.devices)}\n")
                    for mac, data in sorted(self.devices.items(), 
                                          key=lambda x: x[1]['rssi'], reverse=True)[:5]:
                        f.write(f"{mac}: {data['rssi']}dBm, {data['name']}\n")
            
            print("Results logged")
        except Exception as e:
            print(f"Log error: {e}")
    
    def cleanup(self):
        """Cleanup resources"""
        self.stop_scan()
        if self.audio:
            self.audio.duty_u16(0)
        self.ble.active(False)

def main_menu():
    """Main menu for Fox Hunt Lite"""
    scanner = FoxHuntLite()
    
    while True:
        print("\n" + "=" * 45)
        print("Fox Hunt Lite - BLE Direction Finder")
        print("=" * 45)
        print("\n1. Scan for devices")
        print("2. Hunt strongest signal")
        print("3. Select specific target")
        print("4. Toggle audio feedback")
        print("5. Log results")
        print("6. Exit")
        
        choice = input("\nChoice (1-6): ").strip()
        
        if choice == "1":
            scanner.run_scan_mode()
            
        elif choice == "2":
            scanner.run_scan_mode()
            if scanner.devices:
                # Auto-select strongest
                strongest = max(scanner.devices.items(), 
                              key=lambda x: x[1]['rssi'])
                scanner.target_mac = strongest[0]
                scanner.target_name = strongest[1]['name']
                scanner.mode = "HUNT"
                scanner.run_hunt_mode()
            
        elif choice == "3":
            if scanner.select_target():
                scanner.run_hunt_mode()
            
        elif choice == "4":
            scanner.toggle_audio()
            
        elif choice == "5":
            scanner.log_results()
            
        elif choice == "6":
            print("Goodbye!")
            scanner.cleanup()
            break
        
        else:
            print("Invalid choice")

def main():
    """Entry point"""
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\nFox Hunt stopped")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()