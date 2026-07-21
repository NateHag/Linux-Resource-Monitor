#!/usr/bin/env python3
import os
import signal
import psutil
import subprocess
import gi
import re
from datetime import datetime

# Force GTK 3 because AppIndicator3 requires it
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')

from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator

APP_ID = "nate-sys-tray"

class NateSysTray:
    def __init__(self):
        self.indicator = AppIndicator.Indicator.new(
            APP_ID,
            "drive-harddisk-symbolic",
            AppIndicator.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        
        # Menu items that we'll update dynamically
        self.menu = Gtk.Menu()
        
        self.item_disk = Gtk.MenuItem(label="Disk: Scanning...")
        self.item_ram = Gtk.MenuItem(label="RAM: Scanning...")
        self.item_cpu = Gtk.MenuItem(label="CPU: Scanning...")
        self.item_gpu_nv = Gtk.MenuItem(label="NVIDIA GPU: Scanning...")
        self.item_gpu_amd = Gtk.MenuItem(label="AMD iGPU: Scanning...")
        
        self.menu.append(self.item_disk)
        self.menu.append(self.item_ram)
        self.menu.append(self.item_cpu)
        self.menu.append(self.item_gpu_nv)
        self.menu.append(self.item_gpu_amd)
        
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Add a quick "Refresh Dashboard" option
        item_dash = Gtk.MenuItem(label="Open Mission Control (Web)")
        item_dash.connect("activate", self.open_dashboard)
        self.menu.append(item_dash)

        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Quit option
        item_quit = Gtk.MenuItem(label="Exit Monitor")
        item_quit.connect("activate", Gtk.main_quit)
        self.menu.append(item_quit)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        self.update_data()
        # Refresh every 3 seconds for a snappier feel
        GLib.timeout_add_seconds(3, self.update_data)

    def get_nv_gpu_usage(self):
        try:
            # nvidia-smi --query-gpu=utilization.gpu,temperature.gpu --format=csv,noheader,nounits
            output = subprocess.check_output(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"]).decode().strip()
            use, temp = output.split(',')
            return f"{use.strip()}% @ {temp.strip()}C"
        except:
            return "N/A"

    def get_amd_gpu_usage(self):
        # Pointing to integrated AMD (Radeon 780M)
        # Since rocm-smi is missing, we'll try to pull from sysfs if possible, or fallback
        try:
            # Typical path for AMD integrated GPU usage in sysfs on Linux
            # /sys/class/drm/card1/device/gpu_busy_percent (adjust card index if needed)
            # Nate has card1 for AMD usually.
            path = "/sys/class/drm/card1/device/gpu_busy_percent"
            if os.path.exists(path):
                with open(path, 'r') as f:
                    use = f.read().strip()
                return f"{use}%"
            return "0% (No SMI)"
        except:
            return "N/A"

    def get_disk_details(self):
        usage = psutil.disk_usage('/')
        # Return Free space in GB
        return f"{usage.percent}% ({usage.free // (1024**3)}GB Free)"

    def update_data(self):
        try:
            # Gather stats
            cpu_pct = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            disk_str = self.get_disk_details()
            nv_gpu_str = self.get_nv_gpu_usage()
            amd_gpu_str = self.get_amd_gpu_usage()
            
            # Update Tray Label (The "Quick Look")
            # Showing NV GPU first since it's the main powerhouse now
            label_text = f" D:{psutil.disk_usage('/').percent}% | N:{nv_gpu_str.split(' ')[0]}"
            self.indicator.set_label(label_text, "nate-sys-label")
            
            # Update Tooltip/Menu Items (The "Deep Dive")
            self.item_disk.set_label(f"SSD Space: {disk_str}")
            self.item_ram.set_label(f"Memory: {ram.percent}% ({ram.available // (1024**2)}MB Avail)")
            self.item_cpu.set_label(f"CPU Load: {cpu_pct}%")
            self.item_gpu_nv.set_label(f"NVIDIA RTX 5070 Ti: {nv_gpu_str}")
            self.item_gpu_amd.set_label(f"AMD Radeon 780M (iGPU): {amd_gpu_str}")
            
        except Exception as e:
            print(f"Update error: {e}")
        return True

    def open_dashboard(self, _):
        subprocess.Popen(["xdg-open", "/home/nate/Desktop/DASHBOARD.html"])

if __name__ == "__main__":
    # Handle clean quitting
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    NateSysTray()
    Gtk.main()
