# LD2450 Home Radar
Target tracking involves real-time tracking of the position of a (moving) target within a specific area, enabling measurement of the target’s distance, angle and speed (relative to the sensor).

## 📖 Overview
LD2450 radar code designed to work with ESP32-WROOM-32U with MicroPython 1.29.0.

My Setup:
- Arch Linux + Hyprland
- HLK-LD2450 Radar
- ESP32-WROOM-32U Microcontroller
- MicroPython 1.29.0 Firmware
- Python + PySide6 Application
- Bluetooth Low Energy and Wifi
- 6 metres range
- 120° field of view
- 3 maximum targets

## ✨ Features
* **Real-time target tracking:** Tracks up to 3 entities at once.
* **Custom PySide6 radar interface:** The design of the radar is based on [this video](https://www.youtube.com/watch?v=6afM9WfYh6I&list=WL&index=6)
* **Distance rings from 1m to 6m:** Increments to help the user see exactly how close the target is.
* **120° angle display:** The same angle as the real radar, to maximize the display on the screen.
* **Up to 3 detected targets:** Do I even need to explain this?
* **Bluetooth and Wifi:** It scans for Bluetooth, then Wifi. It will keep the second one as a fallback/failsafe. (Intended process. Might be wrong. I didn't check.)
* **Offline screen when no connection:** Displays an "Offline.png" to show you that it, in fact, can not connect.

## 🧾 Requirements
HARDWARE
- Radar: HLK-LD2450
- Microchip: ESP32-WROOM-32U
- LD2450 antenna (Recommended)
- ESP32 antenna (I haven't tested)
- Power and wiring

SOFTWARE
- OS: Arch Linux (I tested it on this. Haven't tested Windows. Not like anyone is gonna see this repo anyways.)
- WM: Hyprland (Again, the resizing feature was designed on Hyprland. Maybe it works on Windows?)
- Python 3.13+
- PySide6
- Bleak
- MicroPython 1.29.0
- A computer with Bluetooth Low Energy support

NOTE: The ESP32 code was tested specifically on an ESP32-WROOM-32U. Other ESP32 boards may require changes to the UART pins or configuration.

## 🔧 Setup
- [ ] Flash ESP32 and install MicroPython 1.29.0 on the ESP32.
- [ ] Connect the LD2450 to the ESP32. The current version is: LD2450 RX → ESP32 GPIO 17, LD2450 TX → ESP32 GPIO 16, Baud rate → 256000, and GND → GND. (I am not an electrical engineer I am not liable if I am wrong.)
- [ ] Open ESP32/main.py (There are 2 main.py. Use the one that is nested under ESP32) and enter your wifi credentials. This is private wifi so don't share it.
- [ ] Install bleak and Pyside6 with "pip install bleak PySide6".
- [ ] Run python main.py (The normal one. The one that's literally 900 ish lines idk. Give or take.)
- [ ] Oh right also change the image at "image = QPixmap" and shove in your image location. The file is main.py (The larger one).
- [ ] Oh also same big main.py file, you gotta add your ESP32 address. I forgot how to figure that out so good luck. Just google how to find it or something.

The ESP32 continuously reads LD2450 target frames, extracts the target coordinates, and sends them to the desktop application using BLE notifications.
The desktop application converts those coordinates into positions on the radar display.

## ⚠️ Disclaimer
> I am not liable for anything. Use at your own risk. I am not a professional I do this for a hobby.
> This is my first repo.
> Heavily under development. However, it functions well enough to be published.
> The Wi-Fi section is still under development and I have not tested that yet. I currently get around -70 dBm, so an external antenna may be useful.

## 📜 License

MIT License

Copyright (c) 2026 JavaTurtleMC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

