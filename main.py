import sys
import math
import asyncio
import time
from bleak import BleakScanner, BleakClient
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QPixmap
from SENSITIVE import ESP32_ADDRESS, IMAGE_PATH

ESP32_NAME = "Home Radar"
# ESP32 Mac address has been moved to "SENSITIVE.py"

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"


######################################################################
#                     BLUETOOTH          WORKER                      #
######################################################################

class BluetoothWorker(QThread):
    connection_result = Signal(bool, str)
    status_message = Signal(str)
    wifi_result = Signal(str, object)
    bluetooth_signal = Signal(object)
    radar_targets = Signal(object)

    def __init__(self):
        super().__init__()
        self.client = None
        self.running = True
        self.wifi_result_recieved = False


    def stop(self):
        self.running = False
    
    def run(self):
        try:
            asyncio.run(self.connect_bluetooth())
        
        except Exception as error:
            print("Worker error:", error)
    
    async def connect_bluetooth(self):
        self.status_message.emit("SCANNING FOR DEVICE...")


        scanner = BleakScanner()
        await scanner.start()

        device = None
        bluetooth_rssi = None
    
        for _ in range(100):
            await asyncio.sleep(0.1)

            for found_device, advertisement in (scanner.discovered_devices_and_advertisement_data.values()):
                if found_device.address == ESP32_ADDRESS:
                    device = found_device
                    bluetooth_rssi = advertisement.rssi
                    break
        
            if device is not None:
                break
    
        await scanner.stop()


        if device is None:
            self.connection_result.emit(
                False,
                "BLUETOOTH DEVICE NOT FOUND"
            )

            return
    
        print(
            "Bluetooth RSSI:",
            bluetooth_rssi,
            "dBm"
        )

        self.bluetooth_signal.emit(
            bluetooth_rssi
        )

        self.status_message.emit(
            "BLUETOOTH DEVICE FOUND"
        )

        self.status_message.emit(
            "CONNECTING VIA BLUETOOTH..."
        )

        try:

            self.client = BleakClient(device)
            await self.client.connect()

            if not self.client.is_connected:
                self.connection_result.emit(
                    False,
                    "BLUETOOTH CONNECTION FAILED"
                )

                return
        
            await self.client.start_notify(
                UART_TX_UUID,
                self.handle_notification
            )

            self.connection_result.emit(
                True,
                "Bluetooth"
            )

            await asyncio.sleep(5)
            if not self.wifi_result_recieved:
                self.wifi_result.emit("failed", "NONE")

            while self.client.is_connected and self.running:
                await asyncio.sleep(0.5)
        
            print("Bluetooth disconnected")

        except Exception as error:
            print("Bluetooth error:", error)

            self.connection_result.emit(
                False,
               "BLUETOOTH CONNECTION FAILED"
            )
        
        finally:
            if self.client is not None:
                try:
                    if self.client.is_connected:
                        await self.client.stop_notify(UART_TX_UUID)
                        await self.client.disconnect()
                    
                except Exception as error:
                    print("Bluetooth cleanup error:", error)
    



    def handle_notification(self, sender, data):

        try:
            message = data.decode().strip()
        
        except UnicodeDecodeError:
            message = None
        
        if message is not None:
            message = message.strip()
            print("ESP32:", message)

            if message.startswith("WIFI_CONNECTED:"):
                rssi = message.split(":", 1)[1]
                self.wifi_result_recieved = True
                self.wifi_result.emit("connected", rssi)
                return
        
            elif message.startswith("WIFI_FAILED"):
                rssi = message.split(":", 1)[1]
                self.wifi_result_recieved = True
                self.wifi_result.emit("failed", rssi)
                return


        # Radar Packet
        if len(data) < 1:
            return

        target_count = data[0]

        if target_count > 3:
            return
        
        targets = []

        offset = 1

        for _ in range(target_count):
            if offset + 4 > len(data):
                return
            
            x = int.from_bytes(
                data[offset:offset + 2],
                "little",
                signed = True
            )

            y = int.from_bytes(
                data[offset + 2:offset + 4],
                "little",
                signed = True
            )

            targets.append(
                (x, y)
            )

            offset += 4

        self.radar_targets.emit(targets)


######################################################################
#                        MAIN         WINDOW                         #
######################################################################



class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Home Radar")
        self.setStyleSheet("background-color: #000000;")



        self.online = False
        self.connection_type = "Disconnected"
        self.fallback = "Wifi"
        self.booting = True
        self.connection_status = "CONNECTING VIA WIFI..."

        self.signal_strength = None
        self.signal_type = "Bluetooth"

        self.targets = []

        self.target_trails = []
        self.target_directions = {}
        self.target_ids = {}
        
        self.start_time = time.monotonic()
        self.frame_count = 0
        self.fps = 0
        self.fps_time = self.start_time

        self.target_slots = [1, 2, 3]
        self.trail_lifetime = 3.0
        self.trail_timer = QTimer(self)
        self.trail_timer.timeout.connect(self.update)
        self.trail_timer.start(25)

        self.bluetooth_worker = BluetoothWorker()


        self.bluetooth_worker.status_message.connect(
            self.update_connection_status
        )


        self.bluetooth_worker.connection_result.connect(
            self.bluetooth_finished
        )


        self.bluetooth_worker.wifi_result.connect(
            self.wifi_result
        )

        self.bluetooth_worker.bluetooth_signal.connect(
            self.update_bluetooth_signal
        )

        self.bluetooth_worker.radar_targets.connect(
            self.update_targets
        )

        self.bluetooth_worker.start()

       
    def closeEvent(self, event):
        self.bluetooth_worker.stop()

        if self.bluetooth_worker.isRunning():
            self.bluetooth_worker.wait()
        
        event.accept()

    def update_targets(self, targets):
        now = time.monotonic()

        self.targets = targets
        current_directions = {}
        current_ids = {}

        for trail in self.target_trails:
            trail["footprints"] = [
                footprint
                for footprint in trail["footprints"]
                if now - footprint["time"] <= self.trail_lifetime
            ]
        
        self.target_trails = [
            trail
            for trail in self.target_trails
            if now - trail.get("last_seen", now) <= 1.0
        ]
        
        used_trails = set()

        for x, y in targets:
            best_trail = None
            best_distance = None

            for index, trail in enumerate(self.target_trails):
                if index in used_trails:
                    continue

                last_x, last_y = trail["last_position"]

                distance = math.sqrt(
                    (x - last_x) ** 2
                    + (y - last_y) ** 2
                )

                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_trail = index
                
            if best_trail is not None and best_distance <= 1000:
                trail = self.target_trails[best_trail]
                trail["last_seen"] = now
                last_x, last_y = trail["last_position"]

                previous_sample = trail.get("sample_position")
                previous_sample_time = trail.get("sample_time")

                # Target Speed
                if previous_sample is not None and previous_sample_time is not None:
                    previous_x, previous_y = previous_sample

                    sample_distance = math.sqrt((x - previous_x) ** 2 + (y - previous_y) ** 2)
                    sample_time = now - previous_sample_time

                    if sample_time > 0:
                        trail["speed"] = (sample_distance / sample_time) / 10

                        previous_distance = math.sqrt(previous_x ** 2 + previous_y ** 2)
                        current_distance = math.sqrt(x ** 2 + y ** 2)

                        if sample_distance < 10:
                            trail["motion"] = ""
                            trail["speed"] = 0

                        elif current_distance < previous_distance:
                            trail["motion"] = "IN"
                        elif current_distance > previous_distance:
                            trail["motion"] = "OUT"
                
                trail["sample_position"] = (x, y)
                trail["sample_time"] = now


                if best_distance >= 80:
                    dx = x - last_x
                    dy = y - last_y

                    movement_distance = math.sqrt(
                        dx ** 2 + dy ** 2
                    )

                    if movement_distance > 0:
                        trail["last_direction"] = (
                            dx / movement_distance,
                            dy / movement_distance
                        )

                        trail["footprints"].append(
                            {
                                "position": (x, y),
                                "direction": trail["last_direction"],
                                "time": now
                            }
                        )

                    trail["last_position"] = (x, y)

                current_directions[(x, y)] = trail["last_direction"]
                current_ids[(x, y)] = trail["id"]

                used_trails.add(best_trail)

            else:
                used_ids = {
                    trail["id"]
                    for trail in self.target_trails
                }

                free_ids = [
                    target_id
                    for target_id in self.target_slots
                    if target_id not in used_ids
                ]

                if not free_ids:
                    continue

                new_target_id = free_ids[0]

                self.target_trails.append(
                    {
                        "last_position": (x, y),
                        "last_direction": (0, -1),
                        "footprints": [],
                        "id": new_target_id,

                        "sample_position": (x, y),
                        "sample_time": now,
                        "speed": 0,
                        "motion": "IN",
                        "last_seen": now
                    }
                )

                current_directions[(x, y)] = (0, -1)
                current_ids[(x, y)] = new_target_id

                used_trails.add(
                    len(self.target_trails) - 1
                )
        
        self.target_trails = [
            trail
            for trail in self.target_trails
            if trail["footprints"] or trail["last_position"] is not None
        ]

        self.target_directions = current_directions
        self.target_ids = current_ids

        self.update()

    def update_bluetooth_signal(self, rssi):
        self.signal_strength = rssi
        self.signal_type = "Bluetooth"


    def update_connection_status(self, message):
        self.connection_status = message
        self.update()

    def bluetooth_finished(self, success, connection_type):
        if success:
            self.connection_status = "CHECKING WIFI..."
            self.update()

        else:
            self.online = False
            self.connection_type = "Disconnected"
            self.fallback = "None"
            self.connection_status = connection_type
            self.booting = False

            self.update()
    
    def wifi_check_timeout(self):
        print("Wifi check timed out")
        self.online = True
        self.connection_type = "AUTO (Bluetooth)"
        self.fallback = "Unavailable"
        self.connection_status = "CONNECTION ACTIVE"
        self.signal_type = "Bluetooth"

        self.finish_boot()
        
    def finish_boot(self):
        self.booting = False
        self.update()


    def wifi_result(self, result, rssi):
        if result == "connected":

            self.online = True
            self.connection_type = "AUTO (Wifi)"
            self.fallback = "Bluetooth"
            self.connection_status = "CONNECTION ACTIVE"
            self.signal_type = "Wifi"

            try:
                self.signal_strength = int(rssi)

            except(ValueError, TypeError):
                self.signal_strength = None
        
        else:

            self.online = True
            self.connection_type = "AUTO (Bluetooth)"
            self.fallback = "Unavailable"
            self.connection_status = "CONNECTION ACTIVE"

            self.signal_type = "Bluetooth"

            if rssi == "NONE":
                self.signal_strength = None
            
            else:
                try:
                    self.signal_strength = int(rssi)
                
                except(ValueError, TypeError):
                    self.signal_strength = None
        
        self.finish_boot()



    def get_target_info(self, x, y):
        target_id = self.target_ids.get((x, y), 0)
        target_distance = math.sqrt(x ** 2 + y ** 2)
        target_angle = math.degrees(math.atan2(x, y))

        target_speed = 0
        target_motion = "IN"

        for trail in self.target_trails:
            if trail.get("id") == target_id:
                target_speed = trail.get("speed", 0)
                target_motion = trail.get("motion", "IN")
                break
        
        return (
            target_id,
            target_distance,
            target_angle,
            target_speed,
            target_motion
        )





    def paintEvent(self, event):
        
        painter = QPainter(self)

        self.frame_count += 1
        now = time.monotonic()

        if now - self.fps_time >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.fps_time = now

        ###################################
        #           Boot Screen           #
        ###################################

        if self.booting:
            
            # Boot Screen Rectangle
            painter.setPen(QColor("#a6e3a1"))
            painter.setBrush(QColor("#000000"))

            painter.drawRect(
                50,
                50,
                self.width() - 100,
                self.height() - 100
            )

            # Title
            painter.setFont(
                QFont("JetBrainsMono Nerd Font", 70)
            )

            painter.drawText(
                50,
                self.height() / 3,
                self.width() - 100,
                70,
                Qt.AlignmentFlag.AlignCenter,
                "LD2450 RADAR"
            )

            # Subtitle
            painter.setFont(
                QFont("JetBrainsMono Nerd Font", 27)
            )

            painter.drawText(
                50,
                self.height() / 3 + 125,
                self.width() - 100,
                40,
                Qt.AlignmentFlag.AlignCenter,
                "24GHz HUMAN MOTION TRACKING"
            )

            # Dotted Line
            painter.setPen(QColor("#a6e3a1"))
            painter.setBrush(QColor("#a6e3a1"))
            
            boot_dotted_line_width = 800
            boot_dotted_line_start = (self.width() - boot_dotted_line_width) / 2

            dot_y = self.height() / 3 + 210

            painter.setClipRect(
                50,
                50,
                self.width() - 100,
                self.height() - 100
            )

            for x in range(round(boot_dotted_line_start), round(boot_dotted_line_start + boot_dotted_line_width), 25):
                painter.drawEllipse(x, dot_y, 5, 5)
            
            painter.setClipping(False)


            # Connection Status

            painter.setFont(
                QFont("JetBrainsMono Nerd Font", 25)
            )

            painter.drawText(
                50,
                dot_y + 200,
                self.width() - 100,
                40,
                Qt.AlignmentFlag.AlignCenter,
                self.connection_status
            )


            return


        ###################################
        #             Radar               #
        ###################################
        
        

        if not self.online:
            image = QPixmap(IMAGE_PATH) # Path has been moved to SENSITIVE.py

            scaled_offline_image = image.scaled(
                self.width() * 0.5,
                self.height() * 0.5,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            painter.drawPixmap(
                (self.width() - scaled_offline_image.width()) / 2,
                (self.height() - scaled_offline_image.height()) / 2,
                scaled_offline_image
            )
            return
            

        pen = QPen(QColor("#a6e3a1"))
        pen.setWidth(3)

        painter.setPen(pen)
        painter.setBrush(QColor("#a6e3a1"))

        center_x = self.width() / 2
        center_y = self.height() * 0.97

        radius = round(self.height() * 0.8)
        angle = math.radians(60)
        max_radius = (self.width() * 0.95) / math.sin(angle) / 2        # Only let the radar take up 95% of the available width
        radius = min(radius, max_radius)
        scale = radius / 1000                                           # Radius controls scale. 1000 radius = 1.00 scale, 500 radius = 0.50 scale
        blind_radius = radius * 0.03

        # Top Bar
        top_bar_height = round(55 * scale)

        painter.setPen(QColor("#a6e3a1"))
        painter.setBrush(QColor("#a6e3a1"))

        painter.drawRect(
            0,
            0,
            self.width(),
            top_bar_height
        )

        # Top Bar Text
        painter.setPen(QColor("#000000"))

        top_bar_font = QFont("JetBrainsMono Nerd Font", round(20 * scale))
        painter.setFont(top_bar_font)

        # Left Text
        painter.drawText(
            round(20 * scale),
            0,
            round(self.width() * 0.5),
            top_bar_height,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "LD2450 RADAR"
        )

        # Target Info Boxes
        target_box_x = round(16 * scale)
        target_box_y = top_bar_height + round(12 * scale)

        target_box_width = round(210 * scale)
        target_box_height = round(105 * scale)

        target_box_gap = round(12 * scale)

        active_targets = {}

        for x, y in self.targets[:3]:
            target_id = self.target_ids.get((x, y), 0)

            if target_id in (1, 2, 3):
                active_targets[target_id] = (x, y)
        
        for target_id in self.target_slots:
            box_x = (target_box_x + (target_id - 1) * (target_box_width + target_box_gap))
            box_y = target_box_y

            target_data = active_targets.get(target_id)

            if target_data is None:
                empty_pen = QPen(QColor("#696969"))
                empty_pen.setStyle(Qt.PenStyle.DotLine)
                empty_pen.setWidth(max(1, round(2 * scale)))

                painter.setPen(empty_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                painter.drawRect(
                    box_x,
                    box_y,
                    target_box_width,
                    target_box_height
                )
            
                label_width = round(38 * scale)
                label_height = round(24 * scale)

                painter.drawRect(
                    box_x,
                    box_y,
                    label_width,
                    label_height
                )

                painter.setPen(QColor("#696969"))
                label_font = QFont("JetBrainsMono Nerd Font", round(13 * scale))
                painter.setFont(label_font)

                painter.drawText(
                    box_x,
                    box_y,
                    label_width,
                    label_height,
                    Qt.AlignmentFlag.AlignCenter,
                    f"T{target_id}"
                )

                empty_font = QFont("JetBrainsMono Nerd Font", round(18 * scale))
                painter.setFont(empty_font)
                painter.setPen(QColor("#696969"))

                painter.drawText(
                    box_x,
                    box_y,
                    target_box_width,
                    target_box_height,
                    Qt.AlignmentFlag.AlignCenter,
                    "NO TARGET"
                )

                continue

            # Active Target
            x, y = target_data
            distance = math.sqrt(x ** 2 + y ** 2)
            target_angle = math.degrees(math.atan2(x, y))

            target_speed = 0
            target_motion = "IN"

            for trail in self.target_trails:
                if trail.get("id") == target_id:
                    target_speed = trail.get("speed", 0)
                    target_motion = trail.get("motion", "IN")
                    break
            
            box_x = (target_box_x + (target_id - 1) * (target_box_width + target_box_gap))
            box_y = target_box_y

            # Box Border
            box_pen = QPen(QColor("#a6e3a1"))
            box_pen.setWidth(max(1, round(2 * scale)))
            painter.setPen(box_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.drawRect(box_x, box_y, target_box_width, target_box_height)

            # Target Green Label
            target_label_width = round(38 * scale)
            target_label_height = round(24 * scale)

            painter.setPen(QColor("#a6e3a1"))
            painter.setBrush(QColor("#a6e3a1"))

            painter.drawRect(box_x, box_y, target_label_width, target_label_height)

            # Target Black Text
            painter.setPen(QColor("#000000"))
            target_label_font = QFont("JetBrainsMono Nerd Font", round(13 * scale))

            painter.setFont(target_label_font)

            painter.drawText(box_x, box_y, target_label_width, target_label_height, Qt.AlignmentFlag.AlignCenter, f"T{target_id}")

            # Angle Text
            angle_font = QFont("JetBrainsMono Nerd Font", round(11 * scale))
            painter.setFont(angle_font)
            angle_text = f"{-target_angle:+.1f}°"
            angle_metrics = QFontMetrics(painter.font())
            angle_width = angle_metrics.horizontalAdvance(angle_text)
            painter.setPen(QColor("#a6e3a1"))

            painter.drawText(
                box_x
                + target_box_width
                - angle_width
                - round(8 * scale),
                
                box_y
                + round(3 * scale),
                angle_width,
                target_label_height,
                
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, angle_text)

            # Distance Text
            distance_font = QFont("JetBrainsMono Nerd Font", round(24 * scale))
            painter.setFont(distance_font)
            distance_text = (f"{distance / 1000:.2f}m")
            painter.setPen(QColor("#a6e3a1"))

            painter.drawText(
                box_x + round(8 * scale),
                box_y + round(30 * scale),
                target_box_width - round(16 * scale),
                round(35 * scale),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                distance_text
            )

            # Speed
            speed_font = QFont("JetBrainsMono Nerd Font", round(12 * scale))
            painter.setFont(speed_font)

            if target_speed < 10:
                speed_text = "0 cm/s"
            
            else:
                speed_text = (
                    f"{target_speed:.0f} cm/s "
                    f"{target_motion}"
                )

            painter.drawText(
                box_x + round(8 * scale),
                box_y + round(70 * scale),
                target_box_width - round(16 * scale),
                round(25 * scale),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                speed_text
            )



        # Target Count
        painter.setPen(QColor("#000000"))
        top_bar_font = QFont("JetBrainsMono Nerd Font", round(20 * scale))
        painter.setFont(top_bar_font)


        target_count = len(self.targets)

        if target_count == 1:
            target_text = "1 TARGET"
        
        else:
            target_text = f"{target_count} TARGETS"

        # Uptime
        uptime = int(time.monotonic() - self.start_time)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60

        uptime_text = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        # Right Text
        right_text = (
            f"{target_text}   "
            f"{self.fps} FPS   "
            f"{uptime_text}"
        )

        right_metrics = QFontMetrics(painter.font())
        right_text_width = right_metrics.horizontalAdvance(right_text)

        painter.drawText(
            self.width() - right_text_width - round(20 * scale),
            0,
            right_text_width,
            top_bar_height,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            right_text
        )

        pen.setWidth(3)
        painter.setPen(pen)


        # Left Line
        end_x = center_x + radius * math.sin(angle)
        end_y = center_y - radius * math.cos(angle)

        painter.drawLine(
            center_x,
            center_y,
            end_x,
            end_y
        )

        # Right Line
        end_x = center_x - radius * math.sin(angle)
        end_y = center_y - radius * math.cos(angle)

        painter.drawLine(
            center_x,
            center_y,
            end_x,
            end_y
        )

        painter.setBrush(QColor("#a6e3a1"))

        # Sector Arc
        painter.drawArc(
            center_x - radius,
            center_y - radius,
            radius * 2,
            radius * 2,
            30 * 16,                                                    # 90 degrees is up. Range is 120 degrees total. 90 - (120/2) = 30
            120 * 16
        )

        

        # Internal Guide Lines
        dashed_pen = QPen(QColor("#a6e3a1"))
        dashed_pen.setStyle(Qt.PenStyle.DashLine)
        dashed_pen.setDashPattern([2, 10])
        dashed_pen.setWidth(2)
        painter.setPen(dashed_pen)
        
        for angle in [-30, 0, 30]:
            angle = math.radians(angle)

            end_x = center_x + radius * math.sin(angle)
            end_y = center_y - radius * math.cos(angle)
        
            painter.drawLine(
                center_x,
                center_y,
                end_x,
                end_y
            )
        
        
        # Filled Sector
        painter.drawPie(
            center_x - blind_radius,
            center_y - blind_radius,
            blind_radius * 2,
            blind_radius * 2,
            30 * 16,
            120 * 16
        )

        # Repeated Rings
        for distance in range(1, 7):
            ring_radius = blind_radius + (radius - blind_radius) * distance / 6

            painter.drawArc(
                center_x - ring_radius,
                center_y - ring_radius,
                ring_radius * 2,
                ring_radius * 2,
                30 * 16,
                120 * 16
            )

        # Distance Labelling
        painter.setFont(QFont("JetBrainsMono Nerd Font", round(18 * scale)))

        for distance in range(1,6):
            ring_radius = blind_radius + (radius - blind_radius) * distance / 6
            
            label_x = center_x + blind_radius
            label_y = center_y - ring_radius + 6 * scale

            painter.setPen(QColor("#000000"))
            painter.setBrush(QColor("#000000"))

            label_size = 50 * scale

            painter.drawEllipse(
                label_x - label_size / 2 + 10 * scale,
                label_y - label_size / 2 - 2 * scale,
                label_size,
                label_size
            )

            painter.setPen(QColor("#a6e3a1"))

            painter.drawText(
                label_x,
                label_y,
                f"{distance}m"
            )


        # Angle Labelling
        label_radius = radius * 0.95                                    # Gap between line and text
        font_size = round(20 * scale)
        painter.setFont(QFont("JetBrainsMono Nerd Font", font_size))
        font_metrics = QFontMetrics(painter.font())

        for angle in [-60, -30, 0, 30, 60]:
            angle_radians = math.radians(angle)

            label_x = center_x + label_radius * math.sin(angle_radians)
            label_y = center_y - label_radius * math.cos(angle_radians)

            painter.setPen(QColor("#000000"))
            painter.setBrush(QColor("#000000"))

            label_size = 50 * scale

            painter.drawEllipse(
                label_x - label_size / 2,
                label_y - label_size / 2,
                label_size,
                label_size
            )

            painter.setPen(QColor("#a6e3a1"))
            angle_text = f"{angle}"
            text_width = font_metrics.horizontalAdvance(angle_text)
            text_height = font_metrics.height()

            painter.drawText(
                label_x - text_width / 2,
                label_y + text_height / 4,
                angle_text
            )

        # Angle Marks

        painter.setPen(pen)

        for angle in [-45, -30, -15, 0, 15, 30, 45]:

            angle_radians = math.radians(angle)

            inner_radius = radius * 0.98

            start_x = center_x + inner_radius * math.sin(angle_radians)
            start_y = center_y - inner_radius * math.cos(angle_radians)

            end_x = center_x + radius * math.sin(angle_radians)
            end_y = center_y - radius * math.cos(angle_radians)

            painter.drawLine(
                start_x,
                start_y,
                end_x,
                end_y
            )
    
        ###################################
        #        Connection Status        #
        ###################################

        painter.setFont(
            QFont("JetBrainsMono Nerd Font", round(50 * scale))
        )

        painter.drawText(
            (30 * scale),
            self.height() - (260 * scale),
            "RANGE 6.0m"
        )

        painter.setFont(
            QFont("JetBrainsMono Nerd Font", round(27 * scale))
        )

        if self.online:

            painter.drawText(
                (30 * scale),
                self.height() - (190 * scale),
                "● CONNECTION ACTIVE"
            )
        
        else:
            painter.drawText(
                (30 * scale),
                self.height() - (190 * scale),
                "Offline"
            )

        # Signal text too wide
        
        #if self.signal_strength is not None:
        #    painter.drawText(
        #        (30 * scale),
        #        self.height() - (120 * scale),
        #        f"TYPE:     {self.connection_type} ({self.signal_strength} dBm)"
        #    )
        #
        #else:

        painter.drawText(
            (30 * scale),
            self.height() - (120 * scale),
            f"TYPE:     {self.connection_type}"
        )

        painter.drawText(
            (30 * scale),
            self.height() - (50 * scale),
            f"FALLBACK: {self.fallback}"
        )

        # Target Trails
        now = time.monotonic()
        for trail in self.target_trails:

            for footprint in trail["footprints"]:
                age = now - footprint["time"]

                if age > self.trail_lifetime:
                    continue

                x, y = footprint["position"]

                distance = math.sqrt(x * x + y * y)

                if distance <= 0 or distance > 6000:
                    continue

                target_radius = (
                    (distance / 6000)
                    * (radius - blind_radius)
                    + blind_radius
                )

                target_angle = math.atan2(x, y)

                if abs(target_angle) > math.radians(60):
                    continue

                footprint_x = (
                    center_x
                    -  target_radius * math.sin(target_angle)
                )

                footprint_y = (
                    center_y
                    - target_radius * math.cos(target_angle)
                )


                footprint_pen = QPen(QColor("#a6e3a1"))
                footprint_pen.setWidth(max(2, round(3 * scale)))

                painter.setPen(footprint_pen)

                direction_x, direction_y = footprint["direction"]
                footprint_length = 5 * scale

                painter.drawLine(
                    footprint_x - direction_x * footprint_length / 2,
                    footprint_y - direction_y * footprint_length / 2,
                    footprint_x + direction_x * footprint_length / 2,
                    footprint_y + direction_y * footprint_length / 2
                )



        # Targets
        target_pen = QPen(QColor("#a6e3a1"))
        target_pen.setWidth(round(12*scale))

        painter.setPen(target_pen)
        painter.setBrush(QColor("#a6e3a1"))

        for x, y in self.targets:
            distance = math.sqrt(x * x + y * y)
            
            if distance <= 0:
                continue

            if distance > 6000:
                continue
            
            # Convert millimetres to screen radius
            target_radius = (distance / 6000) * (radius - blind_radius) + blind_radius

            # Convert X/Y into an angle. 0 degrees = Straight
            target_angle = math.atan2(x, y)

            # Ignore targets outside +/- 60 degree FOV
            if abs(target_angle) > math.radians(60):
                continue

            target_x = (center_x - target_radius * math.sin(target_angle))
            target_y = (center_y - target_radius * math.cos(target_angle))

            target_guide_pen = QPen(QColor("#a6e3a1"))
            target_guide_pen.setStyle(Qt.PenStyle.DashLine)
            target_guide_pen.setDashPattern([2, 10])
            target_guide_pen.setWidth(2)


            painter.setPen(target_guide_pen)

            painter.drawLine(
                center_x,
                center_y,
                target_x,
                target_y
            )

            dot_size = max(16 * scale, 24 * scale)
            painter.setPen(QPen(QColor("#a6e3a1")))
            painter.setBrush(QColor("#a6e3a1"))

            painter.drawEllipse(
                target_x - dot_size / 2,
                target_y - dot_size / 2,
                dot_size,
                dot_size
            )




            # Outer Circle Of Target

            target_marker_radius = (dot_size / 2) + 8

            ring_pen = QPen(QColor("#a6e3a1"))
            ring_pen.setWidth(round(3 * scale))
            painter.setPen(ring_pen)

            painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.drawEllipse(
                target_x - target_marker_radius,
                target_y - target_marker_radius,
                target_marker_radius * 2,
                target_marker_radius * 2
            )

            # Crosshair Marks
            crosshair_gap = 10 * scale
            crosshair_length = 10 * scale

            crosshair_pen = QPen(QColor("#a6e3a1"))
            crosshair_pen.setWidth(round(3 * scale))
            painter.setPen(crosshair_pen)



            # Top
            painter.drawLine(
                target_x,
                target_y - target_marker_radius - crosshair_gap,
                target_x,
                target_y - target_marker_radius
                - crosshair_gap
                - crosshair_length
            )

            # Right
            painter.drawLine(
                target_x + target_marker_radius + crosshair_gap,
                target_y,
                target_x + target_marker_radius
                + crosshair_gap
                + crosshair_length,
                target_y
            )
        
            # Bottom
            painter.drawLine(
                target_x,
                target_y + target_marker_radius + crosshair_gap,
                target_x,
                target_y + target_marker_radius
                + crosshair_gap
                + crosshair_length
            )

            # Left
            painter.drawLine(
                target_x - target_marker_radius - crosshair_gap,
                target_y,
                target_x - target_marker_radius
                - crosshair_gap
                - crosshair_length,
                target_y
            )

            # Target Tracker
            target_id = self.target_ids.get(
                (x, y),
                0
            )

            target_distance = distance / 1000

            target_text = f"T{target_id} {target_distance:.2f}m"

            target_font = QFont("JetBrainsMono Nerd Font", round(14 * scale))

            painter.setFont(target_font)
            font_metrics = QFontMetrics(painter.font())

            text_width = font_metrics.horizontalAdvance(target_text)
            text_height = font_metrics.height()

            box_padding_x = 8 * scale
            box_padding_y = 4 * scale

            box_width = text_width + box_padding_x * 2
            box_height = text_height + box_padding_y * 2

            box_x = target_x - box_width / 2

            box_y = (target_y - target_marker_radius - crosshair_gap - crosshair_length - box_height - 8 * scale)

            painter.setPen(QColor("#a6e3a1"))
            painter.setBrush(QColor("#a6e3a1"))

            painter.drawRect(
                box_x,
                box_y,
                box_width,
                box_height
            )

            painter.setPen(QColor("#000000"))

            painter.drawText(
                box_x,
                box_y,
                box_width,
                box_height,
                Qt.AlignmentFlag.AlignCenter,
                target_text
            )



            # Target Directional Arrow
            direction_x, direction_y = self.target_directions.get(
                (x, y),
                (0, -1)
            )

            screen_direction_x = -direction_x
            screen_direction_y = -direction_y

            arrow_start_distance = target_marker_radius + 8
            arrow_length = 18 * scale

            arrow_start_x = (target_x + screen_direction_x * arrow_start_distance)
            arrow_start_y = (target_y + screen_direction_y * arrow_start_distance)
            arrow_tip_x = (arrow_start_x + screen_direction_x * arrow_length)
            arrow_tip_y = (arrow_start_y + screen_direction_y * arrow_length)

            arrow_pen = QPen(QColor("#a6e3a1"))
            arrow_pen.setWidth(round(3 * scale))
            painter.setPen(arrow_pen)

            # Arrow Shaft
            painter.drawLine(
                arrow_start_x,
                arrow_start_y,
                arrow_tip_x,
                arrow_tip_y
            )

            # Arrow head
            arrow_head_length = 7 * scale
            arrow_head_width = 4 * scale

            perpendicular_x = -screen_direction_y
            perpendicular_y = screen_direction_x

            painter.drawLine(
                arrow_tip_x,
                arrow_tip_y,
                arrow_tip_x - screen_direction_x * arrow_head_length + perpendicular_x * arrow_head_width,
                arrow_tip_y - screen_direction_y * arrow_head_length + perpendicular_y * arrow_head_width
            )

            painter.drawLine(
                arrow_tip_x,
                arrow_tip_y,
                arrow_tip_x - screen_direction_x * arrow_head_length - perpendicular_x * arrow_head_width,
                arrow_tip_y - screen_direction_y * arrow_head_length - perpendicular_y * arrow_head_width
            )
        

        

        






if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())