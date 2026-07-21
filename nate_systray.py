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
        
        self.menu = Gtk.Menu()
        
        self.item_disk = Gtk.MenuItem(label="Disk: Scanning...")
        self.item_ram = Gtk.MenuItem(label="RAM: Scanning...")
        self.item_cpu = Gtk.MenuItem(label="CPU: Scanning...")
        
        self.menu.append(self.item_disk)
        self.menu.append(self.item_ram)
        self.menu.append(self.item_cpu)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Dictionary to hold dynamic GPU menu items
        self.gpu_items = {}
        
        self.menu.append(Gtk.SeparatorMenuItem())
        item_dash = Gtk.MenuItem(label="Open Mission Control (Web)")
        item_dash.connect("activate", self.open_dashboard)
        self.menu.append(item_dash)

        self.menu.append(Gtk.SeparatorMenuItem())
        item_quit = Gtk.MenuItem(label="Exit Monitor")
        item_quit.connect("activate", Gtk.main_quit)
        self.menu.append(item_quit)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        self.update_data()
        GLib.timeout_add_seconds(3, self.update_data)

    def get_gpus(self):
        gpus = []
        
        # 1. Check for NVIDIA GPUs
        try:
            nv_out = subprocess.check_output([
                "nvidia-smi", 
                "--query-gpu=name,utilization.gpu,temperature.gpu", 
                "--format=csv,noheader,nounits"
            ]).decode().strip()
            for line in nv_out.split('\n'):
                if line.strip():
                    name, use, temp = line.split(',')
                    gpus.append({
                        "name": f"NV: {name.strip()}",
                        "stats": f"{use.strip()}% @ {temp.strip()}C"
                    })
        except:
            pass

        # 2. Check for AMD GPUs via sysfs (more reliable than CLI tools for varied drivers)
        try:
            # Iterate through available DRM render nodes
            for i in range(128, 135): # Standard render node range
                path = f"/sys/class/drm/renderD{i}/device"
                if os.path.exists(f"{path}/gpu_busy_percent"):
                    # Try to get a nicer name from the device ID
                    with open(f"{path}/gpu_busy_percent", 'r') as f:
                        use = f.read().strip()
                    
                    # Try to get vendor to confirm it's AMD (0x1002)
                    with open(f"{path}/vendor", 'r') as f:
                        vendor = f.read().strip()
                    
                    if vendor == "0x1002":
                        gpus.append({
                            "name": f"AMD GPU (renderD{i})",
                            "stats": f"{use}%"
                        })
        except:
            pass

        # 3. Check for Intel GPUs (IGPs)
        try:
            for i in range(128, 135):
                path = f"/sys/class/drm/renderD{i}/device"
                if os.path.exists(f"{path}/vendor"):
                    with open(f"{path}/vendor", 'r') as f:
                        vendor = f.read().strip()
                    if vendor == "0x8086" and os.path.exists(f"{path}/uapi/i915_pmu"):
                        # Basic check for intel - usage extraction for Intel is complex without intel-gpu-tools
                        # but we can at least list its presence or 'N/A'
                        gpus.append({
                            "name": f"Intel GPU (renderD{i})",
                            "stats": "Detected"
                        })
        except:
            pass

        return gpus

    def get_disk_details(self):
        usage = psutil.disk_usage('/')
        return f"{usage.percent}% ({usage.free // (1024**3)}GB Free)"

    def update_data(self):
        try:
            cpu_pct = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            disk_str = self.get_disk_details()
            
            # Get Current GPUs
            gpus = self.get_gpus()
            
            # Update menu items dynamically
            for gpu in gpus:
                name = gpu['name']
                if name not in self.gpu_items:
                    new_item = Gtk.MenuItem(label=f"{name}: {gpu['stats']}")
                    # Insert before the separator/dashboard items
                    self.menu.insert(new_item, 3 + len(self.gpu_items))
                    self.gpu_items[name] = new_item
                    new_item.show()
                else:
                    self.gpu_items[name].set_label(f"{name}: {gpu['stats']}")

            # Update Tray Label (Quick Look)
            gpu_summary = gpus[0]['stats'].split(' ')[0] if gpus else "N/A"
            label_text = f" D:{psutil.disk_usage('/').percent}% | G:{gpu_summary}"
            self.indicator.set_label(label_text, "nate-sys-label")
            
            self.item_disk.set_label(f"SSD Space: {disk_str}")
            self.item_ram.set_label(f"Memory: {ram.percent}% ({ram.available // (1024**2)}MB Avail)")
            self.item_cpu.set_label(f"CPU Load: {cpu_pct}%")
            
        except Exception as e:
            print(f"Update error: {e}")
        return True

    def open_dashboard(self, _):
        subprocess.Popen(["xdg-open", "/home/nate/Desktop/DASHBOARD.html"])

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    NateSysTray()
    Gtk.main()
