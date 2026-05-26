#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

# ANSI colors helper
def color_print(text, color="white"):
    colors = {
        "green": "\033[0;32m",
        "red": "\033[0;31m",
        "yellow": "\033[0;33m",
        "blue": "\033[0;34m",
        "cyan": "\033[0;36m",
        "white": "\033[0m"
    }
    if os.name == 'nt':  # Windows command prompt colors workaround
        print(text)
    else:
        print(f"{colors.get(color, colors['white'])}{text}\033[0m")

def get_pio_path():
    bin_dir = Path(sys.executable).parent
    pio_name = "pio.exe" if os.name == "nt" else "pio"
    pio_path = bin_dir / pio_name
    if pio_path.exists():
        return str(pio_path)
    return "pio"

# USB vendor IDs for the USB-to-UART bridge chips used by ESP32 / Arduino boards.
ESP_COMPATIBLE_VIDS = {
    0x10C4,  # Silicon Labs CP210x (common on ESP32-CAM)
    0x1A86,  # QinHeng CH340/CH341 (common on ESP32 dev boards / clones)
    0x0403,  # FTDI
    0x303A,  # Espressif (native USB on ESP32-S2/S3/C3)
    0x067B,  # Prolific PL2303
    0x2341,  # Arduino
    0x2A03,  # Arduino (older)
    0x1B4F,  # SparkFun
    0x239A,  # Adafruit
}

# Substrings (lowercased) that identify a likely ESP32/Arduino USB-serial port
# when VID/PID metadata is unavailable.
ESP_COMPATIBLE_KEYWORDS = (
    "usbserial", "usbmodem", "wchusbserial", "slab", "cp210", "ch340",
    "ch341", "ftdi", "uart", "ttyusb", "ttyacm",
)

def get_serial_ports():
    try:
        import serial.tools.list_ports
        return list(serial.tools.list_ports.comports())
    except ImportError:
        color_print("Warning: pyserial is not available. Port autodetect disabled.", "yellow")
        return []

def is_esp_compatible(port):
    """Heuristic: is this port a likely ESP32/Arduino USB-serial device?"""
    if getattr(port, "vid", None) in ESP_COMPATIBLE_VIDS:
        return True
    haystack = f"{port.device} {port.description or ''} {getattr(port, 'hwid', '') or ''}".lower()
    return any(keyword in haystack for keyword in ESP_COMPATIBLE_KEYWORDS)

def select_port():
    all_ports = get_serial_ports()
    if not all_ports:
        return input("Please enter the serial port path manually (e.g. /dev/ttyUSB0 or COM3): ").strip()

    ports = [p for p in all_ports if is_esp_compatible(p)]
    showing_filtered = bool(ports)
    if not ports:
        color_print("No ESP32/Arduino-compatible ports detected; showing all serial ports.", "yellow")
        ports = all_ports

    while True:
        if showing_filtered:
            color_print("\nDetected ESP32/Arduino-compatible serial ports:", "cyan")
        else:
            color_print("\nDetected serial ports:", "cyan")
        for idx, port in enumerate(ports, 1):
            desc = f" - {port.description}" if port.description else ""
            print(f"  {idx}) {port.device}{desc}")
        show_all_option = showing_filtered and len(ports) < len(all_ports)
        manual_idx = len(ports) + 1
        if show_all_option:
            print(f"  {manual_idx}) Show all serial ports")
            manual_idx += 1
        print(f"  {manual_idx}) Enter port manually")

        try:
            choice = input(f"Select a port (1-{manual_idx}): ").strip()
            if not choice:
                continue
            val = int(choice)
            if 1 <= val <= len(ports):
                return ports[val - 1].device
            elif show_all_option and val == len(ports) + 1:
                ports = all_ports
                showing_filtered = False
                continue
            elif val == manual_idx:
                return input("Please enter the serial port path manually: ").strip()
        except ValueError:
            pass
        print(f"Invalid selection. Please choose between 1 and {manual_idx}.")

def ask_yes_no(question, default="y"):
    options = "[Y/n]" if default.lower() == "y" else "[y/N]"
    val = input(f"{question} {options}: ").strip().lower()
    if not val:
        val = default.lower()
    return val in ["y", "yes"]

def run_npm_install():
    color_print("\n=== Installing Webapp Frontend Dependencies ===", "blue")
    webapp_dir = Path(__file__).resolve().parent / "webapp"
    try:
        # Use shell=True for windows npm compatibility
        subprocess.run(["npm", "install"], cwd=webapp_dir, shell=True, check=True)
        color_print("Frontend dependencies installed successfully!", "green")
    except Exception as e:
        color_print(f"Error installing frontend dependencies: {e}", "red")
        color_print("You may need to run 'npm install' inside the webapp/ directory manually.", "yellow")

def select_firmware_devices(devices):
    """Let the user choose which devices to flash. Returns a sublist of devices."""
    color_print("\nDevices available to flash:", "cyan")
    for idx, dev in enumerate(devices, 1):
        print(f"  {idx}) {dev['device_name']}")
    color_print(
        "Enter the numbers to flash (e.g. '1,3'), 'all', or 'none' to skip.", "cyan"
    )

    while True:
        choice = input("Devices to flash [all]: ").strip().lower()
        if not choice or choice == "all":
            return devices
        if choice in ("none", "skip", "0"):
            return []
        try:
            selected = []
            for token in choice.replace(",", " ").split():
                val = int(token)
                if not 1 <= val <= len(devices):
                    raise ValueError
                if devices[val - 1] not in selected:
                    selected.append(devices[val - 1])
            if selected:
                return selected
        except ValueError:
            pass
        print(f"Invalid selection. Choose numbers between 1 and {len(devices)}, 'all', or 'none'.")

def flash_firmware(device_name, directory, env_name):
    color_print(f"\n--- Preparing to flash {device_name} ---", "cyan")

    port = select_port()
    if not port:
        color_print("No port selected. Skipping flashing.", "yellow")
        return

    pio_path = get_pio_path()
    cmd = [
        pio_path, "run",
        "-d", str(directory),
        "-e", env_name,
        "--target", "upload",
        "--upload-port", port
    ]
    
    color_print(f"Running PlatformIO command: {' '.join(cmd)}", "blue")
    try:
        subprocess.run(cmd, check=True)
        color_print(f"Successfully flashed {device_name} on {port}!", "green")
    except subprocess.CalledProcessError as e:
        color_print(f"Failed to flash {device_name}. Error code: {e.returncode}", "red")
        if ask_yes_no("Would you like to try flashing this device again?"):
            flash_firmware(device_name, directory, env_name)

def generate_launch_scripts():
    color_print("\n=== Generating Startup Launcher Scripts ===", "blue")
    root_dir = Path(__file__).resolve().parent

    # Linux/Mac Script
    sh_content = f"""#!/bin/bash
# Automatically generated by ChArm setup wizard
export CHARM_PYTHON="$(pwd)/venv/bin/python"
cd webapp
npm run dev
"""
    sh_path = root_dir / "start.sh"
    try:
        sh_path.write_text(sh_content, encoding="utf-8")
        os.chmod(sh_path, 0o755)
        color_print(f"Created executable start.sh launcher in root.", "green")
    except Exception as e:
        color_print(f"Could not create start.sh: {e}", "red")

    # Windows Script
    bat_content = r"""@echo off
:: Automatically generated by ChArm setup wizard
set CHARM_PYTHON=%~dp0venv\Scripts\python.exe
cd webapp
npm run dev
"""
    bat_path = root_dir / "start.bat"
    try:
        bat_path.write_text(bat_content, encoding="utf-8")
        color_print("Created start.bat launcher in root.", "green")
    except Exception as e:
        color_print(f"Could not create start.bat: {e}", "red")

def print_help_tips():
    if os.name != 'nt':
        color_print("\n=== Linux/macOS Permissions Note ===", "yellow")
        color_print("If PlatformIO fails to upload because of serial port permission issues,", "yellow")
        color_print("make sure your user belongs to the 'dialout' (or 'uucp') group.", "yellow")
        color_print("Example command: sudo usermod -a -G dialout $USER", "yellow")
        color_print("You may need to log out and log back in for changes to take effect.", "yellow")
    else:
        color_print("\n=== Windows Serial Drivers Note ===", "yellow")
        color_print("Ensure you have installed the correct USB-to-UART drivers (e.g. CP210x or CH340)", "yellow")
        color_print("for your boards so that they show up as COM ports in Device Manager.", "yellow")

def main():
    color_print("=============================================", "green")
    color_print("    ChArm Setup & Installation Wizard        ", "green")
    color_print("=============================================", "green")
    
    root_dir = Path(__file__).resolve().parent
    
    # 1. Install NPM frontend packages
    if ask_yes_no("Would you like to install Node.js/NPM dependencies for the webapp frontend?"):
        run_npm_install()
    
    # 2. Hardware firmware flashing
    if ask_yes_no("Would you like to flash firmware to your hardware devices?"):
        devices = [
            # ESP32 CAM (camera firmware only, not the mega bridge)
            {
                "device_name": "ESP32 CAM",
                "directory": root_dir / "arduino_code" / "esp32_cam_mega_bridge",
                "env_name": "esp32cam",
            },
            {
                "device_name": "ESP32 UI Box",
                "directory": root_dir / "arduino_code" / "esp32_ui_box",
                "env_name": "esp32_ui_box",
            },
            {
                "device_name": "Arduino Mega 2560",
                "directory": root_dir / "arduino_code",
                "env_name": "megaatmega2560",
            },
        ]

        selected = select_firmware_devices(devices)
        if not selected:
            color_print("Skipping all firmware flashing.", "yellow")
        else:
            for dev in selected:
                flash_firmware(**dev)
            print_help_tips()

    # 3. Create startup shortcuts
    generate_launch_scripts()
    
    color_print("\nSetup configuration finished! To launch the webapp, run:", "green")
    if os.name == 'nt':
        color_print("  start.bat", "cyan")
    else:
        color_print("  ./start.sh", "cyan")
    color_print("=============================================", "green")

if __name__ == "__main__":
    main()
