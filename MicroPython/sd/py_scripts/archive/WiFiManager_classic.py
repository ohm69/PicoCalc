# After Running this you should 
from brad import connect, load_wifi
import network

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

def connect_to_network(wlan, networks):
    print("\nSelect a network to connect:")
    for i, net in enumerate(networks):
        ssid = net[0].decode() if isinstance(net[0], bytes) else net[0]
        rssi = net[3]
        auth = net[4]
        print(f"{i + 1}. {ssid} | RSSI: {rssi} | Security: {auth}")

    choice = get_input("\nEnter number (or 0 to skip): ")
    if not choice.isdigit() or int(choice) == 0:
        print("Cancelled.")
        return

    idx = int(choice) - 1
    if idx < 0 or idx >= len(networks):
        print("Invalid selection.")
        return

    selected = networks[idx]
    ssid = selected[0].decode() if isinstance(selected[0], bytes) else selected[0]
    auth = selected[4]

    password = ""
    if auth != 0:
        password = read_password(f"Enter password for '{ssid}': ")

    print(f"Connecting to {ssid}...")
    success = connect(ssid, password)

    if success:
        ip = wlan.ifconfig()[0]
        print(f" Connected to {ssid} with IP: {ip}")
    else:
        print(" Failed to connect.")

def main():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # Check if already connected BEFORE trying to auto-connect
    already_connected = wlan.isconnected()
    
    if already_connected:
        print(f" Currently connected to: {wlan.config('essid')}")
        print(f" IP: {wlan.ifconfig()[0]}")
        print("\n1. Disconnect and connect to a new network")
        print("2. Keep current connection")
        choice = input("\nEnter choice: ").strip()
        if choice == "1":
            disconnect(wlan)
            print(" Scanning for networks...")
            networks = wlan.scan()
            connect_to_network(wlan, networks)
        else:
            print(" Keeping current connection.")
    else:
        ssid, password = load_wifi()
        if ssid and connect(ssid, password):
            print(f" Auto-connected to {ssid}")
        else:
            print(" Scanning for new networks...")
            networks = wlan.scan()
            connect_to_network(wlan, networks)

if __name__ == "__main__":
    main()
