import brad
import bluetooth
import time
import math
import os
import network
try:
    from mac_prefixes import MAC_PREFIXES
except ImportError:
    MAC_PREFIXES = {}

LOG_FILE = "/sd/logs/scan_log.txt"
MAX_RUNTIME = 30
RSSI_AT_1M = -59
N_FACTOR = 2.0
DISPLAY_WIDTH = 320

device_memory = {}
ble_devices = {}

def parse_apple_data(mfg_data):
    """Parse Apple-specific manufacturer data (Company ID: 0x004C)"""
    if len(mfg_data) < 4:
        return {"company": "Apple", "type": "Unknown", "raw": mfg_data.hex()}
    
    # Skip company ID (first 2 bytes: 4c00)
    apple_data = mfg_data[2:]
    data_type = apple_data[0]
    
    result = {"company": "Apple"}
    
    if data_type == 0x02 and len(apple_data) >= 3:
        subtype = apple_data[1]
        if subtype == 0x15 and len(apple_data) >= 23:
            # iBeacon format
            uuid = apple_data[2:18]
            major = int.from_bytes(apple_data[18:20], 'big')
            minor = int.from_bytes(apple_data[20:22], 'big')
            tx_power = int.from_bytes(apple_data[22:23], 'big', signed=True)
            result.update({
                "type": "iBeacon",
                "uuid": uuid.hex().upper(),
                "major": major,
                "minor": minor,
                "tx_power": tx_power
            })
        else:
            result.update({
                "type": "Apple Proximity Beacon",
                "subtype": f"0x{subtype:02x}",
                "data": apple_data[2:].hex()
            })
    
    elif data_type == 0x07:
        result.update({
            "type": "AirPods",
            "data": apple_data[1:].hex()
        })
    
    elif data_type == 0x09:
        result.update({
            "type": "AirPlay",
            "data": apple_data[1:].hex()
        })
    
    elif data_type == 0x0a:
        result.update({
            "type": "AirDrop",
            "data": apple_data[1:].hex()
        })
    
    elif data_type == 0x0c:
        result.update({
            "type": "Handoff/Continuity",
            "data": apple_data[1:].hex()
        })
    
    elif data_type == 0x0f:
        result.update({
            "type": "AirPods Pro",
            "data": apple_data[1:].hex()
        })
    
    elif data_type == 0x10:
        result.update({
            "type": "Nearby Action/Apple TV",
            "data": apple_data[1:].hex()
        })
    
    elif data_type == 0x12:
        result.update({
            "type": "FindMy Network",
            "data": apple_data[1:].hex()
        })
    
    else:
        result.update({
            "type": f"Apple Unknown (0x{data_type:02x})",
            "data": apple_data[1:].hex()
        })
    
    return result

def parse_manufacturer_data(mfg_data):
    """Parse manufacturer data based on company ID"""
    if len(mfg_data) < 2:
        return {"raw": mfg_data.hex()}
    
    # Company ID is little-endian in the first 2 bytes
    company_id = int.from_bytes(mfg_data[:2], 'little')
    
    # Common company IDs
    companies = {
        0x004C: "Apple",
        0x0006: "Microsoft", 
        0x00E0: "Google",
        0x004F: "Nordic Semiconductor",
        0x0075: "Samsung",
        0x001D: "Qualcomm",
        0x0087: "Garmin",
        0x000A: "Qualcomm Technologies",
        0x02E5: "Fitbit",
        0x0171: "Amazon",
    }
    
    company_name = companies.get(company_id, f"Unknown (0x{company_id:04x})")
    
    if company_id == 0x004C:  # Apple
        return parse_apple_data(mfg_data)
    else:
        return {
            "company": company_name,
            "company_id": f"0x{company_id:04x}",
            "data": mfg_data[2:].hex() if len(mfg_data) > 2 else ""
        }

def parse_ibeacon(mfg_data):
    if len(mfg_data) >= 25 and mfg_data[:4] == b'\x4C\x00\x02\x15':
        uuid = mfg_data[4:20]
        major = int.from_bytes(mfg_data[20:22], 'big')
        minor = int.from_bytes(mfg_data[22:24], 'big')
        tx_power = int.from_bytes(mfg_data[24:25], 'big', signed=True)
        return {
            "type": "iBeacon",
            "uuid": uuid.hex(),
            "major": major,
            "minor": minor,
            "tx_power": tx_power
        }
    return None

def rssi_to_distance(rssi):
    return 10 ** ((RSSI_AT_1M - rssi) / (10 * N_FACTOR))

def log_to_file(line):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except:
        pass

def get_vendor_label(mac):
    prefix = mac.upper()[0:8]
    return MAC_PREFIXES.get(prefix, "Unknown")

def decode_adv_data(adv_data):
    """FIXED: Handle memoryview objects"""
    # Convert memoryview to bytes if necessary
    if isinstance(adv_data, memoryview):
        adv_data = bytes(adv_data)
    
    parsed = {}
    i = 0
    while i < len(adv_data):
        if i >= len(adv_data):
            break
        length = adv_data[i]
        if length == 0 or i + length >= len(adv_data):
            break
        type_ = adv_data[i + 1]
        value = adv_data[i + 2:i + 1 + length]
        parsed[type_] = value
        i += 1 + length
    return parsed

def parse_extra_fields(adv_data_bytes):
    """FIXED: Handle memoryview objects"""
    try:
        ad = decode_adv_data(adv_data_bytes)
        info = {}

        if 0x19 in ad:
            appearance = int.from_bytes(ad[0x19], 'little')
            info['appearance'] = appearance

        if 0x02 in ad:
            info['services_16bit'] = [ad[0x02][i:i+2] for i in range(0, len(ad[0x02]), 2)]

        if 0x06 in ad:
            info['services_128bit'] = [ad[0x06][i:i+16] for i in range(0, len(ad[0x06]), 16)]

        if 0x09 in ad:  # Complete Local Name
            try:
                # Handle both bytes and memoryview
                name_data = ad[0x09]
                if isinstance(name_data, memoryview):
                    name_data = bytes(name_data)
                info['device_name'] = name_data.decode('utf-8')
            except (UnicodeDecodeError, TypeError):
                info['device_name'] = "<Invalid UTF-8>"

        if 0xFF in ad:
            mfg_data = ad[0xFF]
            # Convert memoryview to bytes if necessary
            if isinstance(mfg_data, memoryview):
                mfg_data = bytes(mfg_data)
            
            parsed_mfg = parse_manufacturer_data(mfg_data)
            info['manufacturer'] = parsed_mfg
            
            # Keep raw hex for debugging
            info['manufacturer_data_raw'] = mfg_data.hex()

        return info
    except Exception as e:
        return {"error": str(e)}

def show_devices_ble(ble_data):
    """Enhanced display function"""
    print("\n=== BLE Devices (Grouped by Vendor/Name) ===")
    grouped = {}
    
    for mac, info in ble_data.items():
        # Determine grouping key
        if 'manufacturer' in info.get('extra', {}):
            mfg_info = info['extra']['manufacturer']
            group_key = f"{mfg_info.get('company', 'Unknown')} - {mfg_info.get('type', 'Generic')}"
        elif info['name'] not in ("Unknown", "", "<Invalid UTF-8>"):
            group_key = info['name']
        else:
            group_key = get_vendor_label(mac)
        
        if group_key not in grouped:
            grouped[group_key] = []
        grouped[group_key].append((mac, info['rssi'], info['name'], info.get('extra', {})))

    for group in sorted(grouped.keys()):
        devices = sorted(grouped[group], key=lambda x: x[1], reverse=True)
        print(f"\n[{group}] ({len(devices)} device{'s' if len(devices) != 1 else ''})")
        
        for mac, rssi, name, extra in devices:
            dist = rssi_to_distance(rssi)
            short_mac = mac[-5:]
            print(f"- {short_mac} | {rssi:>4} dBm | {dist:>5.1f} ft | {name}")
            
            if 'manufacturer' in extra:
                mfg = extra['manufacturer']
                print(f"  Company: {mfg.get('company', 'Unknown')}")
                if 'type' in mfg:
                    print(f"  Type: {mfg['type']}")
                if 'uuid' in mfg:
                    print(f"  iBeacon UUID: {mfg['uuid']}")
                    print(f"  Major: {mfg['major']} Minor: {mfg['minor']} TX: {mfg['tx_power']}")
                if 'data' in mfg and mfg['data']:
                    print(f"  Data: {mfg['data']}")
            
            if 'appearance' in extra:
                print(f"  Appearance: {extra['appearance']}")
            if 'services_16bit' in extra:
                print(f"  Services (16-bit): {[s.hex() for s in extra['services_16bit']]}")
            if 'services_128bit' in extra:
                print(f"  Services (128-bit): {[s.hex() for s in extra['services_128bit']]}")

            log_to_file(f"BLE: {mac} | RSSI: {rssi} | Name: {name} | Manufacturer: {extra.get('manufacturer', {})} | Extra: {extra}")

def get_adv_name(adv_data):
    """FIXED: Handle memoryview objects"""
    try:
        # Convert memoryview to bytes if necessary
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
                except UnicodeDecodeError:
                    return "<Invalid UTF-8>"
            i += 1 + length
        return "Unknown"
    except Exception as e:
        return f"<Error: {str(e)}>"

def ble_irq(event, data):
    """FIXED: IRQ handler with proper error handling"""
    try:
        if event == 5:
            addr_type, addr, adv_type, rssi, adv_data = data
            mac = ':'.join(['%02X' % b for b in bytes(addr)])
            adv_info = get_adv_name(adv_data)
            extra = parse_extra_fields(adv_data)
            ble_devices[mac] = {
                "rssi": rssi,
                "name": adv_info,
                "extra": extra,
            }
    except Exception as e:
        # Silently ignore errors to prevent spam
        pass

def scan_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    results = wlan.scan()
    print("\n=== Wi-Fi Networks ===")
    for net in sorted(results, key=lambda x: x[3], reverse=True):
        ssid = net[0].decode() if isinstance(net[0], bytes) else net[0]
        rssi = net[3]
        auth = net[4]
        channel = net[2]
        mac = ':'.join('%02X' % b for b in net[1])
        security = {0: "Open", 1: "WEP", 2: "WPA-PSK", 3: "WPA2-PSK", 4: "WPA/WPA2-PSK"}.get(auth, "Unknown")
        print(f"- {ssid:<20} | {rssi:>4} dBm | Ch: {channel:<2} | {security} | {mac}")
        log_to_file(f"WIFI: {ssid} | RSSI: {rssi} | Ch: {channel} | {security} | MAC: {mac}")

def main():
    print("Starting BLE scan... Give 30 Seconds BRB")
    ble = bluetooth.BLE()
    ble.active(True)
    ble.irq(ble_irq)
    ble.gap_scan(30000, 30000, 30000)  # 30 seconds

    time.sleep(MAX_RUNTIME)

    ble.gap_scan(None)  # stop scan
    ble.active(False)
    show_devices_ble(ble_devices)

    # scan_wifi()

if __name__ == "__main__":
    main()