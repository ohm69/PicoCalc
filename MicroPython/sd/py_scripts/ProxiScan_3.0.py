"""
ProxiScan 3.0 - Fox Hunt Edition for PicoCalc
Features:
- Radio Direction Finding (RDF) capabilities
- Directional signal strength display
- Target tracking and hunting mode
- Enhanced audio feedback
- Compass-style interface
- Signal logging and analysis
"""

import picocalc
import brad
import bluetooth
import time
import math
import os
import utime
from machine import Pin, PWM

try:
    from mac_prefixes import MAC_PREFIXES
except ImportError:
    MAC_PREFIXES = {}

# Configuration
LOG_FILE = "/sd/logs/foxhunt_log.txt"
RSSI_AT_1M = -59
N_FACTOR = 2.0
SCAN_DURATION = 10  # Not used anymore, keeping for compatibility
AUDIO_PIN = 28

# Color definitions (for 4-bit grayscale display)
COLOR_BLACK = 0
COLOR_DARK_GRAY = 5
COLOR_GRAY = 10
COLOR_LIGHT_GRAY = 12
COLOR_WHITE = 15

# Color themes
COLOR_HEADER = COLOR_WHITE
COLOR_NORMAL = COLOR_LIGHT_GRAY
COLOR_DIM = COLOR_GRAY
COLOR_HIGHLIGHT = COLOR_WHITE
COLOR_WARNING = COLOR_LIGHT_GRAY
COLOR_SUCCESS = COLOR_WHITE

# Fox Hunt Mode Constants
MODE_SCAN = 0
MODE_HUNT = 1
MODE_TRACK = 2

# Arrow key escape sequences
KEY_UP = b'\x1b[A'
KEY_DOWN = b'\x1b[B'
KEY_LEFT = b'\x1b[D'
KEY_RIGHT = b'\x1b[C'
KEY_ESC = b'\x1b\x1b'

class FoxHuntScanner:
    def __init__(self):
        # Display setup
        self.display = picocalc.display
        self.width, self.height = self.display.width, self.display.height
        
        # Audio feedback
        try:
            self.audio = PWM(Pin(AUDIO_PIN))
        except (OSError, ValueError) as e:
            print(f"Audio setup failed: {e}")
            self.audio = None
        
        # Scanner state
        self.mode = MODE_SCAN
        self.mode_names = ["SCAN", "HUNT", "TRACK"]
        self.target_mac = None
        self.target_name = ""
        self.scanning = False
        self.last_scan_start = 0
        
        # Device data
        self.devices = {}
        self.target_history = []
        self.scan_count = 0
        
        # Direction finding simulation
        self.bearing = 0  # Simulated bearing to target
        self.signal_strength = 0
        self.last_rssi = -100
        
        # Performance optimization - cache compass points
        self.compass_cache = None
        self.last_bearing_drawn = -1
        
        # Input buffer
        self.key_buffer = bytearray(10)
        
        # BLE setup
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.ble_irq)
        
        # Animation
        self.animation_phase = 0
        self.last_update = utime.ticks_ms()
        self.last_device_count = 0
        
        print("Fox Hunt Scanner 3.0 initialized")
        self.update_display()
    
    def ble_irq(self, event, data):
        """BLE interrupt handler"""
        try:
            if event == 5:  # ADV received
                # Only process if we're actively scanning
                if not self.scanning:
                    return
                    
                addr_type, addr, adv_type, rssi, adv_data = data
                mac = ':'.join(['%02X' % b for b in bytes(addr)])
                name = self.decode_name(adv_data)
                
                # Update device data
                self.devices[mac] = {
                    'rssi': rssi,
                    'name': name,
                    'last_seen': utime.ticks_ms(),
                    'distance': self.rssi_to_distance(rssi)
                }
                
                # Update target if in hunt mode
                if self.mode == MODE_HUNT and mac == self.target_mac:
                    self.update_target_data(rssi)
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
            return "Unknown Device"
        except:
            return "Unknown Device"
    
    def rssi_to_distance(self, rssi):
        """Convert RSSI to estimated distance in feet"""
        try:
            if rssi >= 0:
                return 0.1
            distance_m = math.pow(10, (RSSI_AT_1M - rssi) / (10 * N_FACTOR))
            return distance_m * 3.28084
        except:
            return 999.9
    
    def update_target_data(self, rssi):
        """Update target tracking data"""
        self.last_rssi = rssi
        self.signal_strength = max(0, min(100, (rssi + 100) * 2))  # Scale to 0-100
        
        # Simulate bearing change based on signal strength variation
        if len(self.target_history) > 0:
            rssi_diff = rssi - self.target_history[-1]['rssi']
            self.bearing += rssi_diff * 2  # Simulate direction change
            self.bearing = self.bearing % 360
        
        # Add to history
        self.target_history.append({
            'time': utime.ticks_ms(),
            'rssi': rssi,
            'distance': self.rssi_to_distance(rssi),
            'bearing': self.bearing
        })
        
        # Keep history manageable
        if len(self.target_history) > 20:
            self.target_history.pop(0)
        
        # Audio feedback
        self.play_tone(rssi)
    
    def play_tone(self, rssi):
        """Play audio tone based on signal strength"""
        if not self.audio:
            return
        
        try:
            # Convert RSSI to frequency (higher RSSI = higher pitch)
            freq = max(200, min(2000, (rssi + 100) * 20))
            self.audio.freq(int(freq))
            self.audio.duty_u16(16384)  # 25% duty cycle
            utime.sleep_ms(50)
            self.audio.duty_u16(0)  # Turn off
        except:
            pass
    
    def start_scan(self):
        """Start BLE scanning"""
        try:
            # Use continuous scanning (0 = scan forever until stopped)
            self.ble.gap_scan(0, 30000, 30000)
            self.scan_count += 1
            self.last_scan_start = utime.ticks_ms()
            self.scanning = True
        except Exception as e:
            print(f"Scan start failed: {e}")
    
    def stop_scan(self):
        """Stop BLE scanning"""
        try:
            # Stop scanning first
            self.ble.gap_scan(None)
            utime.sleep_ms(100)  # Give time for scan to stop
            self.scanning = False  # Set flag after scan stopped
            self.last_scan_start = 0  # Reset scan timer
            # Keep devices for analysis - don't clear
        except Exception as e:
            print(f"Scan stop failed: {e}")
            self.scanning = False  # Ensure flag is set even on error
    
    def select_target(self):
        """Select strongest device as target"""
        if not self.devices:
            return False
        
        # Find strongest signal
        strongest_mac = max(self.devices.keys(), 
                          key=lambda k: self.devices[k]['rssi'])
        
        self.target_mac = strongest_mac
        self.target_name = self.devices[strongest_mac]['name']
        self.mode = MODE_HUNT
        self.target_history.clear()
        return True
    
    def update_display(self):
        """Update the display based on current mode"""
        self.display.fill(0)
        
        if self.mode == MODE_SCAN:
            self.draw_scan_mode()
        elif self.mode == MODE_HUNT:
            self.draw_hunt_mode()
        elif self.mode == MODE_TRACK:
            self.draw_track_mode()
        
        self.display.show()
    
    def draw_scan_mode(self):
        """Draw scanning interface"""
        # Header
        self.display.rect(0, 0, self.width, 30, COLOR_HEADER)
        self.display.text("FOX HUNT SCANNER 3.0", 5, 8, COLOR_HEADER)
        self.display.text(f"MODE: {self.mode_names[self.mode]}", 5, 18, COLOR_HIGHLIGHT)
        
        # Device count and scan info
        device_count = len(self.devices)
        scan_status = "SCANNING" if self.scanning else "STOPPED"
        scan_color = COLOR_SUCCESS if self.scanning else COLOR_WARNING
        self.display.text(f"Status: {scan_status}", 10, 40, scan_color)
        
        if not self.scanning:
            # Show stopped screen
            self.display.text("Scanner is stopped", 10, 80, COLOR_NORMAL)
            self.display.text("Press P or SPACE to start scanning", 10, 100, COLOR_HIGHLIGHT)
            
            # Show summary of last scan if devices were found
            if device_count > 0:
                self.display.text(f"Last scan found {device_count} devices", 10, 130, COLOR_DIM)
                self.display.text(f"Total scans: {self.scan_count}", 10, 150, COLOR_DIM)
                self.display.text("Press H to hunt strongest device", 10, 170, COLOR_HIGHLIGHT)
        else:
            # Show active scanning with devices
            self.display.text(f"Devices Found: {device_count}", 10, 55, COLOR_NORMAL)
            self.display.text(f"Scans: {self.scan_count}", 10, 70, COLOR_DIM)
            
            # Device list (top 6 by signal strength for less clutter)
            y_start = 90
            max_devices = min(6, (self.height - y_start - 80) // 35)  # Dynamic based on screen height
            sorted_devices = sorted(self.devices.items(), 
                                  key=lambda x: x[1]['rssi'], reverse=True)[:max_devices]
            
            for i, (mac, data) in enumerate(sorted_devices):
                y = y_start + i * 35  # Increased spacing to prevent overlap
                
                # Skip if would go off screen
                if y + 30 > self.height - 80:
                    break
                
                # Device box - color based on signal strength
                box_color = COLOR_NORMAL if data['rssi'] > -70 else COLOR_DIM
                self.display.rect(5, y, self.width - 10, 32, box_color)
                
                # Signal strength bar - simplified
                signal_width = int(max(2, min(40, (data['rssi'] + 100) * 1.5)))
                bar_color = COLOR_HIGHLIGHT if data['rssi'] > -60 else COLOR_NORMAL
                self.display.fill_rect(8, y + 3, signal_width, 4, bar_color)
                
                # Device info - more compact layout
                short_mac = mac[-8:]
                name = data['name'][:12] if data['name'] else "[No Name]"
                mac_color = COLOR_HIGHLIGHT if i == 0 else COLOR_NORMAL
                
                # Top line: MAC and RSSI
                self.display.text(f"{short_mac} {data['rssi']}dBm", 8, y + 10, mac_color)
                # Bottom line: Name and distance
                self.display.text(f"{name} {data['distance']:.1f}ft", 8, y + 22, COLOR_DIM)
        
        # Controls
        self.draw_scan_controls()
    
    def draw_hunt_mode(self):
        """Draw hunting interface with compass"""
        # Header
        self.display.rect(0, 0, self.width, 25, COLOR_HEADER)
        self.display.text("HUNTING MODE", 5, 5, COLOR_HEADER)
        self.display.text(f"Target: {self.target_name[:12]}", 5, 15, COLOR_HIGHLIGHT)
        
        # Target info
        if self.target_mac and self.target_mac in self.devices:
            target = self.devices[self.target_mac]
            rssi_color = COLOR_SUCCESS if target['rssi'] > -60 else (COLOR_NORMAL if target['rssi'] > -75 else COLOR_WARNING)
            self.display.text(f"RSSI: {target['rssi']} dBm", 10, 35, rssi_color)
            self.display.text(f"Distance: {target['distance']:.1f} ft", 10, 50, COLOR_NORMAL)
            
            # Signal strength meter
            self.draw_signal_meter(target['rssi'])
        
        # Compass display
        self.draw_compass()
        
        # Signal history graph
        self.draw_signal_history()
        
        # Controls
        self.draw_hunt_controls()
    
    def draw_compass(self):
        """Draw compass with directional indicator"""
        center_x, center_y = 160, 120
        radius = 40
        
        # Compass circle - using rect as approximation since circle not available
        # Draw octagon approximation of circle
        for angle in range(0, 360, 45):
            x1 = center_x + int(radius * math.cos(math.radians(angle)))
            y1 = center_y + int(radius * math.sin(math.radians(angle)))
            x2 = center_x + int(radius * math.cos(math.radians(angle + 45)))
            y2 = center_y + int(radius * math.sin(math.radians(angle + 45)))
            self.display.line(x1, y1, x2, y2, 1)
        
        # Cardinal directions
        self.display.text("N", center_x - 3, center_y - radius - 10, COLOR_HEADER)
        self.display.text("S", center_x - 3, center_y + radius + 2, COLOR_NORMAL)
        self.display.text("E", center_x + radius + 2, center_y - 3, COLOR_NORMAL)
        self.display.text("W", center_x - radius - 10, center_y - 3, COLOR_NORMAL)
        
        # Direction arrow (simulated)
        bearing_rad = math.radians(self.bearing)
        arrow_length = radius - 5
        end_x = center_x + int(arrow_length * math.sin(bearing_rad))
        end_y = center_y - int(arrow_length * math.cos(bearing_rad))
        
        # Draw arrow
        self.display.line(center_x, center_y, end_x, end_y, COLOR_HIGHLIGHT)
        # Arrow head
        head_length = 8
        head_angle = 0.5
        head1_x = end_x - int(head_length * math.sin(bearing_rad - head_angle))
        head1_y = end_y + int(head_length * math.cos(bearing_rad - head_angle))
        head2_x = end_x - int(head_length * math.sin(bearing_rad + head_angle))
        head2_y = end_y + int(head_length * math.cos(bearing_rad + head_angle))
        
        self.display.line(end_x, end_y, head1_x, head1_y, COLOR_HIGHLIGHT)
        self.display.line(end_x, end_y, head2_x, head2_y, COLOR_HIGHLIGHT)
        
        # Bearing text
        self.display.text(f"Bearing: {int(self.bearing)}°", center_x - 30, center_y + radius + 15, COLOR_NORMAL)
    
    def draw_signal_meter(self, rssi):
        """Draw vertical signal strength meter"""
        meter_x, meter_y = 280, 35
        meter_width, meter_height = 20, 100
        
        # Meter outline
        self.display.rect(meter_x, meter_y, meter_width, meter_height, COLOR_NORMAL)
        
        # Signal level - color coded
        signal_level = max(0, min(meter_height - 4, (rssi + 100) * 2))
        if signal_level > 0:
            # Gradient effect for signal bar
            bar_color = COLOR_SUCCESS if rssi > -60 else (COLOR_NORMAL if rssi > -75 else COLOR_WARNING)
            self.display.fill_rect(meter_x + 2, 
                                 meter_y + meter_height - 2 - signal_level, 
                                 meter_width - 4, signal_level, bar_color)
        
        # Scale markings
        for i in range(0, meter_height, 20):
            self.display.hline(meter_x - 3, meter_y + i, 3, COLOR_DIM)
        
        self.display.text("S", meter_x + 25, meter_y + 5, COLOR_HEADER)
        self.display.text("I", meter_x + 25, meter_y + 25, COLOR_NORMAL)
        self.display.text("G", meter_x + 25, meter_y + 45, COLOR_NORMAL)
        self.display.text("N", meter_x + 25, meter_y + 65, COLOR_NORMAL)
        self.display.text("A", meter_x + 25, meter_y + 85, COLOR_NORMAL)
        self.display.text("L", meter_x + 25, meter_y + 105, COLOR_HEADER)
    
    def draw_signal_history(self):
        """Draw signal strength history graph"""
        if len(self.target_history) < 2:
            return
        
        graph_x, graph_y = 10, 180
        graph_width, graph_height = 200, 60
        
        # Graph outline
        self.display.rect(graph_x, graph_y, graph_width, graph_height, COLOR_NORMAL)
        self.display.text("Signal History", graph_x, graph_y - 10, COLOR_HEADER)
        
        # Plot history
        if len(self.target_history) > 1:
            max_rssi = max(h['rssi'] for h in self.target_history)
            min_rssi = min(h['rssi'] for h in self.target_history)
            rssi_range = max_rssi - min_rssi if max_rssi != min_rssi else 1
            
            for i in range(1, len(self.target_history)):
                x1 = graph_x + (i - 1) * graph_width // len(self.target_history)
                x2 = graph_x + i * graph_width // len(self.target_history)
                
                y1 = graph_y + graph_height - int((self.target_history[i-1]['rssi'] - min_rssi) / rssi_range * (graph_height - 4))
                y2 = graph_y + graph_height - int((self.target_history[i]['rssi'] - min_rssi) / rssi_range * (graph_height - 4))
                
                self.display.line(x1, y1, x2, y2, COLOR_HIGHLIGHT)
    
    def draw_track_mode(self):
        """Draw tracking mode with detailed target info"""
        self.display.text("TRACKING MODE", 10, 10, COLOR_HEADER)
        
        if self.target_mac and len(self.target_history) > 0:
            latest = self.target_history[-1]
            
            # Target details
            self.display.text(f"Target: {self.target_name}", 10, 30, COLOR_HIGHLIGHT)
            self.display.text(f"MAC: {self.target_mac}", 10, 45, COLOR_NORMAL)
            rssi_color = COLOR_SUCCESS if latest['rssi'] > -60 else (COLOR_NORMAL if latest['rssi'] > -75 else COLOR_WARNING)
            self.display.text(f"Current RSSI: {latest['rssi']} dBm", 10, 60, rssi_color)
            self.display.text(f"Distance: {latest['distance']:.1f} ft", 10, 75, COLOR_NORMAL)
            self.display.text(f"Bearing: {latest['bearing']:.0f}°", 10, 90, COLOR_NORMAL)
            
            # Statistics
            if len(self.target_history) > 1:
                avg_rssi = sum(h['rssi'] for h in self.target_history) / len(self.target_history)
                min_dist = min(h['distance'] for h in self.target_history)
                
                self.display.text(f"Avg RSSI: {avg_rssi:.1f} dBm", 10, 110, COLOR_DIM)
                self.display.text(f"Closest: {min_dist:.1f} ft", 10, 125, COLOR_SUCCESS)
                self.display.text(f"Samples: {len(self.target_history)}", 10, 140, COLOR_DIM)
        
        self.draw_track_controls()
    
    def draw_scan_controls(self):
        """Draw scan mode controls"""
        y_start = self.height - 60
        self.display.text("Controls:", 10, y_start, COLOR_HEADER)
        self.display.text("P/SPACE: Start/Stop Scan", 10, y_start + 15, COLOR_NORMAL)
        self.display.text("H: Hunt Strongest  L: Log", 10, y_start + 30, COLOR_NORMAL)
        self.display.text("C: Clear target  ESC: Exit", 10, y_start + 45, COLOR_NORMAL)
    
    def draw_hunt_controls(self):
        """Draw hunt mode controls"""
        y_start = self.height - 45
        self.display.text("S: Scan  T: Track  C: Clear target", 10, y_start, COLOR_NORMAL)
        self.display.text("L: Log data  ESC: Exit", 10, y_start + 15, COLOR_NORMAL)
        self.display.text("Arrow keys: Simulate movement", 10, y_start + 30, COLOR_DIM)
    
    def draw_track_controls(self):
        """Draw track mode controls"""
        y_start = self.height - 30
        self.display.text("S: Scan  H: Hunt  C: Clear target", 10, y_start, COLOR_NORMAL)
        self.display.text("L: Log data  ESC: Exit", 10, y_start + 15, COLOR_NORMAL)
    
    def handle_input(self):
        """Handle keyboard input"""
        # Check if we have terminal input available
        if hasattr(picocalc, 'terminal') and picocalc.terminal:
            count = picocalc.terminal.readinto(self.key_buffer)
            if not count:
                return False
            key_data = bytes(self.key_buffer[:count])
        else:
            # Fallback for serial/REPL mode - skip input handling
            # In serial mode, rely on menu-based interface instead
            return False
        
        # Check for space key first (priority handling)
        if b' ' in key_data or (count == 1 and self.key_buffer[0] == 32):
            if self.mode == MODE_SCAN:
                self.toggle_scanning()
            return True
        
        # Check for ESC key (exit) - handle different ESC sequences
        if key_data == KEY_ESC or key_data == b'\x1b' or (count == 1 and self.key_buffer[0] == 27):
            return "EXIT"
        
        # Handle arrow keys (simulate movement in hunt mode)
        if self.mode == MODE_HUNT:
            if key_data == KEY_UP:
                self.bearing = (self.bearing - 10) % 360
                return True
            elif key_data == KEY_DOWN:
                self.bearing = (self.bearing + 10) % 360
                return True
            elif key_data == KEY_LEFT:
                self.bearing = (self.bearing - 30) % 360
                return True
            elif key_data == KEY_RIGHT:
                self.bearing = (self.bearing + 30) % 360
                return True
        
        # Handle single character keys
        if count == 1:
            key = self.key_buffer[0]
            
            # P key - start/stop scan
            if key == ord('p') or key == ord('P'):
                if self.mode == MODE_SCAN:
                    self.toggle_scanning()
                return True
            
            elif key == ord('h') or key == ord('H'):  # Hunt mode
                if self.mode == MODE_SCAN and self.devices:  # Can hunt if we have devices
                    self.select_target()
                    self.update_display()
                elif self.mode == MODE_TRACK:
                    self.mode = MODE_HUNT
                    self.update_display()
                return True
            
            elif key == ord('s') or key == ord('S'):  # Scan mode
                self.mode = MODE_SCAN
                self.stop_scan()
                return True
            
            elif key == ord('t') or key == ord('T'):  # Track mode
                if self.target_mac:
                    self.mode = MODE_TRACK
                return True
            
            elif key == ord('l') or key == ord('L'):  # Log data
                if self.mode == MODE_TRACK or (self.mode == MODE_HUNT and self.target_mac):
                    self.log_target_data()
                return True
            
            elif key == ord('c') or key == ord('C'):  # Clear/deselect target
                if self.mode == MODE_HUNT or self.mode == MODE_TRACK:
                    self.target_mac = None
                    self.target_name = ""
                    self.target_history.clear()
                    self.mode = MODE_SCAN
                    self.update_display()
                return True
        
        return True
    
    def toggle_scanning(self):
        """Toggle scanning state in scan mode"""
        if self.scanning:
            self.stop_scan()
        else:
            self.start_scan()
        self.update_display()  # Update display to show new state
    
    def log_target_data(self):
        """Log current target data to file"""
        if not self.target_mac or not self.target_history:
            # Show message on display
            self.display.fill_rect(10, self.height - 60, self.width - 20, 40, COLOR_BLACK)
            self.display.text("No target data to log", 20, self.height - 50, COLOR_WARNING)
            self.display.show()
            utime.sleep_ms(300)
            self.update_display()
            return
        
        try:
            log_dir = "/sd/logs"
            try:
                os.listdir(log_dir)
            except OSError:
                os.mkdir(log_dir)
            
            with open(LOG_FILE, "a") as f:
                timestamp = utime.ticks_ms()
                latest = self.target_history[-1]
                f.write(f"FOXHUNT: {timestamp} | Target: {self.target_name} | "
                       f"MAC: {self.target_mac} | RSSI: {latest['rssi']} | "
                       f"Distance: {latest['distance']:.2f} | "
                       f"Bearing: {latest['bearing']:.0f}\n")
            
            # Show success message on display
            self.display.fill_rect(10, self.height - 60, self.width - 20, 40, COLOR_BLACK)
            self.display.text("Target data logged!", 20, self.height - 50, COLOR_SUCCESS)
            self.display.show()
            utime.sleep_ms(300)
            self.update_display()
        except Exception as e:
            # Show error message on display
            self.display.fill_rect(10, self.height - 60, self.width - 20, 40, COLOR_BLACK)
            self.display.text("Log error!", 20, self.height - 50, COLOR_WARNING)
            self.display.show()
            utime.sleep_ms(300)
            self.update_display()
    
    def update_animation(self):
        """Update animations"""
        current_time = utime.ticks_ms()
        if current_time - self.last_update > 1000:  # Reduced to 1 FPS to save CPU
            self.animation_phase = (self.animation_phase + 1) % 360
            
            # Simulate slight bearing drift in hunt mode (only if actively tracking)
            if self.mode == MODE_HUNT and self.target_mac and self.target_mac in self.devices:
                drift = math.sin(self.animation_phase * 0.05) * 1  # Reduced drift
                self.bearing = (self.bearing + drift) % 360
            
            self.last_update = current_time
            return True
        return False
    
    def cleanup(self):
        """Cleanup resources"""
        self.stop_scan()
        if self.audio:
            self.audio.duty_u16(0)
        self.ble.active(False)
        
        self.display.fill(0)
        self.display.text("Fox Hunt Scanner Offline", 10, 10, COLOR_DIM)
        self.display.show()
    
    def run(self):
        """Main scanner loop"""
        # Check if terminal input is available
        if not hasattr(picocalc, 'terminal') or not picocalc.terminal:
            print("ProxiScan 3.0 requires direct hardware interface")
            print("When connected via serial, please use:")
            print("- ProxiScan_compact for basic BLE scanning")
            print("- FoxHunt_lite for text-based fox hunting")
            input("\nPress Enter to exit...")
            return
        
        try:
            while True:
                # Handle input
                result = self.handle_input()
                if result == "EXIT":
                    break
                
                # No need to restart scan anymore - using continuous mode
                # Scans will run until explicitly stopped
                
                # Update animations and display
                should_update = self.update_animation()
                
                # Also update display when device count changes
                if self.scanning and len(self.devices) != getattr(self, 'last_device_count', 0):
                    self.last_device_count = len(self.devices)
                    should_update = True
                
                if should_update:
                    self.update_display()
                
                # Short delay
                utime.sleep_ms(50)
                
        except KeyboardInterrupt:
            print("Scanner interrupted")
        
        self.cleanup()
        return

def main():
    """Main function"""
    try:
        scanner = FoxHuntScanner()
        scanner.run()
        print("Fox Hunt Scanner exited")
    except Exception as e:
        print(f"Error: {e}")
        import sys
        sys.print_exception(e)

if __name__ == "__main__":
    main()