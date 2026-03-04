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

# DPI-awareness: yritetään molempia kutsuja turvallisesti
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

        # näytön koko (moninäyttöissä voi säätää tarpeen mukaan)
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def _create_overlay(self, x1, y1, x2, y2, border_width=8, overlay_alpha=160, border_color=(255,0,0,255)):
        """
        Luo RGBA-overlay:
        - koko näyttö tummennettuna (overlay_alpha)
        - valitun alueen sisus läpinäkyvä (ei tummennusta)
        - valinnan ympärille paksu, läpinäkymätön reunus (border_color)
        """
        img = Image.new("RGBA", (self.screen_w, self.screen_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # koko näyttöön puoliläpinäkyvä musta
        draw.rectangle((0, 0, self.screen_w, self.screen_h), fill=(0, 0, 0, overlay_alpha))

        # "leikataan" valitun alueen sisus tekemällä se täysin läpinäkyvä
        draw.rectangle((x1, y1, x2, y2), fill=(0, 0, 0, 0))

        # piirretään kirkas reunus valitun alueen ympärille (useita kertoja border_width:in vuoksi)
        # ImageDraw:n width-parametri ei aina toimi odotetusti, joten piirretään useita outlineja
        for i in range(border_width):
            rect = (x1 - i, y1 - i, x2 + i, y2 + i)
            draw.rectangle(rect, outline=border_color)

        return img

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        # luodaan tyhjä overlay ja lisätään canvasille
        self.overlay_img = Image.new("RGBA", (self.screen_w, self.screen_h), (0,0,0,0))
        self.overlay_tk = ImageTk.PhotoImage(self.overlay_img)
        self.img_id = self.canvas.create_image(0, 0, image=self.overlay_tk, anchor='nw')

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        x1, x2 = sorted([self.start_x, cur_x])
        y1, y2 = sorted([self.start_y, cur_y])

        # widget -> ruudun koordinaatit
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        abs_x1 = root_x + x1
        abs_y1 = root_y + y1
        abs_x2 = root_x + x2
        abs_y2 = root_y + y2

        # luo overlay kirkkaalla reunuksella (säädä border_width ja overlay_alpha)
        self.overlay_img = self._create_overlay(abs_x1, abs_y1, abs_x2, abs_y2,
                                                border_width=8, overlay_alpha=160,
                                                border_color=(255,0,0,255))
        self.overlay_tk = ImageTk.PhotoImage(self.overlay_img)
        self.canvas.itemconfig(self.img_id, image=self.overlay_tk)
        # pidetään viittaus jotta kuva ei katoa garbage collectionin takia
        self.canvas.image_ref = self.overlay_tk

    def on_button_release(self, event):
        end_x, end_y = (event.x, event.y)
        x1, x2 = sorted([self.start_x, end_x])
        y1, y2 = sorted([self.start_y, end_y])

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        abs_x1 = root_x + x1
        abs_y1 = root_y + y1
        abs_x2 = root_x + x2
        abs_y2 = root_y + y2

        if abs_x2 - abs_x1 > 5 and abs_y2 - abs_y1 > 5:
            self.bbox = (abs_x1, abs_y1, abs_x2, abs_y2)

        self.root.after(100, self.root.destroy)


def set_console_always_on_top(title):
    # Haetaan komentorivi-ikkunan kahva (handle)
    hwnd = win32gui.GetForegroundWindow()
    print(f"> Setting window AlwaysOnTop with handle {hwnd}.")
    if hwnd:
        win32gui.SetWindowPos(hwnd, 
                              win32con.HWND_TOPMOST, 
                              0, 0, 800, 1200, 
                              0)
        win32gui.SetWindowText(hwnd, "Scribe")

def wait_enter_or_esc(prompt="Press ENTER to continue, ESC to exit: "):
    """
    Odottaa Enteriä tai Esc:iä konsolissa.
    Palauttaa True jos jatketaan (Enter), False jos suljetaan (Esc).
    """
    print(prompt, end='', flush=True)
    while True:
        ch = msvcrt.getwch()  # palauttaa str, esim '\r' Enter, '\x1b' Esc
        # Jos käyttäjä painaa Enter (CR)
        if ch == '\r':
            print()  # rivinvaihto siistin tulostuksen vuoksi
            return True
        # Jos käyttäjä painaa Esc
        if ch == '\x1b':
            print()  # rivinvaihto
            return False
        # Muut näppäimet: jatketaan odotusta (ei tulosteta)

# ADDED: start convert
def start_convert_in_background():
    """
    Käynnistää convert.py taustaprosessina ilman, että pääohjelma odottaa.
    Palauttaa (True, pid) jos onnistui, muuten (False, error_message).
    """
    convert_path = os.path.join(BASE_DIR, 'convert.py')
    if not os.path.isfile(convert_path):
        return False, f"convert.py not found at: {convert_path}"

    try:
        if os.name == 'nt':
            CREATE_NEW_CONSOLE = 0x00000010
            DETACHED_PROCESS = 0x00000008
            proc = subprocess.Popen([sys.executable, convert_path],
                                    creationflags=CREATE_NEW_CONSOLE | DETACHED_PROCESS,
                                    close_fds=True)
        else:
            proc = subprocess.Popen([sys.executable, convert_path],
                                    preexec_fn=os.setsid,
                                    close_fds=True)
        return True, proc.pid
    except Exception as e:
        return False, str(e)
# ADDED: end

def count_files(category_name):
    """Laskee tiedostojen määrän kyseisessä kategoriassa."""
    path = os.path.join(BASE_DIR, 'UPLOADS', category_name)
    if not os.path.exists(path):
        return 0
    return len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])

def wait_for_global_trigger(prompt="[F8] Start Selection | [ESC] Back to Menu"):
    """
    Odottaa globaalia näppäinpainallusta riippumatta siitä, mikä ikkuna on aktiivinen.
    """
    print(f"\n>>> {prompt}", end='', flush=True)
    
    while True:
        # F8 aloittaa kaappauksen
        if keyboard.is_pressed('f8'):
            while keyboard.is_pressed('f8'): pass # Estetään useat rekisteröinnit yhdellä painalluksella
            print("\nTriggered!")
            return True
        
        # ESC palaa valikkoon
        if keyboard.is_pressed('esc'):
            while keyboard.is_pressed('esc'): pass
            print("\nReturning to menu...")
            return False
        
        time.sleep(0.01) # Säästetään prosessoria

def main():
    title = "Capture Tool"
    os.system(f"title {title}")
    time.sleep(0.2)
    set_console_always_on_top(title)

    categories = {"1": "POWER", "2": "DONATIONS", "3": "KILLS"}

    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("="*40)
        print("CAPTURE TOOL - DATABASE GENERATOR")
        print("="*40)
        print("Select category:")
        
        # Tulostetaan kategoriat ja tiedostomäärät
        for key, name in categories.items():
            count = count_files(name)
            print(f" {key}. {name.ljust(10)} ({count} images)")
            
        print("-" * 40)
        print(" 9. Run convert.py in background")
        print("\n[ESC] Quit program")
        print("="*40)
        print("\nChoice (1-3,9): ", end='', flush=True)

        # Luetaan näppäinpainallus suoraan (ilman Enterin vaatimusta valikossa)
        # Tämä tekee ESC:stä välittömän ja estää tyhjän Enterin sulkemasta ohjelmaa
        ch = msvcrt.getwch()

        if ch == '\x1b': # ESC painettu alkutilassa
            print("ESC")
            break
        
        # ADDED: handle 9 - start convert.py in background
        if ch == '9':
            print('9')
            ok, info = start_convert_in_background()
            if ok:
                print(f"Started convert.py as background process (PID {info}).")
            else:
                print(f"Failed to start convert.py: {info}")
            time.sleep(0.5)
            continue
        # ADDED: end

        if ch not in categories:
            # Jos painettiin jotain muuta kuin 1, 2 tai 3 (esim. Enter)
            continue

        choice = ch
        print(choice) # Tulostetaan valittu numero näkyviin

        target_folder = os.path.join(BASE_DIR, 'UPLOADS', categories[choice])
        if not os.path.exists(target_folder):
            os.makedirs(target_folder)

        while True:
            # 1. Odotetaan globaalia triggeriä (F8 tai ESC)
            if not wait_for_global_trigger():
                break # ESC painettu globaalisti -> poistutaan kategoriavalikkoon

            # 2. Suoritetaan kaappaus
            try:
                selector = AreaSelector()
                selector.root.mainloop()
            except Exception as e:
                print(f"ERROR: {e}")
                continue # Yritetään uudestaan

            # 3. Tallennetaan kuva, jos alue valittiin
            if selector.bbox:
                timestamp = datetime.datetime.now().strftime("%H%M%S")
                file_name = f"cap_{timestamp}.png"
                save_path = os.path.join(target_folder, file_name)

                try:
                    screenshot = ImageGrab.grab(bbox=selector.bbox, all_screens=True)
                    screenshot.save(save_path)
                    # Näytetään heti tallennuksen jälkeen uusi tiedostomäärä
                    current_count = count_files(categories[choice])
                    print(f"DONE: {file_name} saved. Total in {categories[choice]}: {current_count}")
                except Exception as e:
                    print(f"CAPTURE ERROR: {e}")
            else:
                print(">>> Canceled or area too small.")

            # POISTETTU: wait_enter_or_esc -kutsu täältä!
            # Silmukka palaa nyt suoraan alkuun wait_for_global_triggeriin.
            print("-" * 30)

    print("\n>>> Program closed.")

if __name__ == "__main__":
    main()
