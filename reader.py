import os
import win32gui # type: ignore
import win32con # type: ignore
import numpy as np
import configparser
import pyautogui
import time
import random
import ctypes
from ctypes import wintypes as wt
import pyperclip
from datetime import datetime
from seeker import screen_check
from logger import out, tallenna_tulokset, tallenna_lopulliset_tulokset, add_player_to_db, player_exists_check
from controller import check_escape_hotkey, py_click, scroll_down, scroll_up, recalibrate
from vision import get_validated_score, capture_pfp


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
DEBUG = config.getboolean('DEBUG', 'debug_logger', fallback=True)

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
viimeisin_luku = 0
read_index = 0
total_ocr_calls = 0

def add_self(name="Sphen of love"):
    tag = name
    playerID = player_exists_check(tag=name)
    if playerID is None:
        joindate = datetime.now().strftime("%d:%m:%Y")
        date_for_id = str(joindate).replace(":", "")
        randomize = random.randint(100000, 999999)
        letter = chr(random.randint(ord('A'), ord('Z')))
        index = 666
        playerID = (f"{date_for_id}-{index}{letter}{randomize}")
        py_click(target="open_pfp")
        img = capture_pfp(playerID)
        out("Generating the playerID")

        if img is not None: 
            try:
                out("Writing to database")
                add_player_to_db(name=name, tag=tag, playerID=playerID, joindate=joindate, profilepicture=img)
            except Exception as e:
                out(f"database write error {e}")
            pyautogui.press('esc')
        else:
            out("pfp read failed, skipping database write")
    return tag, playerID


def tag_player(index=0):
    joindate = datetime.now().strftime("%d:%m:%Y")
    date_for_id = str(joindate).replace(":", "")
    randomize = random.randint(100000, 999999)
    letter = chr(random.randint(ord('A'), ord('Z')))
    out(f"Generated parameters: {joindate}, {date_for_id}, {randomize}, {letter}")
    pyperclip.copy("")
    py_click(target="copy_player_name")
    py_click(target="note_name_field")
    pyautogui.hotkey("ctrl", "v")
    name = tag = pyperclip.paste()
    py_click(target="save_button")
    if check("save_changes_check"):
        py_click(target="save_confirmation")
    out("Opening the profile picture")
    py_click(target="open_pfp")
    out("Generating the playerID")
    playerID = (f"{date_for_id}-{index}{letter}{randomize}")
    out(f"PlayerID : {playerID}")
    time.sleep(0.2)
    img = capture_pfp(playerID)
    out("Image capture completed")
    if img is not None: 
        try:
            out("Writing to database")
            add_player_to_db(name=name, tag=tag, playerID=playerID, joindate=joindate, profilepicture=img)
        except Exception as e:
            out(f"database write error {e}")
        pyautogui.press('esc')
    else:
        out("pfp read failed, skipping database write")
    return tag, playerID
# JG1000
# whatyousay
# flatulax

def check_tag():
    if check("no_tag_check"):
        tag, player_id = tag_player()
    else:
        py_click(target="note_name_field")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "c")
        py_click(target="close_profile")
        tag = pyperclip.paste()
        time.sleep(0.15)
        player_id = player_exists_check(tag)
        out(f"Check tag raturned id {player_id} with tag {tag}")
        if player_id is None:
            tag, player_id = tag_player(1)
    
    return tag, player_id

def detect_position(pos=0):
    
    if check("is_player_profile_check"): return 1
    elif check("very_popular_check"): return 2
    elif check("own_screen_check"): return 3
    elif check("low_level_check"): return 4
    else:
        out("read_pos screen checks failed")
        return 0
                
def own_profile():
    out("--> Own profile detected!")
    own_name = "Sphen of love"
    player, player_id = add_self(own_name)
    py_click(target="close_player_window")
    out(f"--> Own profile found, setting plyer as {player} and returning to previous view.")
    return player, player_id

def read_pos(pos):  
    if check_escape_hotkey():
        return 6, "6", 6, 6, "6"
    out(f"-->  Reading position {pos}.")
    global read_index
    read_index += 1
    score, position = 0, 99
    score_read_area, player = "", ""
    match pos:
        case 1: #1st place
            target = "readarea_1"       
            position = 1
        case 2: #2nd place
            target = "readarea_2"
            position = 2
        case 3: #3rd place
            target = "readarea_3"
            position = 3
        case 4: #4th place
            target = "readarea_4"
            position = 4
        case 5: #5th place
            target = "readarea_5"
            position = 5
        case 6: #bottom rotation
            target = "readarea_0"
            position = 0
        case _:
            print("tuntematon positio")
            return 6, "6", 6, 6, "6"
        
    out(f"--> Position {position} found.")  
    score_read_area = f"readarea_{position}_score"
    py_click(target="default_position")
    py_click(target=target)
    out("--> Clearing clipboard.")
    try:
        pyperclip.copy("")
    except Exception as e:
        out(f" error {e}")

    match detect_position():
        case 1:
            out("--> Not own profile, reading player name:")
            py_click(target="open_profile")
            player, player_id = check_tag()
            if player == "error" and player_id == "error":
                pass
            py_click(target="close_player_window")
            out(f"----> player {player} found")
        case 2:
            py_click(target="close_popular")
            player, player_id = own_profile()
        case 3:
            player, player_id = own_profile()
        case 4:
            out("low level player detected")
            pyautogui.press('esc')
            return 0, "0", 0, 0, "0"
        case 0:
            out("read_pos screen checks failed")
            return 6, "6", 6, 6, "6"
 
    out("--> Calling score reading pipeline:")
    score, cycle = get_validated_score(score_read_area, player, pos=position)
    out(f"--> score of {score} returned in {cycle} read cycles")
    out(f"----> Setting line index as {read_index}")
    return read_index, player, score, cycle, player_id

def read_daily(day=""):
    global read_index
    read_index = 0
    score = 0
    player = ""
    ndx = 0
    kaikki_tulokset = []
    finished = False
    py_click(930, 930, duration=0.2)
    if check("top_reached"):
        scroll_down(16)
    elif check("SVS_top_reached"):
        scroll_down(10)
    x=0
    
    while x < 25:
        if check("top_reached", error_threshold=2) or check("SVS_top_reached" ,error_threshold=2): 
            pass
        else:
            recalibrate()
        for i in range(5):
            if check("top_reached", error_threshold=2) or check("SVS_top_reached" ,error_threshold=2):
                #print("top reached")
                finished = True
                break
            else:
                #print("not at the top yet")
                ndx, player, score, cycle, player_id = read_pos(6)
                if ndx == 6 and player == "6" and score==6 and cycle==6:
                    return False
                if ndx == 0 and player == "0" and score==0 and cycle==0:
                    out("Skipping reading")
                    py_click(target="default_position")
                    scroll_up(-5)
                else:
                    tallenna_tulokset(ndx, score, player, cycle, player_id)
                    kaikki_tulokset.append({
                        "indeksi": ndx,
                        "pelaaja": player,
                        "pisteet": score,
                        "lukukerrat": cycle,
                        "player_id": player_id
                    })
                    print(F"{ndx} : {player} : {score}") 
                    print(f"{cycle} lukukertaa")
                    py_click(930, 930, duration=0.2)
                    if i == 2:
                        scroll_up(-5)
                    else:
                        scroll_up(-6)
        if x == 99:
            return False
        if finished:
            break
        x+=1
    for j in range(5, 0, -1):
        ndx, player, score, cycle, player_id = read_pos(j)
        if ndx == 6 and player == "6" and score==6 and cycle==6:
            return False
        tallenna_tulokset(ndx, score, player, cycle, player_id)
        out(F"{ndx} : {player} : {score}")
        out(f"{cycle} lukukertaa")
        kaikki_tulokset.append({
            "indeksi": ndx,
            "pelaaja": player,
            "pisteet": score,
            "lukukerrat": cycle,
            "player_id": player_id
            })
        py_click(930, 930, duration=0.1)
    tallenna_lopulliset_tulokset(kaikki_tulokset, day)
    return True

def check(indicator_id, error_threshold=10, interval=0.05):
    elapsed = 0
    while elapsed < error_threshold:
        if DEBUG: print(f"read cycle {elapsed +1}")
        if screen_check(indicator_id):
            out(f"performing screencheck for {indicator_id}, successful try number {elapsed+1}")
            return True  # Näkymä löytyi!    
        time.sleep(interval)
        elapsed += 1
        
    out(f"----> Screen Check Timeout : {indicator_id} at cycle {elapsed}")
    return False


def select_day(day="mon"):
    if check("alliance_filterON_check"):
        py_click(target=day)
    else:
        if check("alliance_filter_check"):
            py_click(target="your_alliance_checkmark")
            py_click(target=day)
    return True