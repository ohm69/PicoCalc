# tri_plus_v3_grouped_ui1_fixed.py - 2-line per device UI + logging fix

import brad
import bluetooth
import time
import math
import os

try:
    from mac_prefixes import MAC_PREFIXES
except ImportError:
    MAC_PREFIXES = {}

LOG_FILE = "/sd/logs/scan_log.txt"
MAX_RUNTIME = 60
RSSI_AT_1M = -59
N_FACTOR = 2.0
DISPLAY_WIDTH = 320

device_memory = {}

def show_devices_ble(ble_data):
    print("\n=== BLE Devices (Grouped by Vendor/Name) ===")
    grouped = {}
    for mac, info in ble_data.items():
        vendor = info['name'] if info['name'] not in ("Unknown", "", "<Invalid UTF-8>") else get_vendor_label(mac)
        if vendor not in grouped:
            grouped[vendor] = []
        grouped[vendor].append((mac, info['rssi'], info['name']))

    for group in sorted(grouped.keys()):
        devices = sorted(grouped[group], key=lambda x: x[1], reverse=True)
        print(f"[{group}] ({len(devices)} device{'s' if len(devices) != 1 else ''})")
        for mac, rssi, name in devices:
            dist = rssi_to_distance(rssi)
            short_mac = mac[-5:]
            print(f"- {short_mac} | {rssi:>4} dBm | {dist:>5.1f} ft | {name}")
            log_to_file(f"BLE: {mac} | RSSI: {rssi} | Name: {name} | Dist: {dist:.2f} ft")

def show_devices_wifi(wifi_data):
    print("\n=== Wi-Fi Devices (Grouped by SSID Type) ===")
    grouped = {"MESH Networks": [], "Other SSIDs": []}
    for net in wifi_data:
        ssid = ensure_string(net["ssid"])[:16]
        rssi = int(net["rssi"])
        group = "MESH Networks" if "mesh" in ssid.lower() else "Other SSIDs"
        grouped[group].append((ssid, rssi))

    for group in grouped:
        print(f"[{group}]")
        for ssid, rssi in sorted(grouped[group], key=lambda x: x[1], reverse=True):
            dist = rssi_to_distance(rssi)
            print(f"- {ssid:<16} | {rssi:>4} dBm | {dist:>5.1f} ft")
            mesh = "[MESH]" if "mesh" in ssid.lower() else ""
            log_to_file(f"WiFi: SSID: {ssid} | RSSI: {rssi} | Dist: {dist:.2f} ft {mesh}")

def ensure_string(value):
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8', 'replace')
        except:
            return str(value)
    return str(value)

def rssi_to_distance(rssi):
    try:
        rssi = int(rssi)
        if rssi >= 0:
            return 0.1
        distance_m = math.pow(10, (RSSI_AT_1M - rssi) / (10 * N_FACTOR))
        return distance_m * 3.28084
    except:
        return 0.0

def decode_name(adv_data):
    name = ''
    i = 0
    while i < len(adv_data):
        length = adv_data[i]
        if length == 0:
            break
        type = adv_data[i + 1]
        if type == 0x09:
            try:
                name = adv_data[i + 2:i + 1 + length].decode('utf-8')
            except:
                name = "<Invalid UTF-8>"
            break
        i += 1 + length
    return name

def get_vendor_label(mac):
    prefix = ':'.join(mac.split(':')[0:3]).upper()
    return MAC_PREFIXES.get(prefix, "Unknown")

def update_memory(mac, rssi):
    if mac not in device_memory:
        device_memory[mac] = {"seen": 1, "strongest": rssi}
    else:
        device_memory[mac]["seen"] += 1
        if rssi > device_memory[mac]["strongest"]:
            device_memory[mac]["strongest"] = rssi

def scan_ble_devices(duration=4):
    ble = bluetooth.BLE()
    ble.active(True)
    found = {}

    def bt_irq(event, data):
        if event == 5:
            addr_type, addr, adv_type, rssi, adv_data = data
            mac = ':'.join('{:02X}'.format(b) for b in bytes(addr))
            name = decode_name(adv_data)
            vendor = get_vendor_label(mac)
            label = name if name not in ("Unknown", "", "<Invalid UTF-8>") else vendor
            if label == "Unknown":
                label = "Device"
            found[mac] = {"rssi": int(rssi), "name": label}

    ble.irq(bt_irq)
    ble.gap_scan(duration * 1000, 30000, 30000)
    time.sleep(duration)
    ble.gap_scan(None)
    return found

def scan_wifi_devices():
    results = []
    try:
        wifi_list = brad.scan_no_show()
        for net in wifi_list:
            if len(net) >= 4:
                ssid = ensure_string(net[0])
                rssi = int(net[3])
                results.append({"ssid": ssid, "rssi": rssi})
    except Exception as e:
        print(f"WiFi scan error: {e}")
    return results

def log_to_file(content):
    try:
        log_dir = "/sd/logs"
        try:
            os.listdir(log_dir)
        except OSError:
            os.mkdir(log_dir)
        with open(LOG_FILE, "a") as logf:
            logf.write(content + "\n")
    except Exception as e:
        print("Logging error:", e)

def scan_combined():
    wifi = scan_wifi_devices()
    ble = scan_ble_devices()
    show_devices_ble(ble)
    show_devices_wifi(wifi)

def main():
    print("=== 2-Line UI BLE + WiFi Scanner ===")
    start = time.time()
    while time.time() - start < MAX_RUNTIME:
        print("\n[Scanning...]")
        scan_combined()
        time.sleep(5)
    print("\nScan complete (60s timer).")

if __name__ == "__main__":
    main()
