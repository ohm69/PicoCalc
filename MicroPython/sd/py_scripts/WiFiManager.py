from brad import connect, load_wifi
import network
import time

LOG_FILE = "/sd/logs/wifi_log.txt"

def log_to_file(line):
    """Log WiFi scan results to file"""
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.time()}: {line}\n")
    except:
        pass

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

def scan_wifi_detailed():
    """Enhanced WiFi scanning with detailed information"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    print("\nScanning for Wi-Fi networks...")
    results = wlan.scan()
    
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
    """Enhanced network connection with better UI"""
    if not networks:
        print("No networks available.")
        return
    
    print(f"\nSelect a network to connect:")
    print("0. Rescan networks")
    print("00. Cancel")
    
    choice = get_input("\nEnter number: ")
    
    if choice == "0":
        # Rescan networks
        networks = scan_wifi_detailed()
        if networks:
            connect_to_network(wlan, networks)
        return
    elif choice == "00" or not choice.isdigit():
        print("Cancelled.")
        return

    idx = int(choice) - 1
    if idx < 0 or idx >= len(networks):
        print("Invalid selection.")
        return

    selected = networks[idx]
    
    # Show network details
    show_network_details(selected)
    
    ssid = selected[0].decode() if isinstance(selected[0], bytes) else selected[0]
    auth = selected[4]

    # Get password if needed
    password = ""
    if auth != 0:
        print(f"\nNetwork '{ssid}' requires authentication.")
        password = read_password(f"Enter password for '{ssid}': ")

    print(f"Connecting to {ssid}...")
    success = connect(ssid, password)

    if success:
        ip = wlan.ifconfig()[0]
        print(f"Connected to {ssid}")
        print(f"IP Address: {ip}")
        
        # Log successful connection
        log_to_file(f"CONNECTED: {ssid} | IP: {ip}")
    else:
        print(f"Failed to connect to {ssid}")
        log_to_file(f"FAILED: {ssid}")

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

def main_menu():
    """Enhanced main menu"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    print("=" * 50)
    print("WiFi Manager")
    print("=" * 50)
    
    show_current_connection(wlan)
    
    if wlan.isconnected():
        print("\nOptions:")
        print("1. Scan and connect to new network")
        print("2. Show detailed network scan")
        print("3. Disconnect current network")
        print("4. Show connection details")
        print("5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            disconnect(wlan)
            networks = scan_wifi_detailed()
            connect_to_network(wlan, networks)
            
        elif choice == "2":
            scan_wifi_detailed()
            input("\nPress Enter to continue...")
            
        elif choice == "3":
            disconnect(wlan)
            
        elif choice == "4":
            show_current_connection(wlan)
            input("\nPress Enter to continue...")
            
        elif choice == "5":
            print("Goodbye!")
            return
        else:
            print("Invalid choice")
            
    else:
        print("\nOptions:")
        print("1. Try saved network")
        print("2. Scan and connect to network")
        print("3. Exit")
        
        choice = input("\nEnter choice (1-3): ").strip()
        
        if choice == "1":
            if not connect_to_saved_network(wlan):
                print("\nAuto-connect failed. Scanning for networks...")
                networks = scan_wifi_detailed()
                connect_to_network(wlan, networks)
                
        elif choice == "2":
            networks = scan_wifi_detailed()
            connect_to_network(wlan, networks)
            
        elif choice == "3":
            print("Goodbye!")
            return
        else:
            print("Invalid choice")

def main():
    """Main function with loop for continuous operation"""
    try:
        while True:
            main_menu()
            
            # Ask if user wants to continue
            print("\n" + "-" * 30)
            cont = input("Continue? (Y/n): ").strip().lower()
            if cont == 'n':
                break
            print()
            
    except KeyboardInterrupt:
        print("\n\nWiFi Manager stopped by user")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()