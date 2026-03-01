import os
import win32gui # type: ignore
import win32con # type: ignore
import configparser
import pyautogui
import time
import global_var
import ctypes
import winsound
from datetime import datetime, timedelta
from seeker import screen_check
from logger import out, init_db
from reader import read_daily, read_pos, select_day, check


user32 = ctypes.windll.user32
user32.EnableMouseInPointer(True)
SendInput = user32.SendInput


# --- ALUSTUS JA POLUT ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, 'DATA', 'Config', 'STUFFnSHIET.ini')
error_log_path = os.path.join(BASE_DIR, 'error_log.txt')
stats_path = os.path.join(BASE_DIR, 'statistics.json')
results_path = os.path.join(BASE_DIR, 'RESULTS')
config = configparser.ConfigParser()
config.optionxform = str
config.read(config_path)

DEBUG_DIR = os.path.join(BASE_DIR, 'DATA' ,'DEBUG')
LOG_PATH = os.path.join(BASE_DIR, 'DATA' ,'Logs', 'debug_log.txt')
log_dir = os.path.dirname(LOG_PATH)
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
DEBUG_RUN = config.getboolean('DEBUG', 'debug_run', fallback=True)

# Viiveet
MOVE_D = config.getfloat('DELAYS', 'MOVE_DELAY', fallback=0.2)
RESP_D = config.getfloat('DELAYS', 'RESPONSE_DELAY', fallback=0.1)
UI_D   = config.getfloat('DELAYS', 'UI_DELAY', fallback=0.5)
BUFF_D = config.getfloat('DELAYS', 'BUFFER_DELAY', fallback=2.0)

# Pointterit
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE       = 0x0001
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOD_CONTROL = 0x0002
MOD_ALT = 0x0001

ctypes.windll.user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT, win32con.VK_F12)

pyautogui.PAUSE = RESP_D

def set_console_always_on_top(title):
    # Haetaan komentorivi-ikkunan kahva (handle)
    hwnd = win32gui.GetForegroundWindow()
    out(f"> Setting window AlwaysOnTop with handle {hwnd}.")
    if hwnd:
        win32gui.SetWindowPos(hwnd, 
                              win32con.HWND_TOPMOST, 
                              0, 0, 800, 1200, 
                              0)
        win32gui.SetWindowText(hwnd, "Scribe")

def check_escape():
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x7B) & 0x8000)

def register_f12_hotkey():
    if not ctypes.windll.user32.RegisterHotKey(None, 1, 0, win32con.VK_F12):
        raise RuntimeError("Hotkeyn rekisteröinti epäonnistui")

def main_loop():
    set_console_always_on_top("Scribe")
    try:
        init_db()
    except Exception as e:
        out(f"Database initialization failed: {e}")
    print(">>> Scripture started")
    start_time = datetime.now()
    end_time = 0
    print(f"aloitusaika : {start_time}")
    global viimeisin_luku, total_ocr_calls
    total_ocr_calls = 0
    viimeisin_luku = 0
    mode = config.get('READ_MODE', 'read')
    day = config.get('READ_MODE', 'day')
    global_var.cooldown = datetime.now() - timedelta(hours=1)
    try:
        if screen_check("ranking_window_open_check") or check("SVS_ranking_check"):
            if DEBUG_RUN:
                    out("Performin DEBUG run")
                    read_index, player, score, cycle, player_id = read_pos(6)
                    out(f"DEBUG run successful, values returned: {read_index}, {player}, {score}, {cycle}, {player_id}")
                    input("Paina Enter sulkeaksesi konsolin...")
            else:
                if check("daily_rank_window_check") or check("SVS_ranking_check"):
                    if mode == "weekly":
                        week = ["mon", "tues", "wed", "thur", "fri"]
                        for d in week:
                            select_day(d)
                            if read_daily(d):
                                out(f"Reading day {d} complete")
                            else:
                                print("Ajo keskeytetty")
                                input("Paina Enter sulkeaksesi konsolin...")
                    elif mode == "daily":
                        if read_daily(day):
                            out(f"Reading day {day} complete")
                        else:
                            print("Ajo keskeytetty")
                            input("Paina Enter sulkeaksesi konsolin...")
                    else:
                        out("Day not been set, check INI")
                            
                    pyautogui.mouseUp(button='left')
                    pyautogui.mouseUp(button='right')
                    # Käydään läpi kriittiset ohjausnäppäimet, jotka voivat aiheuttaa tuplaklikkaus-efektiä
                    for key in ['ctrl', 'alt', 'shift']:
                        pyautogui.keyUp(key)
                    time.sleep(0.5) 
                    ctypes.windll.user32.ReleaseCapture()
                    winsound.Beep(1000, 500) # 1000Hz, 0.5 sekuntia
                    print("Kaikki tulokset kerätty ja tallennettu!")
                    end_time = datetime.now()
                    print(f"lopetusaika : {end_time}")
                    run_time = end_time - start_time
                    print(f"ajoon kulunut aika : {run_time}")
                    input("Paina Enter sulkeaksesi konsolin...")
                                
                else:
                    print("daily rank check failed")
        else:
                print("ranking window check failed")
    except Exception as e:
        print(f"virhe : {e} ")
        input("Paina Enter sulkeaksesi konsolin...")

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as e: 
        print(f"\nKriittinen virhe: {e}")
    finally:
        pyautogui.mouseUp(button='left')
        pyautogui.mouseUp(button='right')
        # Käydään läpi kriittiset ohjausnäppäimet, jotka voivat aiheuttaa tuplaklikkaus-efektiä
        for key in ['ctrl', 'alt', 'shift']:
            pyautogui.keyUp(key)
        time.sleep(0.5) 
        ctypes.windll.user32.ReleaseCapture()