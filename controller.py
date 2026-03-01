import os
import configparser
import win32gui # type: ignore
import win32con # type: ignore
import cv2
import numpy as np
import pyautogui
import time
import ctypes
from ctypes import wintypes as wt
import random
from PIL import ImageGrab

from classes import INPUT, MOUSEINPUT
from logger import out


user32 = ctypes.windll.user32
user32.EnableMouseInPointer(True)
SendInput = user32.SendInput

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, 'DATA', 'Config', 'STUFFnSHIET.ini')
config = configparser.ConfigParser()
config.optionxform = str
config.read(config_path)

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE       = 0x0001
MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
SendInput = user32.SendInput

MOD_CONTROL = 0x0002
MOD_ALT = 0x0001
ctypes.windll.user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT, win32con.VK_F12)
ctypes.windll.shcore.SetProcessDpiAwareness(1)
# --- TOIMINNALLISUUS ---
def scroll_down(amount, delay=0.2):
    out(f"----> Perfomring ScrollDown with amount of {amount}.")
    step = -10 if amount >0 else 10
    counter = 0
    while counter < amount:
        pyautogui.moveTo(1000, 950, 0.2)
        #pyautogui.click()
        time.sleep(0.2)
        pyautogui.dragTo(1000,360, 0.3)
        time.sleep(0.5)
        counter+=1

def scroll_up(amount, delay=0.2):
    out(f"----> Perfomring ScrollUp with amount of {amount}.")
    step = -1 if amount >0 else 1

    for _ in range(abs(amount)):
        pyautogui.scroll(step)
        time.sleep(delay)

def py_click(x=0, y=0, duration=0.2, doubleclick=False, target=None):
    out("------> Initiating click sequence")
    execution_time = duration*2

    if target is not None:
        pos_string = config.get('CLICK_POSITIONS', target)
        x, y = map(int, pos_string.split(','))
        out(f"-------->received target {target} as a parameter")
        out(f"-------->Target '{target}' resolved to {x}, {y}")
    variation = config.getint('HUMANIZE', 'position_variation')
    target_x = x + random.randint(-variation, variation)
    target_y = y + random.randint(-variation, variation)
    # Tässä luodaan se vaihtelu
    target_duration = duration + (random.randint(-5, 5) / 100)
    
    pyautogui.click(target_x, target_y, duration=target_duration) 
    time.sleep(target_duration)
    if doubleclick == True:
        pyautogui.click() 
        execution_time = 3*target_duration
    time.sleep(target_duration)

    out(f"------> clicking location {target_x}*{target_y} with execution time of {execution_time:.2f} seconds.")
    
    return True

def send_mouse(flags, dx=0, dy=0):
    mi = MOUSEINPUT(dx, dy, 0, flags, 0, None)
    inp = INPUT(INPUT_MOUSE, mi)
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

def pointer_drag(start_x, start_y, end_x, end_y, duration=0.4, steps=40):

    out(f"----> Moving cursor to starting point {start_x, {start_y}}")
    ctypes.windll.user32.SetCursorPos(start_x, start_y)
    time.sleep(0.05)
    out("------> Pressing mouse left, sending LEFTDOWN event.")
    send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.06)  # pieni hold että peli tunnistaa dragin alun

    out("------> Calculating relative movement and performing drag action..")
    total_dx = end_x - start_x
    total_dy = end_y - start_y

    step_dx = total_dx / steps
    step_dy = total_dy / steps

    for _ in range(steps):
        send_mouse(
            MOUSEEVENTF_MOVE,
            int(step_dx),
            int(step_dy)
        )
        time.sleep(duration / steps)

    time.sleep(0.03)

    out("----> Releasing mouse left, sending LEFTUP event.")
    send_mouse(MOUSEEVENTF_LEFTUP)

def check_escape_hotkey():
    msg = wt.MSG()
    PM_REMOVE = 0x0001
    if ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
        if msg.message == win32con.WM_HOTKEY and msg.wParam == 1:
            print("\n[!] HÄTÄKESKEYTYS: Ctrl+Alt+F12 painettu.")
            return True
    return False

def recalibrate():
    print("--- Aloitetaan visuaalinen kalibrointi ---")
    bbox = (895, 904, 948, 1120)
    target_gap = 18 # Keskikohta 17-19 välille
    min_blue_height = 50 # Jos sinistä on vähemmän, seuraava rivi on liian lähellä
    time.sleep(0.2)
    for attempt in range(4):
        screenshot = ImageGrab.grab(bbox=bbox)
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 1. Etsitään vihreä ankkuri
        lower_green = np.array([40, 40, 40])
        upper_green = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv, lower_green, upper_green)
        green_coords = np.column_stack(np.where(green_mask > 0))
        
        if len(green_coords) == 0:
            print("Virhe: Vihreää ei löytynyt.")
            return False
            
        green_top_y = np.min(green_coords[:, 0])

        # 2. Analysoidaan sininen palkki ankkurin yläpuolella
        lower_blue = np.array([90, 10, 150]) 
        upper_blue = np.array([110, 100, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # Etsitään siniset pikselit kapeasta pystysuorasta kaistaleesta (keskeltä bboxia)
        mid_x = (bbox[2] - bbox[0]) // 2
        blue_pixels_v = np.where(blue_mask[:, mid_x] > 0)[0]

        if len(blue_pixels_v) > 0:
            # Sinisen palkin alin ja ylin koordinaatti suhteessa ankkuriin
            blue_bottom_y = np.max(blue_pixels_v[blue_pixels_v < green_top_y])
            blue_top_y = np.min(blue_pixels_v[blue_pixels_v < green_top_y])
            
            current_gap = green_top_y - blue_bottom_y
            blue_height = blue_bottom_y - blue_top_y
            
            print(f"Väli: {current_gap}px, Sinisen palkin korkeus: {blue_height}px")
            
            # --- TARKISTUS: Onko väli oikea JA onko palkki tarpeeksi pitkä? ---
            # Jos palkki on liian lyhyt, ollaan skrollattu liian ylös (seuraava valkoinen väli näkyy)
            if 17 <= current_gap <= 40 and blue_height > min_blue_height:
                print("Näkymä kalibroitu täydellisesti.")
                return True

            # --- KORJAUSLIIKKEEN PÄÄTTELY ---
            if current_gap < 17:
                # Liian lähellä tai osittain takana -> Vedetään YLÖS
                drag_amount = 880
            #elif current_gap > 19:
                # Liian kaukana -> Vedetään ALAS
                #drag_amount = 5
            elif blue_height <= min_blue_height:
                # Väli on ehkä ok, mutta palkki on loppumassa (skrollattu liikaa ylös)
                # Vedetään ALAS, jotta saadaan nykyinen palkki kunnolla näkyviin
                print("Palkki liian lyhyt, korjataan alaspäin.")
                drag_amount = 980
            else:
                drag_amount = 930
        else:
            print("Sinistä ei näy, skrollataan reilusti alas.")
            drag_amount = 50
        offset = 930 - drag_amount
        # Suoritetaan korjaus win32_dragilla (koska se todettiin toimivaksi)
        pointer_drag(930, 930, 930, drag_amount, duration=0.7)
        #safe_drag(drag_amount)
    return False