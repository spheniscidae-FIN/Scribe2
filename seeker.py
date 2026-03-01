import os
import cv2
import numpy as np
import configparser
from PIL import ImageGrab
from datetime import datetime, timedelta

# --- ALUSTUS JA POLUT ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, 'DATA', 'Config', 'STUFFnSHIET.ini')
stats_path = os.path.join(BASE_DIR, 'statistics.json')

config = configparser.ConfigParser()
config.optionxform = str
config.read(config_path)

# Viiveet
MOVE_D = config.getfloat('DELAYS', 'MOVE_DELAY', fallback=0.2)
RESP_D = config.getfloat('DELAYS', 'RESPONSE_DELAY', fallback=0.1)
UI_D   = config.getfloat('DELAYS', 'UI_DELAY', fallback=0.5)
BUFF_D = config.getfloat('DELAYS', 'BUFFER_DELAY', fallback=2.0)



def screen_check(indicator_id):
    try:
        # Haetaan koko rivi merkkijonona
        line = config.get('SCREEN_INDICATORS', indicator_id)
        # Pilkotaan ja poistetaan tyhjät
        parts = [p.strip() for p in line.split(',') if p.strip()]
        
        # Varmistetaan, että saatiin tarpeeksi osia (nimi + 4 koord + threshold = 6 osaa)
        if len(parts) < 6:
            print(f"ERROR: ID {indicator_id} has invalid INI format: {parts}")
            return False

        img_name = parts[0]
        
        # Määritetään koordinaatit dynaamisesti (tukee x1,y1,x2,y2 muotoa)
        x1, y1, x2, y2 = map(int, parts[1:5])
        
        # TÄRKEÄÄ: Lasketaan leveys ja korkeus
        width = x2 - x1
        height = y2 - y1
        
        # Haetaan threshold - pakotetaan indeksi 5
        threshold_val = int(parts[5]) / 100.0

        # Tulostetaan kerran logiin varmistus (vain testivaiheessa)
        #print(f"DEBUG: {indicator_id} | Thresh: {threshold_val} | ROI: {width}x{height}")

        # Kuvakaappaus (bbox = left, top, right, bottom)
        bbox = (x1, y1, x2, y2)
        screenshot_rgb = np.array(ImageGrab.grab(bbox=bbox))
        screenshot_bgr = cv2.cvtColor(screenshot_rgb, cv2.COLOR_RGB2BGR)

        # Lataa template
        template_path = os.path.join(BASE_DIR, 'DATA', 'Templates', img_name)
        template = cv2.imread(template_path, cv2.IMREAD_COLOR)

        if template is None:
            print(f"ERROR: Template {img_name} missing.")
            return False

        # Vertailu
        res = cv2.matchTemplate(screenshot_bgr, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        separator = "---------------------|--->"
        if max_val >= threshold_val:
            deviation = threshold_val - max_val
            #print(f"SUCCESS, ID:{indicator_id} \n{separator}READ value: {max_val:.3f} \n{separator}Threshold: {threshold_val} \n{separator}Deviation: {deviation}")
            return True
        else:
            deviation = threshold_val - max_val
            #print(f"FAILED ID:{indicator_id} - Mismatch: \n{separator}READ value:{max_val:.3f} \n{separator}Threshold: {threshold_val} \n{separator}Deviation:{deviation}")
            return False

    except Exception as e:
        print(f"SCREEN_CHECK CRITICAL ERROR: {e}")
        return False
    

