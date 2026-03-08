import os
import win32gui
import win32con
import win32console
import tkinter as tk
from PIL import ImageGrab, Image, ImageDraw, ImageTk
import datetime
import time
import ctypes
import msvcrt
import sys
import subprocess
import keyboard

from seeker import screen_check
from controller import scroll_down, scroll_up, py_click

# DPI-awareness
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class AreaSelector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0.7)
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.config(cursor="cross")

        self.canvas = tk.Canvas(self.root, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.start_x = None
        self.start_y = None
        self.img_id = None
        self.overlay_img = None
        self.overlay_tk = None
        self.bbox = None

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def _create_overlay(self, x1, y1, x2, y2, border_width=8, overlay_alpha=160, border_color=(255,0,0,255)):
        img = Image.new("RGBA", (self.screen_w, self.screen_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, self.screen_w, self.screen_h), fill=(0, 0, 0, overlay_alpha))
        draw.rectangle((x1, y1, x2, y2), fill=(0, 0, 0, 0))
        for i in range(border_width):
            rect = (x1 - i, y1 - i, x2 + i, y2 + i)
            draw.rectangle(rect, outline=border_color)
        return img

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.overlay_img = Image.new("RGBA", (self.screen_w, self.screen_h), (0,0,0,0))
        self.overlay_tk = ImageTk.PhotoImage(self.overlay_img)
        self.img_id = self.canvas.create_image(0, 0, image=self.overlay_tk, anchor='nw')

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        x1, x2 = sorted([self.start_x, cur_x])
        y1, y2 = sorted([self.start_y, cur_y])
        root_x, root_y = self.root.winfo_rootx(), self.root.winfo_rooty()
        abs_x1, abs_y1 = root_x + x1, root_y + y1
        abs_x2, abs_y2 = root_x + x2, root_y + y2

        self.overlay_img = self._create_overlay(abs_x1, abs_y1, abs_x2, abs_y2)
        self.overlay_tk = ImageTk.PhotoImage(self.overlay_img)
        self.canvas.itemconfig(self.img_id, image=self.overlay_tk)
        self.canvas.image_ref = self.overlay_tk

    def on_button_release(self, event):
        end_x, end_y = (event.x, event.y)
        x1, x2 = sorted([self.start_x, end_x])
        y1, y2 = sorted([self.start_y, end_y])
        root_x, root_y = self.root.winfo_rootx(), self.root.winfo_rooty()
        abs_x1, abs_y1 = root_x + x1, root_y + y1
        abs_x2, abs_y2 = root_x + x2, root_y + y2

        if abs_x2 - abs_x1 > 5 and abs_y2 - abs_y1 > 5:
            self.bbox = (abs_x1, abs_y1, abs_x2, abs_y2)
        self.root.after(100, self.root.destroy)

def flush_input():
    """Tyhjentää näppäimistöpuskurin, jotta ESC-painallus ei valu valikkoon."""
    while msvcrt.kbhit():
        msvcrt.getwch()

def set_console_always_on_top(title):
    hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 800, 1200, 0)
        win32gui.SetWindowText(hwnd, "Scribe")

def start_convert_in_background():
    convert_path = os.path.join(BASE_DIR, 'convert.py')
    if not os.path.isfile(convert_path):
        return False, f"convert.py not found at: {convert_path}"
    try:
        flags = 0x00000010 | 0x00000008 if os.name == 'nt' else 0
        subprocess.Popen([sys.executable, convert_path], creationflags=flags, close_fds=True)
        return True, "Process started"
    except Exception as e:
        return False, str(e)

def count_files(category_name):
    path = os.path.join(BASE_DIR, 'UPLOADS', category_name)
    if not os.path.exists(path): return 0
    return len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])

def wait_for_global_trigger(prompt="[F8] Start Selection | [ESC] Back to Menu"):
    print(f"\n>>> {prompt}", end='', flush=True)
    while True:
        if keyboard.is_pressed('f8'):
            while keyboard.is_pressed('f8'): pass
            print("\nTriggered!")
            return True
        if keyboard.is_pressed('esc'):
            while keyboard.is_pressed('esc'): pass
            print("\nReturning to menu...")
            flush_input()  # Tyhjennetään puskuri ennen paluuta
            return False
        time.sleep(0.01)

def main():
    title = "Capture Tool"
    os.system(f"title {title}")
    set_console_always_on_top(title)

    # Kategoriat (Lisätty 4. SATURDAY)
    categories = {"1": "POWER", "2": "DONATIONS", "3": "KILLS", "4": "SATURDAY"}

    while True:
        flush_input() # Varmistetaan puhdas puskuri valikkoon tultaessa
        os.system('cls' if os.name == 'nt' else 'clear')
        print("="*40)
        print("CAPTURE TOOL - DATABASE GENERATOR")
        print("="*40)
        print("Select category:")
        
        for key, name in categories.items():
            count = count_files(name)
            print(f" {key}. {name.ljust(10)} ({count} images)")
            
        print("-" * 40)
        print(" 9. Run convert.py in background")
        print("\n[ESC] Quit program")
        print("="*40)
        print("\nChoice (1-4,9): ", end='', flush=True)

        ch = msvcrt.getwch()

        if ch == '\x1b': # ESC päävalikossa
            print("ESC - Closing program...")
            break
        
        if ch == '9':
            ok, info = start_convert_in_background()
            print(f"\n{info}")
            time.sleep(1)
            continue

        if ch not in categories:
            continue

        choice = ch
        target_folder = os.path.join(BASE_DIR, 'UPLOADS', categories[choice])
        os.makedirs(target_folder, exist_ok=True)

        while True:
            if not wait_for_global_trigger():
                break

            try:
                selector = AreaSelector()
                selector.root.mainloop()
            except Exception as e:
                print(f"ERROR: {e}")
                continue

            if selector.bbox:
                timestamp = datetime.datetime.now().strftime("%H%M%S")
                save_path = os.path.join(target_folder, f"cap_{timestamp}.png")

                try:
                    screenshot = ImageGrab.grab(bbox=selector.bbox, all_screens=True)
                    screenshot.save(save_path)
                    print(f"DONE: Saved to {categories[choice]}")
                except Exception as e:
                    print(f"CAPTURE ERROR: {e}")
            else:
                print(">>> Canceled.")
            print("-" * 30)

    print("\n>>> Program closed.")

if __name__ == "__main__":
    main()