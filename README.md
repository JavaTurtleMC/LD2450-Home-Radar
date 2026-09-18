# LD2450 Home Radar
<img src="https://img.shields.io/badge/License-MIT-white?style=flat&logo=github" alt="Badge"> <img src="https://img.shields.io/badge/Operating%20System%20Tested-Windows_11%20%2F%20Linux-blue?style=flat&logo=github" alt="Badge">

Real-time target tracking radar module within a specific area (usually up to 6 meters and 120 degrees range). Measurement of a target's distance, angle, and speed.
> [!TIP]
> If this project helped you out, please consider starring the repository or letting others know about it. It is my first project and I hope it helps you.

## Overview
LD2450 radar code designed to work with ESP32-WROOM-32U with MicroPython 1.29.0.

> [!IMPORTANT]
> I have only tested the code on the things listed below. If you use something else, please be aware that you may have to adjust your code.

My Setup:
- Arch Linux + Hyprland
- HLK-LD2450 Radar
- ESP32-WROOM-32U Microcontroller
- MicroPython 1.29.0 Firmware
- Python + PySide6 Application

Radar Features:
- Bluetooth Low Energy and Wifi
- 6 metres range
- 120° field of view
- 3 maximum targets

## Features
* **Real-time target tracking:** Tracks up to 3 entities at once.
* **Custom PySide6 radar interface:** The design of the radar is based on [this video](https://www.youtube.com/watch?v=6afM9WfYh6I&list=WL&index=6)
* **Distance rings from 1m to 6m:** Increments to help the user see exactly how close the target is.
* **120° angle display:** The same angle as the real radar, to maximize the display on the screen.
* **Up to 3 detected targets:** Do I even need to explain this?
* **Bluetooth and Wifi:** It scans for Bluetooth, then Wifi. It will keep the second one as a fallback/failsafe.
* **Offline screen when no connection:** Displays an "Offline.png" to show you that it, in fact, can not connect.

## Requirements
HARDWARE
- Radar: HLK-LD2450
- Microchip: ESP32-WROOM-32U
- LD2450 antenna (Recommended)
- ESP32 antenna (Highly recommended)
- Power and wiring

> [!IMPORTANT]
> The antennas are highly recommended. From my testing, I get about -80 dBm using Bluetooth without the antenna, while getting -40 dBm with it.
> Your results may vary from mine. I am just letting you know what to expect.


SOFTWARE
- OS: Arch Linux, Windows 11 (Only tested it on these two. Cannot guarantee results on other operating systems.)
- WM: Hyprland (If you are on Windows you can ignore this. It should work on other WM's but I cannot guarantee results.)
- Python 3.13+
- PySide6
- Bleak
- MicroPython 1.29.0
- A computer with Bluetooth Low Energy support

> [!NOTE]
> The ESP32 code was tested specifically on an ESP32-WROOM-32U. Other ESP32 boards may require changes to the UART pins or configuration.

## Version Requirement
> [!IMPORTANT]
> As of v1.1.0 "Stable", a ***separate*** file named `SENSITIVE.py` must be added manually.

This file is intentionally excluded from the repository because it contains private information.

## SENSITIVE.py
> [!TIP]
> Create a file named `SENSITIVE.py` and place it in the same folder as your `main.py` (The radar main.py).
> Use this format:
> ```
> ESP32_ADDRESS = ""
> 
> IMAGE_PATH = ""
> 
> WIFI_SSID = ""
> 
> WIFI_PASSWORD = ""
> ```
> Add your info in between the quotation marks. Yes, keep the quotation marks.

## Private Information
> [!CAUTION]
> `SENSITIVE.py` contains your private information. Do not share that file online.

## How Do I Rename SENSITIVE.py?
> [!TIP]
> If you rename `SENSITIVE.py`, make sure to change the import line in both of the `main.py` files (radar and esp32 folder).
> For example, `from SENSITIVE import ESP32_ADDRESS` may become `from Passwords import ESP_ADDRESS`

## Setup
- [ ] Flash ESP32 and install MicroPython 1.29.0 on the ESP32.
- [ ] Connect the LD2450 to the ESP32. The current version is: LD2450 RX → ESP32 GPIO 17, LD2450 TX → ESP32 GPIO 16, Baud rate → 256000, and GND → GND. (I am not an electrical engineer I do not know much about electricity, please be careful.)

The next step is split into two instructions, depending on your version. For users on `v1.0.0`, follow this:
- [ ] Open `ESP32/main.py` (There are 2 main.py. Use the one that is nested under ESP32) and enter your wifi credentials. This is private wifi so don't share it.

For users who cloned my repository, you are most likely using a newer build such as `v1.1.0 "Stable"` or higher. Use this instead:
- [ ] Create `SENSITIVE.py` and insert your credentials there. Do not share your private information online.

Now, you can just continue as normal:
- [ ] Install bleak and Pyside6 with "pip install bleak PySide6".
- [ ] Run python main.py (The larger one that is ***NOT*** nested.)

> [!NOTE]
> To use the radar, just run the `main.py` that is ***NOT*** nested. This is the file that is much longer than the other one.
> You must upload the `main.py` (the ***shorter*** one, nested under ***ESP32***) to the microcontroller. This code must be reuploaded when you update it.

> [!TIP]
> If it says you are missing dependencies in Python, you may need Bleak and PySide6. I also said it right above you in the setup checklist.
 

The ESP32 continuously reads LD2450 target frames, extracts the target coordinates, and sends them to the desktop application using BLE notifications.
The desktop application converts those coordinates into positions on the radar display.

> [!WARNING]
> Use at your own risk. I am not a professional, and I do this for a hobby.
> This is my first repo, there are many things I can change. Please do let me know what I can fix.

## License

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

