#!/usr/bin/env python3
import os
import signal
import psutil
import subprocess
import gi
import time
from datetime import datetime

# Force GTK 3
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator

APP_ID = "sys-resource-monitor"
DASH_PATH = os.path.expanduser("~/Desktop/DASHBOARD.html")

class ResourceMonitorTray:
    def __init__(self):
        self.indicator = AppIndicator.Indicator.new(
            APP_ID, "drive-harddisk-symbolic", AppIndicator.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        
        self.menu = Gtk.Menu()
        
        self.item_cpu = Gtk.MenuItem()
        self.item_ram = Gtk.MenuItem()
        self.menu.append(self.item_cpu)
        self.menu.append(self.item_ram)
        
        self.sep_gpu = Gtk.SeparatorMenuItem()
        self.menu.append(self.sep_gpu)
        self.gpu_items = {} 

        self.sep_disk = Gtk.SeparatorMenuItem()
        self.menu.append(self.sep_disk)
        self.disk_items = {} 
        
        self.menu.append(Gtk.SeparatorMenuItem())
        item_dash = Gtk.MenuItem(label="Open Mission Control (Web)")
        item_dash.connect("activate", self.open_dashboard)
        self.menu.append(item_dash)

        item_quit = Gtk.MenuItem(label="Exit Monitor")
        item_quit.connect("activate", Gtk.main_quit)
        self.menu.append(item_quit)
        
        self.menu.show_all()
        self.indicator.set_menu(self.menu)
        
        self.last_io_time = time.time()
        self.last_io_counters = psutil.disk_io_counters(perdisk=True)

        self.update_data()
        GLib.timeout_add_seconds(2, self.update_data)

    def draw_bar(self, label, pct, width=15):
        """Creates a bar-first label to ensure alignment in proportional fonts."""
        pct = int(float(pct))
        filled = int((pct / 100) * width)
        # Using standard block characters that usually have consistent em-widths
        bar = "█" * filled + "░" * (width - filled)
        
        # Placing the bar first ensures that even in variable-width fonts,
        # the bars themselves align as long as the first character '[' is at the start.
        # Format: [████░░░] 50% | Label
        return f"[{bar}] {pct:>3}% | {label}"

    def get_gpus(self):
        gpus = []
        try:
            nv_out = subprocess.check_output([
                "nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"
            ]).decode().strip()
            for line in nv_out.split('\n'):
                if line.strip():
                    name, use, temp, v_used, v_total = line.split(',')
                    gpus.append({"name": "NVIDIA", "model": name.strip(), "load": use.strip(), "temp": temp.strip(), "v_used": v_used.strip(), "v_total": v_total.strip()})
        except: pass
        try:
            for i in range(128, 135):
                path = f"/sys/class/drm/renderD{i}/device"
                if os.path.exists(f"{path}/gpu_busy_percent"):
                    with open(f"{path}/gpu_busy_percent", 'r') as f: use = f.read().strip()
                    gpus.append({"name": "AMD", "model": "Radeon 780M", "load": use, "temp": "N/A", "v_used": "0", "v_total": "0"})
        except: pass
        return gpus

    def get_io_rates(self):
        now = time.time()
        dt = max(now - self.last_io_time, 0.1)
        rates = {}
        try:
            counters = psutil.disk_io_counters(perdisk=True)
            for d, cur in counters.items():
                if d in self.last_io_counters:
                    last = self.last_io_counters[d]
                    rates[d] = ((cur.read_bytes - last.read_bytes)/dt/(1024**2), (cur.write_bytes - last.write_bytes)/dt/(1024**2))
            self.last_io_counters = counters
            self.last_io_time = now
        except: pass
        return rates

    def update_data(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory()
            io = self.get_io_rates()
            gpus = self.get_gpus()
            
            # --- BRAIN ---
            self.item_cpu.set_label(self.draw_bar("CPU", cpu))
            self.item_ram.set_label(self.draw_bar("RAM", ram.percent))
            
            # --- MUSCLE ---
            gpu_index = 3
            for g in gpus:
                lbl = f"GPU: {g['model']}"
                bar_text = self.draw_bar(g['name'], g['load'])
                if lbl not in self.gpu_items:
                    item = Gtk.MenuItem(label=bar_text)
                    self.menu.insert(item, gpu_index)
                    self.gpu_items[lbl] = item
                    item.show()
                else:
                    self.gpu_items[lbl].set_label(bar_text)
                gpu_index += 1

            # --- MEMORY ---
            disk_index = gpu_index + 1
            for part in psutil.disk_partitions(all=False):
                if part.mountpoint == '/' or part.mountpoint.startswith(('/mnt', '/media')):
                    usage = psutil.disk_usage(part.mountpoint)
                    name = "SSD" if part.mountpoint == "/" else part.mountpoint.split('/')[-1]
                    lbl = f"Disk: {name}"
                    bar_text = self.draw_bar(name, usage.percent)
                    if lbl not in self.disk_items:
                        item = Gtk.MenuItem(label=bar_text)
                        self.menu.insert(item, disk_index)
                        self.disk_items[lbl] = item
                        item.show()
                    else:
                        self.disk_items[lbl].set_label(bar_text)
                    disk_index += 1

            # Tray Summary
            util = gpus[0]['load'] if gpus else "0"
            self.indicator.set_label(f" C:{cpu}% R:{ram.percent}% G:{util}%", "nate-sys-label")
            
            self.sync_dashboard(cpu, ram, gpus, io)
        except Exception as e:
            print(f"Update error: {e}")
        return True

    def sync_dashboard(self, cpu, ram, gpus, io):
        if not os.path.exists(DASH_PATH): return
        with open(DASH_PATH, 'r') as f: lines = f.readlines()
        new_lines = []
        for line in lines:
            if 'id="cpu-val"' in line: line = f'                        <span id="cpu-val">{cpu}%</span>\n'
            elif 'id="cpu-bar"' in line: line = f'                    <div id="cpu-bar" class="bar-fill" style="width: {cpu}%"></div>\n'
            elif 'id="ram-val"' in line: line = f'                        <span id="ram-val">{ram.percent}%</span>\n'
            elif 'id="ram-details"' in line: line = f'                        <span id="ram-details">{ram.used//(1024**3)}/{ram.total//(1024**3)} GB</span>\n'
            elif 'id="ram-bar"' in line: line = f'                    <div id="ram-bar" class="bar-fill" style="width: {ram.percent}%; background: #a855f7;"></div>\n'
            elif 'id="nv-load"' in line and gpus:
                nv = [g for g in gpus if g['name'] == "NVIDIA" or g['name'] == "NV"][0]
                line = f'                        <span id="nv-load">{nv["load"]}%</span>\n'
            elif 'id="nv-temp"' in line and gpus:
                nv = [g for g in gpus if g['name'] == "NVIDIA" or g['name'] == "NV"][0]
                line = f'                        <span id="nv-temp">{nv["temp"]}C</span>\n'
            elif 'id="nv-bar"' in line and gpus:
                nv = [g for g in gpus if g['name'] == "NVIDIA" or g['name'] == "NV"][0]
                line = f'                    <div id="nv-bar" class="bar-fill" style="width: {nv["load"]}%; background: #76b900;"></div>\n'
            elif 'id="nv-vram"' in line and gpus:
                nv = [g for g in gpus if g['name'] == "NVIDIA" or g['name'] == "NV"][0]
                line = f'                        <span id="nv-vram">{nv["v_used"]} / {nv["v_total"]} MB</span>\n'
            elif 'id="nv-vram-bar"' in line and gpus:
                nv = [g for g in gpus if g['name'] == "NVIDIA" or g['name'] == "NV"][0]
                v_pct = (int(nv["v_used"])/int(nv["v_total"]))*100 if int(nv["v_total"]) > 0 else 0
                line = f'                    <div id="nv-vram-bar" class="bar-fill" style="width: {v_pct}%; background: #4ade80;"></div>\n'
            elif 'id="amd-load"' in line and len(gpus) > 1:
                amd = [g for g in gpus if g['name'] == "AMD"][0]
                line = f'                        <span id="amd-load">{amd["load"]}%</span>\n'
            elif 'id="amd-bar"' in line and len(gpus) > 1:
                amd = [g for g in gpus if g['name'] == "AMD"][0]
                line = f'                    <div id="amd-bar" class="bar-fill" style="width: {amd["load"]}%; background: #ed1c24;"></div>\n'
            elif 'id="ssd-space"' in line:
                usage = psutil.disk_usage('/')
                line = f'                        <span id="ssd-space">{usage.free//(1024**3)}G Free</span>\n'
            elif 'id="ssd-bar"' in line:
                usage = psutil.disk_usage('/')
                line = f'                    <div id="ssd-bar" class="bar-fill" style="width: {usage.percent}%; background: #38bdf8;"></div>\n'
            elif 'id="ssd-io"' in line:
                dev = [p.device.split('/')[-1] for p in psutil.disk_partitions() if p.mountpoint == '/'][0]
                r, w = io.get(dev, (0.0, 0.0))
                line = f'            <div class="io-tag" id="ssd-io">R: {r:.1f} MB/s | W: {w:.1f} MB/s</div>\n'
            elif 'id="nas-space"' in line and os.path.exists('/mnt/nas_media'):
                usage = psutil.disk_usage('/mnt/nas_media')
                line = f'                        <span id="nas-space">{usage.free//(1024**4)}T Free</span>\n'
            elif 'id="nas-bar"' in line and os.path.exists('/mnt/nas_media'):
                usage = psutil.disk_usage('/mnt/nas_media')
                line = f'                    <div id="nas-bar" class="bar-fill" style="width: {usage.percent}%; background: #a855f7;"></div>\n'
            elif 'id="nas-io"' in line and os.path.exists('/mnt/nas_media'):
                devs = [p.device.split('/')[-1] for p in psutil.disk_partitions() if p.mountpoint == '/mnt/nas_media']
                if devs:
                    r, w = io.get(devs[0], (0.0, 0.0))
                    line = f'            <div class="io-tag" id="nas-io">R: {r:.1f} MB/s | W: {w:.1f} MB/s</div>\n'
            new_lines.append(line)
        with open(DASH_PATH, 'w') as f: f.writelines(new_lines)

    def open_dashboard(self, _):
        subprocess.Popen(["xdg-open", DASH_PATH])

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    ResourceMonitorTray()
    Gtk.main()
