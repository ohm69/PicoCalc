"""
Fox Hunt Competition Edition - ARDF/Radio Direction Finding Scanner
Designed for actual fox hunting competitions with proper direction finding
"""

import bluetooth
import time
import math
import os
from machine import Pin, PWM, ADC

# Competition Configuration
LOG_FILE = "/sd/logs/competition_log.txt"
RSSI_AT_1M = -59  # Calibration value
N_FACTOR = 2.0    # Path loss exponent
AUDIO_PIN = 28
ANTENNA_SAMPLES = 10  # Samples per direction

class CompetitionFoxHunt:
    def __init__(self):
        # BLE setup
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.ble_irq)
        
        # Audio setup
        try:
            self.audio = PWM(Pin(AUDIO_PIN))
            self.audio_enabled = True
        except:
            self.audio = None
            self.audio_enabled = False
        
        # Competition state
        self.target_mac = None
        self.target_name = ""
        self.scanning = False
        self.competition_mode = False
        
        # Direction finding data
        self.rssi_samples = []  # Store RSSI readings
        self.bearing_samples = {}  # RSSI by direction
        self.estimated_bearing = 0
        self.confidence = 0
        
        # Competition timing
        self.start_time = None
        self.found_time = None
        self.waypoints = []
        
        # Signal processing
        self.signal_history = []
        self.peak_rssi = -100
        self.avg_rssi = -100
        
        print("Fox Hunt Competition Edition")
        print("Designed for ARDF competitions")
    
    def ble_irq(self, event, data):
        """BLE interrupt handler with signal processing"""
        if event == 5 and self.scanning:  # ADV received
            try:
                addr_type, addr, adv_type, rssi, adv_data = data
                mac = ':'.join(['%02X' % b for b in bytes(addr)])
                
                # In competition mode, only track target
                if self.competition_mode and mac == self.target_mac:
                    self.process_signal(rssi)
                elif not self.competition_mode:
                    # Store all devices for selection
                    name = self.decode_name(adv_data)
                    if not hasattr(self, 'devices'):
                        self.devices = {}
                    self.devices[mac] = {
                        'rssi': rssi,
                        'name': name,
                        'last_seen': time.time()
                    }
            except:
                pass
    
    def decode_name(self, adv_data):
        """Decode device name"""
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
                if adv_data[i + 1] == 0x09:  # Complete Local Name
                    try:
                        return adv_data[i + 2:i + 1 + length].decode("utf-8")
                    except:
                        return ""
                i += 1 + length
            return ""
        except:
            return ""
    
    def process_signal(self, rssi):
        """Process RSSI for direction finding"""
        # Add to samples
        self.rssi_samples.append(rssi)
        if len(self.rssi_samples) > 50:
            self.rssi_samples.pop(0)
        
        # Update statistics
        if rssi > self.peak_rssi:
            self.peak_rssi = rssi
        
        if len(self.rssi_samples) >= 5:
            self.avg_rssi = sum(self.rssi_samples[-5:]) / 5
        
        # Signal strength audio feedback
        if self.audio_enabled:
            self.audio_feedback(rssi)
    
    def audio_feedback(self, rssi):
        """Competition-style audio feedback"""
        if not self.audio:
            return
        
        try:
            # Classic fox hunt audio pattern
            # Stronger signal = faster beeps
            if rssi > -50:
                beep_delay = 100  # Very close
            elif rssi > -60:
                beep_delay = 200
            elif rssi > -70:
                beep_delay = 400
            elif rssi > -80:
                beep_delay = 800
            else:
                beep_delay = 1600  # Far away
            
            # Check if enough time passed since last beep
            current_time = time.ticks_ms()
            if not hasattr(self, 'last_beep') or time.ticks_diff(current_time, self.last_beep) > beep_delay:
                self.audio.freq(1000)  # 1kHz tone
                self.audio.duty_u16(32768)  # 50% duty
                time.sleep_ms(50)
                self.audio.duty_u16(0)
                self.last_beep = current_time
        except:
            pass
    
    def calibrate_direction(self):
        """Calibrate direction finding by rotating"""
        print("\n=== Direction Calibration ===")
        print("Rotate slowly 360 degrees")
        print("Press ENTER at each cardinal direction")
        print("Press Q to finish early")
        
        directions = ["North (0°)", "East (90°)", "South (180°)", "West (270°)"]
        bearings = [0, 90, 180, 270]
        
        self.bearing_samples = {}
        
        for i, (direction, bearing) in enumerate(zip(directions, bearings)):
            print(f"\nPoint antenna to {direction}")
            cmd = input("Press ENTER when ready (Q to quit): ").strip().lower()
            
            if cmd == 'q':
                break
            
            # Collect samples
            print(f"Sampling {direction}...")
            samples = []
            start = time.time()
            
            while time.time() - start < 3:  # 3 second sample
                if self.rssi_samples:
                    samples.extend(self.rssi_samples[-5:])
                time.sleep(0.1)
            
            if samples:
                avg = sum(samples) / len(samples)
                self.bearing_samples[bearing] = avg
                print(f"{direction}: {avg:.1f} dBm (n={len(samples)})")
        
        # Calculate estimated bearing
        if len(self.bearing_samples) >= 2:
            # Find strongest signal direction
            strongest = max(self.bearing_samples.items(), key=lambda x: x[1])
            self.estimated_bearing = strongest[0]
            self.confidence = self.calculate_confidence()
            
            print(f"\nEstimated bearing: {self.estimated_bearing}°")
            print(f"Confidence: {self.confidence}%")
    
    def calculate_confidence(self):
        """Calculate direction finding confidence"""
        if len(self.bearing_samples) < 2:
            return 0
        
        rssi_values = list(self.bearing_samples.values())
        rssi_range = max(rssi_values) - min(rssi_values)
        
        # Good separation = high confidence
        if rssi_range > 20:
            return 95
        elif rssi_range > 15:
            return 80
        elif rssi_range > 10:
            return 60
        elif rssi_range > 5:
            return 40
        else:
            return 20
    
    def start_competition(self):
        """Start competition timer"""
        self.competition_mode = True
        self.start_time = time.time()
        self.waypoints = []
        print("\n=== COMPETITION STARTED ===")
        print(f"Time: {time.strftime('%H:%M:%S', time.localtime())}")
        print(f"Target: {self.target_name or self.target_mac}")
        print("\nGood luck!")
    
    def mark_waypoint(self):
        """Mark current position/bearing as waypoint"""
        waypoint = {
            'time': time.time() - self.start_time,
            'rssi': self.avg_rssi,
            'peak': self.peak_rssi,
            'bearing': self.estimated_bearing,
            'confidence': self.confidence
        }
        self.waypoints.append(waypoint)
        
        print(f"\nWaypoint #{len(self.waypoints)} marked")
        print(f"Time: {waypoint['time']:.1f}s")
        print(f"Signal: {waypoint['rssi']:.1f} dBm")
        print(f"Bearing: {waypoint['bearing']}°")
    
    def found_fox(self):
        """Mark fox as found"""
        if not self.competition_mode:
            print("Not in competition mode")
            return
        
        self.found_time = time.time()
        elapsed = self.found_time - self.start_time
        
        print("\n*** FOX FOUND! ***")
        print(f"Time: {elapsed//60:.0f}m {elapsed%60:.0f}s")
        print(f"Final signal: {self.peak_rssi} dBm")
        print(f"Waypoints used: {len(self.waypoints)}")
        
        # Log competition results
        self.log_competition()
    
    def log_competition(self):
        """Log competition results"""
        try:
            os.makedirs("/sd/logs", exist_ok=True)
            
            with open(LOG_FILE, "a") as f:
                f.write(f"\n=== Competition Log ===\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n")
                f.write(f"Target: {self.target_name} ({self.target_mac})\n")
                
                if self.found_time:
                    elapsed = self.found_time - self.start_time
                    f.write(f"Found in: {elapsed//60:.0f}m {elapsed%60:.0f}s\n")
                    f.write(f"Peak signal: {self.peak_rssi} dBm\n")
                    
                    # Log waypoints
                    f.write(f"\nWaypoints ({len(self.waypoints)}):\n")
                    for i, wp in enumerate(self.waypoints):
                        f.write(f"  #{i+1}: {wp['time']:.0f}s, "
                               f"{wp['rssi']:.1f}dBm, {wp['bearing']}°\n")
                else:
                    f.write("Status: In progress\n")
                
            print("Results logged")
        except Exception as e:
            print(f"Log error: {e}")
    
    def show_competition_display(self):
        """Show competition status"""
        if not self.competition_mode:
            print("Not in competition mode")
            return
        
        elapsed = time.time() - self.start_time
        
        print("\n" + "=" * 50)
        print(f"COMPETITION MODE - {elapsed//60:.0f}:{elapsed%60:02.0f}")
        print("=" * 50)
        
        # Signal status
        if self.avg_rssi > -100:
            # Signal bar
            signal_pct = max(0, min(100, (self.avg_rssi + 100) * 2))
            bar_len = signal_pct // 5
            signal_bar = "#" * bar_len + "-" * (20 - bar_len)
            
            print(f"Signal: [{signal_bar}] {self.avg_rssi:.1f}dBm")
            print(f"Peak: {self.peak_rssi} dBm")
            
            # Direction
            if self.estimated_bearing >= 0:
                directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                dir_idx = int((self.estimated_bearing + 22.5) % 360 / 45)
                print(f"Bearing: {directions[dir_idx]} ({self.estimated_bearing}°)")
                print(f"Confidence: {self.confidence}%")
            
            # Distance estimate (rough)
            distance = 10 ** ((RSSI_AT_1M - self.avg_rssi) / (10 * N_FACTOR))
            print(f"Est. distance: {distance:.1f}m")
        else:
            print("No signal detected")
        
        print(f"\nWaypoints: {len(self.waypoints)}")
        print("\nControls:")
        print("W=Waypoint C=Calibrate F=Found Q=Quit")
    
    def run_competition_mode(self):
        """Run competition tracking"""
        self.start_competition()
        self.scanning = True
        self.ble.gap_scan(0, 30000, 30000)
        
        last_display = 0
        
        while self.competition_mode:
            # Update display every second
            if time.time() - last_display > 1:
                print("\n" * 30)  # Clear screen
                self.show_competition_display()
                last_display = time.time()
            
            time.sleep(0.1)
        
        self.scanning = False
        self.ble.gap_scan(None)

def competition_menu():
    """Competition-focused menu"""
    scanner = CompetitionFoxHunt()
    
    while True:
        print("\n" + "=" * 50)
        print("Fox Hunt Competition Edition")
        print("=" * 50)
        print("\n1. Quick scan for foxes")
        print("2. Select competition target")
        print("3. Start competition mode")
        print("4. Practice mode")
        print("5. Calibrate direction finding")
        print("6. Review logs")
        print("7. Exit")
        
        choice = input("\nChoice (1-7): ").strip()
        
        if choice == "1":
            # Quick scan
            print("\nScanning for transmitters...")
            scanner.devices = {}
            scanner.scanning = True
            scanner.ble.gap_scan(10000, 30000, 30000)
            
            time.sleep(10)
            scanner.scanning = False
            scanner.ble.gap_scan(None)
            
            if hasattr(scanner, 'devices') and scanner.devices:
                print(f"\nFound {len(scanner.devices)} transmitters:")
                for i, (mac, data) in enumerate(sorted(scanner.devices.items(),
                                                      key=lambda x: x[1]['rssi'], 
                                                      reverse=True)[:5], 1):
                    print(f"{i}. {mac} ({data['rssi']}dBm) {data['name']}")
            else:
                print("No transmitters found")
        
        elif choice == "2":
            # Select target
            if hasattr(scanner, 'devices') and scanner.devices:
                print("\nSelect target:")
                devices = sorted(scanner.devices.items(),
                               key=lambda x: x[1]['rssi'], reverse=True)[:5]
                
                for i, (mac, data) in enumerate(devices, 1):
                    print(f"{i}. {mac} ({data['rssi']}dBm) {data['name']}")
                
                try:
                    idx = int(input("\nSelect (1-5): ")) - 1
                    if 0 <= idx < len(devices):
                        scanner.target_mac = devices[idx][0]
                        scanner.target_name = devices[idx][1]['name']
                        print(f"Target set: {scanner.target_mac}")
                except:
                    print("Invalid selection")
            else:
                print("Please scan first")
        
        elif choice == "3":
            # Competition mode
            if scanner.target_mac:
                scanner.run_competition_mode()
            else:
                print("Please select a target first")
        
        elif choice == "4":
            # Practice mode
            print("\nPractice mode - audio feedback enabled")
            scanner.audio_enabled = True
            scanner.competition_mode = False
            scanner.scanning = True
            scanner.ble.gap_scan(0, 30000, 30000)
            
            print("Scanning... Press Ctrl+C to stop")
            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                pass
            
            scanner.scanning = False
            scanner.ble.gap_scan(None)
        
        elif choice == "5":
            # Calibrate
            if scanner.target_mac:
                scanner.calibrate_direction()
            else:
                print("Please select a target first")
        
        elif choice == "6":
            # View logs
            try:
                with open(LOG_FILE, "r") as f:
                    print("\n=== Recent Logs ===")
                    lines = f.readlines()
                    for line in lines[-20:]:  # Last 20 lines
                        print(line.strip())
            except:
                print("No logs found")
        
        elif choice == "7":
            print("Good hunting!")
            break

def main():
    """Entry point"""
    try:
        competition_menu()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()