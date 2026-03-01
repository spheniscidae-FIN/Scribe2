import os
import win32gui
import win32con  # Tarvitaan vakioarvoja varten
import tkinter as tk
from PIL import ImageGrab
import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class AreaSelector:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes('-alpha', 0.3)  # Läpinäkyvyys
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        
        self.root.config(cursor="cross")
        
        self.canvas = tk.Canvas(self.root, cursor="cross", bg="grey")
        self.canvas.pack(fill="both", expand=True)
        
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.bbox = None

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2)

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        end_x, end_y = (event.x, event.y)
        # Varmistetaan että koordinaatit ovat järjestyksessä (pieni -> suuri)
        x1, x2 = sorted([self.start_x, end_x])
        y1, y2 = sorted([self.start_y, end_y])
        self.bbox = (x1, y1, x2, y2)
        self.root.destroy()

def set_console_always_on_top(title):
    # Haetaan komentorivi-ikkunan kahva (handle)
    hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                              win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
        win32gui.SetWindowText(hwnd, "Seer - Capture Tool")

def log_coordinates(id_name, file_name, bbox):
    log_file = os.path.join(BASE_DIR, "capture_log.txt")
    x1, y1, x2, y2 = bbox
    # Tallenna INI-muodossa
    entry = f"{id_name} = {file_name}, {x1}, {y1}, {x2}, {y2}, 95\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)

def main():
    # Asetetaan konsoli päällimmäiseksi heti alussa
    title = "Clairvoyant"
    os.system(f"title {title}")
    
    print(">>> Initializing Seer...")
    set_console_always_on_top(title)

    print("Press Enter for capture, or Ctrl+C to quit.")
    input()
    
    if not os.path.exists('IMG'): 
        os.makedirs('IMG')

    while True:
        print("\n" + "="*40)
        print(" [STEP 1] Paint the capture area (Esc to cancel)")
        print("="*40)
        
        selector = AreaSelector()
        selector.root.mainloop()
        
        if not selector.bbox:
            print("\n>>> Canceled by user.")
            break

        # Tarkistetaan ettei alue ole nollan kokoinen (vahinkoklikkaus)
        x1, y1, x2, y2 = selector.bbox
        if x1 == x2 or y1 == y2:
            print(">>> ERROR: Area too small. Try again.")
            continue

        print(f"Selected area: {selector.bbox}")
        
        name = input("Give a name for the capture (e.g. play_button): ").strip()
        if not name: 
            print(">>> Name cannot be empty.")
            continue
        
        file_name = f"{name}.png"
        save_path = os.path.join(BASE_DIR, 'IMG', file_name)
        
        # Kaappaus ja tallennus
        screenshot = ImageGrab.grab(bbox=selector.bbox)
        screenshot.save(save_path)
        
        # Loki
        log_coordinates(name, file_name, selector.bbox)
        
        print(f"\n>>> SUCCESS: {save_path}")
        print(">>> Coordinates logged to capture_log.txt")
        print("-" * 40)
        print("Press Enter for NEXT capture, or Ctrl+C to quit.")
        input()

if __name__ == "__main__":
    main()