import sys
import math
import asyncio
from bleak import BleakScanner, BleakClient
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QPixmap

ESP32_NAME = "Home Radar"
ESP32_ADDRESS = "esp32 mac address"

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
        self.targets = targets
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







    def paintEvent(self, event):
        
        painter = QPainter(self)

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
            image = QPixmap("image here")

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

            dot_size = max(8 * scale, 12 * scale)
            painter.drawEllipse(
                target_x - dot_size / 2,
                target_y - dot_size / 2,
                dot_size,
                dot_size
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

        






if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())