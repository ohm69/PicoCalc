from brad import connect, load_wifi
import network
import time

LOG_FILE = "/sd/logs/wifi_log.txt"
SCAN_TIMEOUT = 5  # seconds
MAX_RETRIES = 3

def log_to_file(line):
    """Log WiFi scan results to file with proper error handling"""
    try:
        # Create directory if it doesn't exist
        try:
            import os
            os.makedirs("/sd/logs", exist_ok=True)
        except:
            pass
        
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.time()}: {line}\n")
            f.flush()  # Ensure data is written
    except Exception as e:
        # Silently fail - logging should not crash the app
        print(f"[Log warning: {e}]")

def read_password(prompt="Enter password: "):
    pwd = input(prompt)
    print("✓ Password entered.\n")
    return pwd

def connect_to_saved_network(wlan):
    ssid, password = load_wifi()
    if ssid:
        print(f" Auto-connecting to: {ssid}")
        if connect(ssid, password):
            print(f" Connected to {ssid}")
            return True
        else:
            print(f" Failed to connect to saved network: {ssid}")
    else:
        print(" No saved Wi-Fi credentials found.")
    return False

def get_input(prompt):
    print(prompt)
    return input().strip()

def disconnect(wlan):
    if wlan.isconnected():
        wlan.disconnect()
        print(" Disconnected from current Wi-Fi.")

def scan_wifi_detailed(compact=False):
    """Enhanced WiFi scanning with timeout and retry mechanism"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    print("\nScanning for Wi-Fi networks...")
    
    # Try scanning with retries
    results = []
    for attempt in range(MAX_RETRIES):
        try:
            # Simple scan with error handling
            results = wlan.scan()
            if results:
                break
            else:
                print(f"No networks found on attempt {attempt + 1}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)
                
        except Exception as e:
            print(f"Scan error on attempt {attempt + 1}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(1)
                # Try to reset WiFi interface
                try:
                    wlan.active(False)
                    time.sleep(0.5)
                    wlan.active(True)
                    time.sleep(0.5)
                except:
                    pass
            continue
    
    if not results:
        print("No networks found.")
        return []
    
    print(f"\n=== Wi-Fi Networks Found: {len(results)} ===")
    print("Sorted by signal strength (strongest first)\n")
    
    # Sort by RSSI (signal strength) - strongest first
    sorted_networks = sorted(results, key=lambda x: x[3], reverse=True)
    
    for i, net in enumerate(sorted_networks, 1):
        ssid = net[0].decode() if isinstance(net[0], bytes) else net[0]
        bssid = net[1]  # MAC address bytes
        channel = net[2]
        rssi = net[3]
        auth = net[4]
        
        # Format MAC address
        mac = ':'.join('%02X' % b for b in bssid)
        
        # Security type mapping
        security = {
            0: "Open", 
            1: "WEP", 
            2: "WPA-PSK", 
            3: "WPA2-PSK", 
            4: "WPA/WPA2-PSK"
        }.get(auth, "Unknown")
        
        # Signal strength indicator
        if rssi >= -50:
            signal_quality = "Excellent"
        elif rssi >= -60:
            signal_quality = "Good"
        elif rssi >= -70:
            signal_quality = "Fair"
        else:
            signal_quality = "Poor"
        
        # Security indicator
        security_status = "Secured" if auth != 0 else "Open"
        
        if compact:
            # Compact format for connection selection
            ssid_short = ssid[:15] + ".." if len(ssid) > 17 else ssid
            print(f"{i:2}. {ssid_short:<17} {rssi:>4}dBm Ch{channel:<2} {security_status[:3]}")
        else:
            # Detailed format for network scanning
            print(f"{i:2}. {ssid:<20} | {rssi:>4} dBm | Ch:{channel:<2} | {security_status} | {signal_quality}")
            print(f"    MAC: {mac} | Security: {security}")
        
        # Log to file
        log_to_file(f"WIFI: {ssid} | RSSI: {rssi} | Ch: {channel} | {security} | MAC: {mac}")
    
    print(f"\n{'-' * 60}")
    return sorted_networks

def show_network_details(network):
    """Show detailed information about a specific network"""
    ssid = network[0].decode() if isinstance(network[0], bytes) else network[0]
    bssid = network[1]
    channel = network[2]
    rssi = network[3]
    auth = network[4]
    
    mac = ':'.join('%02X' % b for b in bssid)
    security = {0: "Open", 1: "WEP", 2: "WPA-PSK", 3: "WPA2-PSK", 4: "WPA/WPA2-PSK"}.get(auth, "Unknown")
    
    print(f"\nNetwork Details:")
    print(f"SSID:     {ssid}")
    print(f"MAC:      {mac}")
    print(f"Channel:  {channel}")
    print(f"RSSI:     {rssi} dBm")
    print(f"Security: {security}")
    
    # Signal quality assessment
    if rssi >= -50:
        quality = "Excellent"
    elif rssi >= -60:
        quality = "Good"
    elif rssi >= -70:
        quality = "Fair"
    else:
        quality = "Poor"
    
    print(f"Quality:  {quality}")

def connect_to_network(wlan, networks):
    """Enhanced network connection without recursion"""
    while True:
        if not networks:
            print("No networks available.")
            return False
        
        print(f"\nSelect a network to connect:")
        print("0. Rescan networks")
        print("00. Cancel")
        
        choice = get_input("\nEnter number (or add 'd' for details): ")
        
        if choice == "0":
            # Rescan networks without recursion
            networks = scan_wifi_detailed(compact=True)
            continue
        elif choice == "00":
            print("Cancelled.")
            return False
        elif choice.endswith('d'):
            # Show details for selected network
            try:
                idx = int(choice[:-1]) - 1
                if idx < 0 or idx >= len(networks):
                    print("Invalid selection.")
                    continue
                show_network_details(networks[idx])
                continue
            except ValueError:
                print("Invalid input.")
                continue
        elif not choice.isdigit():
            print("Invalid input.")
            continue

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(networks):
                print("Invalid selection.")
                continue
        except ValueError:
            print("Invalid input.")
            continue

        selected = networks[idx]
        
        # Show basic network info before connecting
        ssid = selected[0].decode() if isinstance(selected[0], bytes) else selected[0]
        rssi = selected[3]
        channel = selected[2]
        print(f"\nConnecting to: {ssid}")
        print(f"Signal: {rssi}dBm Channel: {channel}")
        
        auth = selected[4]

        # Get password if needed
        password = ""
        if auth != 0:
            print(f"Network requires authentication.")
            password = read_password(f"Enter password: ")

        print(f"Connecting...")
        
        # Connect with timeout handling
        try:
            success = connect(ssid, password)
            
            if success:
                ip = wlan.ifconfig()[0]
                print(f"Connected to {ssid}")
                print(f"IP Address: {ip}")
                
                # Log successful connection
                log_to_file(f"CONNECTED: {ssid} | IP: {ip}")
                return True
            else:
                print(f"Failed to connect to {ssid}")
                log_to_file(f"FAILED: {ssid}")
                return False
                
        except Exception as e:
            print(f"Connection error: {e}")
            log_to_file(f"ERROR: {ssid} - {e}")
            return False

def show_current_connection(wlan):
    """Show detailed current connection info"""
    if wlan.isconnected():
        essid = wlan.config('essid')
        ip, subnet, gateway, dns = wlan.ifconfig()
        
        print(f"Currently connected to: {essid}")
        print(f"IP Address: {ip}")
        print(f"Gateway: {gateway}")
        print(f"DNS: {dns}")
        
        # Try to get signal strength (if available)
        try:
            rssi = wlan.status('rssi')
            print(f"Signal: {rssi} dBm")
        except:
            pass
    else:
        print("Not connected to any network")

def monitor_signal(wlan, duration=30):
    """Real-time signal strength monitoring"""
    if not wlan.isconnected():
        print("Not connected to any network")
        return
    
    print(f"Monitoring signal for {duration} seconds...")
    print("Press Ctrl+C to stop early")
    print("-" * 40)
    
    start_time = time.time()
    min_rssi = None
    max_rssi = None
    readings = []
    
    try:
        while time.time() - start_time < duration:
            try:
                rssi = wlan.status('rssi')
                if rssi is not None:
                    readings.append(rssi)
                    
                    # Track min/max
                    if min_rssi is None or rssi < min_rssi:
                        min_rssi = rssi
                    if max_rssi is None or rssi > max_rssi:
                        max_rssi = rssi
                    
                    # Signal quality indicator
                    if rssi >= -50:
                        quality = "Excellent"
                        bars = "****"
                    elif rssi >= -60:
                        quality = "Good"
                        bars = "*** "
                    elif rssi >= -70:
                        quality = "Fair"
                        bars = "**  "
                    else:
                        quality = "Poor"
                        bars = "*   "
                    
                    elapsed = int(time.time() - start_time)
                    print(f"\r{elapsed:2}s: {rssi:>4}dBm {bars} {quality}  ", end="")
                    
                    time.sleep(1)
                else:
                    print("\rSignal data unavailable", end="")
                    time.sleep(1)
                    
            except Exception as e:
                print(f"\rError reading signal: {e}", end="")
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
    
    # Show statistics
    if readings:
        avg_rssi = sum(readings) / len(readings)
        print(f"\n\nSignal Statistics:")
        print(f"Average: {avg_rssi:.1f} dBm")
        print(f"Minimum: {min_rssi} dBm")
        print(f"Maximum: {max_rssi} dBm")
        print(f"Readings: {len(readings)}")
        
        # Log statistics
        log_to_file(f"SIGNAL_MONITOR: Avg:{avg_rssi:.1f} Min:{min_rssi} Max:{max_rssi} Readings:{len(readings)}")
    else:
        print("\nNo signal readings obtained")

def analyze_channels():
    """Analyze WiFi channel usage and congestion"""
    print("\nAnalyzing channel usage...")
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    try:
        networks = wlan.scan()
    except Exception as e:
        print(f"Scan failed: {e}")
        return
    
    if not networks:
        print("No networks found")
        return
    
    # Analyze by channel
    channel_data = {}
    
    for net in networks:
        ssid = net[0].decode() if isinstance(net[0], bytes) else net[0]
        channel = net[2]
        rssi = net[3]
        auth = net[4]
        
        if channel not in channel_data:
            channel_data[channel] = {
                'count': 0,
                'networks': [],
                'avg_rssi': 0,
                'strongest': rssi,
                'weakest': rssi
            }
        
        ch_data = channel_data[channel]
        ch_data['count'] += 1
        ch_data['networks'].append({'ssid': ssid, 'rssi': rssi, 'secure': auth != 0})
        
        # Update signal stats
        if rssi > ch_data['strongest']:
            ch_data['strongest'] = rssi
        if rssi < ch_data['weakest']:
            ch_data['weakest'] = rssi
    
    # Calculate averages
    for ch in channel_data:
        total_rssi = sum(net['rssi'] for net in channel_data[ch]['networks'])
        channel_data[ch]['avg_rssi'] = total_rssi / channel_data[ch]['count']
    
    # Display results
    print(f"\n=== Channel Analysis ({len(networks)} networks) ===")
    print("Ch  Networks  Congestion  Avg Signal  Best Choice")
    print("-" * 50)
    
    # Sort channels by number
    for ch in sorted(channel_data.keys()):
        data = channel_data[ch]
        count = data['count']
        avg_rssi = data['avg_rssi']
        
        # Congestion indicator (more networks = more congestion)
        if count <= 2:
            congestion = "Low"
            cong_bars = "*   "
        elif count <= 5:
            congestion = "Med"
            cong_bars = "**  "
        elif count <= 8:
            congestion = "High"
            cong_bars = "*** "
        else:
            congestion = "Full"
            cong_bars = "****"
        
        # Recommendation
        if count <= 3 and avg_rssi >= -70:
            recommendation = "Good"
        elif count <= 5 and avg_rssi >= -75:
            recommendation = "OK"
        else:
            recommendation = "Avoid"
        
        print(f"{ch:2}  {count:8}  {cong_bars} {congestion}  {avg_rssi:>7.1f}dBm  {recommendation}")
    
    # Show best channels
    print(f"\n=== Recommendations ===")
    
    # Find least congested channels
    sorted_channels = sorted(channel_data.items(), key=lambda x: (x[1]['count'], -x[1]['avg_rssi']))
    
    print("Best channels for new connections:")
    for i, (ch, data) in enumerate(sorted_channels[:3]):
        if i == 0:
            status = "Best"
        elif i == 1:
            status = "Good"
        else:
            status = "OK"
        print(f"  {status}: Channel {ch} ({data['count']} networks, {data['avg_rssi']:.1f}dBm avg)")
    
    # Show detailed view for most congested
    if channel_data:
        most_congested_ch = max(channel_data.keys(), key=lambda x: channel_data[x]['count'])
        if channel_data[most_congested_ch]['count'] > 5:
            print(f"\nMost congested: Channel {most_congested_ch} ({channel_data[most_congested_ch]['count']} networks)")
    
    # Log analysis
    log_to_file(f"CHANNEL_ANALYSIS: {len(networks)} networks across {len(channel_data)} channels")
    
    return channel_data

def analyze_networks():
    """Comprehensive network analysis with security and vendor info"""
    print("\nPerforming network analysis...")
    
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    try:
        networks = wlan.scan()
    except Exception as e:
        print(f"Scan failed: {e}")
        return
    
    if not networks:
        print("No networks found")
        return
    
    # Analyze networks
    network_analysis = {
        'total': len(networks),
        'open': 0,
        'secured': 0,
        'hidden': 0,
        'by_security': {},
        'by_vendor': {},
        'signal_distribution': {
            'excellent': 0,  # >= -50
            'good': 0,       # >= -60
            'fair': 0,       # >= -70
            'poor': 0        # < -70
        },
        'duplicate_ssids': {},
        'strongest_network': None,
        'weakest_network': None
    }
    
    # Common OUI (MAC prefix) to vendor mapping
    oui_vendors = {
        '00:0C:6B': 'Cisco',
        '10:0C:6B': 'Cisco',
        '16:0C:6B': 'Cisco',
        '1A:0C:6B': 'Cisco',
        'AC:E2:D3': 'HP',
        'F4:C1:14': 'Technicolor',
        'F8:79:0A': 'Arris',
        '7C:7E:F9': 'Eero',
        '00:1B:11': 'D-Link',
        '00:1F:33': 'Netgear',
        '00:24:B2': 'Netgear',
        '30:B5:C2': 'TP-Link',
        '00:14:BF': 'Linksys',
        '00:1A:70': 'Linksys',
        '00:90:4C': 'Epigram',
        'DC:A6:32': 'Raspberry Pi',
        'B8:27:EB': 'Raspberry Pi',
        'E4:5F:01': 'Raspberry Pi'
    }
    
    for net in networks:
        ssid = net[0].decode() if isinstance(net[0], bytes) else net[0]
        bssid = net[1]
        channel = net[2]
        rssi = net[3]
        auth = net[4]
        
        # Security analysis
        if auth == 0:
            network_analysis['open'] += 1
            sec_type = 'Open'
        else:
            network_analysis['secured'] += 1
            security_types = {
                1: 'WEP',
                2: 'WPA-PSK',
                3: 'WPA2-PSK',
                4: 'WPA/WPA2-PSK',
                5: 'WPA3'
            }
            sec_type = security_types.get(auth, 'Unknown')
        
        network_analysis['by_security'][sec_type] = network_analysis['by_security'].get(sec_type, 0) + 1
        
        # Hidden network detection
        if not ssid:
            network_analysis['hidden'] += 1
            ssid = '[Hidden]'
        
        # Duplicate SSID detection
        if ssid in network_analysis['duplicate_ssids']:
            network_analysis['duplicate_ssids'][ssid] += 1
        else:
            network_analysis['duplicate_ssids'][ssid] = 1
        
        # Signal distribution
        if rssi >= -50:
            network_analysis['signal_distribution']['excellent'] += 1
        elif rssi >= -60:
            network_analysis['signal_distribution']['good'] += 1
        elif rssi >= -70:
            network_analysis['signal_distribution']['fair'] += 1
        else:
            network_analysis['signal_distribution']['poor'] += 1
        
        # Track strongest/weakest
        if network_analysis['strongest_network'] is None or rssi > network_analysis['strongest_network']['rssi']:
            network_analysis['strongest_network'] = {'ssid': ssid, 'rssi': rssi, 'channel': channel}
        if network_analysis['weakest_network'] is None or rssi < network_analysis['weakest_network']['rssi']:
            network_analysis['weakest_network'] = {'ssid': ssid, 'rssi': rssi, 'channel': channel}
        
        # Vendor analysis
        mac_prefix = ':'.join('%02X' % b for b in bssid[:3])
        vendor = 'Unknown'
        for prefix, v_name in oui_vendors.items():
            if mac_prefix.startswith(prefix[:8]):
                vendor = v_name
                break
        
        network_analysis['by_vendor'][vendor] = network_analysis['by_vendor'].get(vendor, 0) + 1
    
    # Display results
    print(f"\n=== Network Analysis Summary ===")
    print(f"Total networks found: {network_analysis['total']}")
    print(f"Open networks: {network_analysis['open']} ({network_analysis['open']*100//network_analysis['total']}%)")
    print(f"Secured networks: {network_analysis['secured']} ({network_analysis['secured']*100//network_analysis['total']}%)")
    print(f"Hidden networks: {network_analysis['hidden']}")
    
    print(f"\n=== Security Distribution ===")
    for sec_type, count in sorted(network_analysis['by_security'].items()):
        percentage = count * 100 // network_analysis['total']
        bars = '*' * (percentage // 10) if percentage > 0 else ''
        print(f"{sec_type:<12}: {count:2} ({percentage:3}%) {bars}")
    
    print(f"\n=== Signal Quality ===")
    sig_dist = network_analysis['signal_distribution']
    for quality, label in [('excellent', 'Excellent'), ('good', 'Good'), ('fair', 'Fair'), ('poor', 'Poor')]:
        count = sig_dist[quality]
        percentage = count * 100 // network_analysis['total'] if network_analysis['total'] > 0 else 0
        print(f"{label:<9}: {count:2} ({percentage:3}%)")
    
    print(f"\n=== Network Highlights ===")
    if network_analysis['strongest_network']:
        s = network_analysis['strongest_network']
        print(f"Strongest: {s['ssid'][:20]} ({s['rssi']}dBm, Ch{s['channel']})")
    if network_analysis['weakest_network']:
        w = network_analysis['weakest_network']
        print(f"Weakest: {w['ssid'][:20]} ({w['rssi']}dBm, Ch{w['channel']})")
    
    # Show duplicate SSIDs
    duplicates = {k: v for k, v in network_analysis['duplicate_ssids'].items() if v > 1}
    if duplicates:
        print(f"\n=== Duplicate SSIDs ===")
        for ssid, count in sorted(duplicates.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"{ssid[:25]:<25}: {count} APs")
    
    # Vendor distribution (only show if interesting)
    if len(network_analysis['by_vendor']) > 1 or 'Unknown' not in network_analysis['by_vendor']:
        print(f"\n=== Access Point Vendors ===")
        for vendor, count in sorted(network_analysis['by_vendor'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"{vendor:<15}: {count}")
    
    # Security warnings
    if network_analysis['open'] > 0:
        print(f"\n! Warning: {network_analysis['open']} open network(s) detected")
    
    wep_count = network_analysis['by_security'].get('WEP', 0)
    if wep_count > 0:
        print(f"! Warning: {wep_count} network(s) using weak WEP encryption")
    
    # Log analysis summary
    log_to_file(f"NETWORK_ANALYSIS: {network_analysis['total']} networks, {network_analysis['open']} open, {network_analysis['secured']} secured")
    
    return network_analysis

def main_menu():
    """Enhanced main menu with error handling"""
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
    except Exception as e:
        print(f"WiFi initialization error: {e}")
        return False
    
    print("=" * 50)
    print("WiFi Manager")
    print("=" * 50)
    
    show_current_connection(wlan)
    
    if wlan.isconnected():
        print("\nOptions:")
        print("1. Scan and connect to new network")
        print("2. Monitor signal strength")
        print("3. Analyze channels")
        print("4. Network analysis")
        print("5. BLE Scanner (ProxiScan)")
        print("6. Disconnect current network")
        print("7. Show connection details")
        print("8. Exit")
        
        choice = input("\nEnter choice (1-8): ").strip()
        
        if choice == "1":
            disconnect(wlan)
            networks = scan_wifi_detailed(compact=True)
            connect_to_network(wlan, networks)
            
        elif choice == "2":
            print("\nSignal Monitoring")
            duration = input("Duration in seconds (default 30): ").strip()
            try:
                duration = int(duration) if duration else 30
                duration = min(duration, 300)  # Max 5 minutes
            except:
                duration = 30
            monitor_signal(wlan, duration)
            input("\nPress Enter to continue...")
            
        elif choice == "3":
            analyze_channels()
            input("\nPress Enter to continue...")
            
        elif choice == "4":
            analyze_networks()
            input("\nPress Enter to continue...")
            
        elif choice == "5":
            # Launch BLE scanner
            try:
                print("\nLaunching BLE Scanner...")
                print("Freeing memory...")
                # Clear some memory before launching
                import gc
                gc.collect()
                
                # Option 1: Try the compact version first
                try:
                    import ProxiScan_compact
                    ProxiScan_compact.main()
                except ImportError:
                    # Option 2: If that fails, try to launch as subprocess
                    print("Note: BLE Scanner requires restart")
                    print("Please run 'ProxiScan_3.0' from main menu")
                    input("\nPress Enter to continue...")
            except ImportError:
                print("BLE Scanner not available")
                input("\nPress Enter to continue...")
            except Exception as e:
                print(f"BLE Scanner error: {e}")
                input("\nPress Enter to continue...")
            
        elif choice == "6":
            disconnect(wlan)
            
        elif choice == "7":
            show_current_connection(wlan)
            input("\nPress Enter to continue...")
            
        elif choice == "8":
            print("Goodbye!")
            return False
        else:
            print("Invalid choice")
            
        return True
            
    else:
        print("\nOptions:")
        print("1. Try saved network")
        print("2. Scan and connect to network")
        print("3. Analyze channels")
        print("4. Network analysis")
        print("5. BLE Scanner (ProxiScan)")
        print("6. Exit")
        
        choice = input("\nEnter choice (1-6): ").strip()
        
        if choice == "1":
            if not connect_to_saved_network(wlan):
                print("\nAuto-connect failed. Scanning for networks...")
                networks = scan_wifi_detailed(compact=True)
                connect_to_network(wlan, networks)
                
        elif choice == "2":
            networks = scan_wifi_detailed(compact=True)
            connect_to_network(wlan, networks)
            
        elif choice == "3":
            analyze_channels()
            input("\nPress Enter to continue...")
            
        elif choice == "4":
            analyze_networks()
            input("\nPress Enter to continue...")
            
        elif choice == "5":
            # Launch BLE scanner
            try:
                print("\nLaunching BLE Scanner...")
                print("Freeing memory...")
                # Clear some memory before launching
                import gc
                gc.collect()
                
                # Option 1: Try the compact version first
                try:
                    import ProxiScan_compact
                    ProxiScan_compact.main()
                except ImportError:
                    # Option 2: If that fails, try to launch as subprocess
                    print("Note: BLE Scanner requires restart")
                    print("Please run 'ProxiScan_3.0' from main menu")
                    input("\nPress Enter to continue...")
            except ImportError:
                print("BLE Scanner not available")
                input("\nPress Enter to continue...")
            except Exception as e:
                print(f"BLE Scanner error: {e}")
                input("\nPress Enter to continue...")
            
        elif choice == "6":
            print("Goodbye!")
            return False
        else:
            print("Invalid choice")
            
        return True

def main():
    """Main function with safe loop and exit handling"""
    max_iterations = 100  # Prevent infinite loops
    iteration = 0
    
    try:
        while iteration < max_iterations:
            iteration += 1
            
            try:
                if not main_menu():
                    break
                
            except Exception as e:
                print(f"\nMenu error: {e}")
                # Give option to exit on error
                if input("Exit? (y/N): ").strip().lower() == 'y':
                    break
                    
    except KeyboardInterrupt:
        print("\n\nWiFi Manager stopped by user")
    except Exception as e:
        print(f"\nCritical error: {e}")
    finally:
        print("WiFi Manager exited.")

if __name__ == "__main__":
    main()