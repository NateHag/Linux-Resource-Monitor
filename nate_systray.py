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
        
        # Static top items
        self.item_cpu = Gtk.MenuItem(label="CPU: Scanning...")
        self.item_ram = Gtk.MenuItem(label="RAM: Scanning...")
        self.menu.append(self.item_cpu)
        self.menu.append(self.item_ram)
        self.menu.append(Gtk.SeparatorMenuItem())
        
        # Categories for dynamic updates
        self.gpu_items = {}
        self.disk_items = {}
        
        # Position trackers
        self.disk_start_index = 3 # After CPU, RAM, Separator
        
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
        # Support NVIDIA
        try:
            nv_out = subprocess.check_output([
                "nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"
            ]).decode().strip()
            for line in nv_out.split('\n'):
                if line.strip():
                    name, use, temp = line.split(',')
                    gpus.append({"name": f"NV: {name.strip()}", "stats": f"{use.strip()}% @ {temp.strip()}C"})
        except: pass

        # Support AMD/Intel via sysfs
        try:
            for i in range(128, 135):
                path = f"/sys/class/drm/renderD{i}/device"
                if os.path.exists(f"{path}/vendor"):
                    with open(f"{path}/vendor", 'r') as f: vendor = f.read().strip()
                    if vendor == "0x1002" and os.path.exists(f"{path}/gpu_busy_percent"):
                        with open(f"{path}/gpu_busy_percent", 'r') as f: use = f.read().strip()
                        gpus.append({"name": f"AMD GPU (D{i})", "stats": f"{use}%"})
                    elif vendor == "0x8086":
                        gpus.append({"name": f"Intel GPU (D{i})", "stats": "Detected"})
        except: pass
        return gpus

    def get_disks(self):
        disks = []
        # Capture Root and any mounts under /mnt or /media (like your NAS)
        for part in psutil.disk_partitions(all=False):
            if part.mountpoint == '/' or part.mountpoint.startswith(('/mnt', '/media')):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    name = "OS (SSD)" if part.mountpoint == "/" else part.mountpoint.split('/')[-1]
                    disks.append({
                        "name": name,
                        "stats": f"{usage.percent}% ({usage.free // (1024**3)}GB Free)"
                    })
                except: pass
        return disks

    def update_data(self):
        try:
            cpu_pct = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            
            # 1. Update Disks
            disks = self.get_disks()
            for i, disk in enumerate(disks):
                name = f"Disk: {disk['name']}"
                if name not in self.disk_items:
                    new_item = Gtk.MenuItem(label=f"{name}: {disk['stats']}")
                    self.menu.insert(new_item, self.disk_start_index + i)
                    self.disk_items[name] = new_item
                    new_item.show()
                else:
                    self.disk_items[name].set_label(f"{name}: {disk['stats']}")

            # 2. Update GPUs
            gpus = self.get_gpus()
            gpu_offset = self.disk_start_index + len(self.disk_items)
            for i, gpu in enumerate(gpus):
                name = gpu['name']
                if name not in self.gpu_items:
                    new_item = Gtk.MenuItem(label=f"{name}: {gpu['stats']}")
                    self.menu.insert(new_item, gpu_offset + i)
                    self.gpu_items[name] = new_item
                    new_item.show()
                else:
                    self.gpu_items[name].set_label(f"{name}: {gpu['stats']}")

            # 3. Static Stats
            self.item_cpu.set_label(f"CPU Load: {cpu_pct}%")
            self.item_ram.set_label(f"Memory: {ram.percent}% ({ram.available // (1024**2)}MB Avail)")

            # 4. Tray Summary (Root Disk % | Primary GPU %)
            root_usage = psutil.disk_usage('/').percent
            gpu_usage = gpus[0]['stats'].split(' ')[0] if gpus else "N/A"
            self.indicator.set_label(f" D:{root_usage}% | G:{gpu_usage}", "nate-sys-label")
            
        except Exception as e:
            print(f"Update error: {e}")
        return True

    def open_dashboard(self, _):
        # We can also make this dynamic if DASHBOARD.html moves
        dash_path = os.path.expanduser("~/Desktop/DASHBOARD.html")
        if os.path.exists(dash_path):
            subprocess.Popen(["xdg-open", dash_path])

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    NateSysTray()
    Gtk.main()
