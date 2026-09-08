import network
import time
import bluetooth
import machine
import math

###################################
#             WARNING             #
#   THIS PART CONTAINS WIFI PASS  #
###################################

WIFI_SSID = "enter your wifi name here"
WIFI_PASSWORD = "wifi password goes here"

wifi_connected = False
wifi_rssi = None

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

wlan.config(reconnects = 0)

print("WIFI_SCAN_START")

try:
    networks = wlan.scan()
    target_found = False
    for network_info in networks:
        ssid = network_info[0].decode()
        rssi = network_info[3]

        if ssid == WIFI_SSID:
            target_found = True
            wifi_rssi = rssi

            print("WIFI_FOUND",
                ssid,
                "RSSI:",
                wifi_rssi
            )

            break
    
    if target_found:
        print("WIFI_CONNECTING")

        wlan.connect(
            WIFI_SSID,
            WIFI_PASSWORD
        )

        for _ in range(10):
            if wlan.isconnected():
                break

            time.sleep(1)
        
        wifi_connected = wlan.isconnected()

        if wifi_connected:
            try:
                wifi_rssi = wlan.status("rssi")
            
            except Exception:
                pass
        
            print(
                "WIFI_CONNECTED",
                "RSSI:",
                wifi_rssi
            )
        
        else:
            print(
                "WIFI_FAILED",
                "RSSI:",
                wifi_rssi
            )

            wlan.disconnect()
            wlan.active(False)
        
    
    else:
        print("WIFI_NOT_FOUND")
        wlan.active(False)

except Exception as error:
    print("WIFI_ERROR:", error)
    wifi_connected = False
    wifi_rssi = None

    try:
        wlan.disconnect()
        wlan.active(False)

    except Exception:
        pass

# LD2450 UART
uart = machine.UART(
    2,
    baudrate = 256000,
    bits = 8,
    parity = None,
    stop = 1,
    rx = 16,
    tx = 17
)

print("LD2450 UART READY")


# Bluetooth Fallback
ble = bluetooth.BLE()
ble.active(True)

UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UART_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), bluetooth.FLAG_NOTIFY)
UART_RX = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), bluetooth.FLAG_WRITE)
    
UART_SERVICE = (UART_UUID, (UART_TX, UART_RX))

((tx_handle, rx_handle),) = ble.gatts_register_services((UART_SERVICE,))



# Connection Handling
connected_handle = None
status_attempts = 0
last_status_time = 0


def start_bluetooth():
    name = "Home Radar"
    adv = b"\x02\x01\x06" + bytes((11, 0x09)) + name.encode()
    ble.gap_advertise(100000, adv)
    print("BLUETOOTH_ADVERTISING")




def bt_irq(event, data):
    global connected_handle
    global status_attempts
    global last_status_time

    if event == 1:
        connected_handle = data[0]

        status_attempts = 0
        last_status_time = time.ticks_ms()

        print("BLUETOOTH_CONNECTED")

    elif event == 2:
        connected_handle = None
        status_attempts = 0

        print("BLUETOOTH_DISCONNECTED")

        start_bluetooth()

ble.irq(bt_irq)
start_bluetooth()

# LD2450 Parsing
radar_buffer = bytearray()
last_targets = None

def parse_target(raw):
    x_raw = raw[0] | (raw[1] << 8)
    y_raw = raw[2] | (raw[3] << 8)

    x = x_raw - 0x7FFF
    y = y_raw - 0x7FFF

    if x_raw & 0x8000:
        x = -x

    distance = math.sqrt(
        x * x + y * y
    )

    return x, y, distance

def send_targets(targets):
    if connected_handle is None:
        return
    
    # One target = 4 bytes.
    # Int16 X + Int16 Y
    # 3 targets = 12 bytes
    # First byte = No. of valid targets

    packet = bytearray()

    packet.append(
        len(targets)
    )

    for x, y, distance in targets:
        packet += int(x).to_bytes(
            2,
            "little",
            signed = True
        )

        packet += int(y).to_bytes(
            2,
            "little",
            signed = True
        )
    
    try:
        ble.gatts_notify(
            connected_handle,
            tx_handle,
            packet
        )

    except Exception as error:
        print(
            "RADAR SEND ERROR:",
            error
        )

def read_radar():
    global radar_buffer
    global last_targets

    if uart.any() == 0:
        return

    data = uart.read()

    if data is None:
        return
    
    radar_buffer.extend(data)

    while True:
        # Finding Frame Header
        header_index = radar_buffer.find(
            b"\xAA\xFF\x03\x00"
        )

        if header_index < 0:
            # Keep a few trailing bytes just in case.
            # Header is split across UART readings.
            
            if len(radar_buffer) > 3:
                radar_buffer = radar_buffer[-3:]

            return
        
        # Throw away anything before header
        if header_index > 0:
            del radar_buffer[
                :header_index
            ]
        
        # Full frame is 30 bytes
        if len(radar_buffer) < 30:
            return
        
        # Check frame footer
        if (
            radar_buffer[28] != 0x55
            or radar_buffer[29] != 0xCC
        ):

            radar_buffer = radar_buffer[0]
            continue
            
        targets = []

        # Three targets
        for target_number in range(3):
            
            start = 4 + target_number * 8
            target_data = radar_buffer[
                start:start + 8
            ]

            x_raw = target_data[0] | (target_data[1] << 8)
            y_raw = target_data[2] | (target_data[3] << 8)

            speed_raw = target_data[4] | (target_data[5] <<8)
            resolution = target_data[6] | (target_data[7] << 8)

            if resolution == 0:
                continue
                
            x = x_raw & 0x7FFF

            if not (x_raw & 0x8000):
                x = -x
            
            y = y_raw - 0x8000

            distance = math.sqrt(x * x + y * y)


            # Ignore targets beyond 6 meters
            if distance <= 6000:
                targets.append(
                    (x, y, distance)
                )
        
        send_targets(targets)
        
        if targets != last_targets:
            print("TARGETS:", targets)
            last_targets = targets

        #Remove processed frame
        radar_buffer = radar_buffer[30:]

###################################
#            MAIN LOOP            #
###################################

while True:

    if connected_handle is not None:
        now = time.ticks_ms()
        
        if (
            status_attempts < 5
            and time.ticks_diff(
                now,
                last_status_time
            ) >= 1000
        ):

            try:
                if wifi_connected:
                    message = (
                        "WIFI_CONNECTED:"
                        + str(wifi_rssi)
                    )
                
                else:
                    if wifi_rssi is not None:
                        message = (
                            "WIFI_FAILED:"
                            +str(wifi_rssi)
                        )
                    
                    else:
                        message = "WIFI_FAILED: NONE"


                ble.gatts_notify(
                    connected_handle,
                    tx_handle,
                    message.encode()
                )

                status_attempts += 1
                last_status_time = now

                print(
                    "SENT",
                    message
                )

            except Exception as error:
                print(
                    "BLE SEND ERROR:",
                    error
                )

    read_radar()

    time.sleep_ms(50)