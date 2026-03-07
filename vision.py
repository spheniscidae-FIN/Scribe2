import os
import win32gui # type: ignore
import win32con # type: ignore
import cv2
import numpy as np
import configparser
import pyautogui
import time
import ctypes
from ctypes import wintypes as wt
import pytesseract
import gc
import tesserocr

from collections import Counter
from PIL import ImageGrab, Image
from skimage.morphology import skeletonize
from skimage.util import invert
from logger import out


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
PFP_PATH = os.path.join(BASE_DIR, 'DATA' ,'DATABASE', 'Profile_pictures')
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

def get_validated_score(indicator_id, player, pos, api):
    global viimeisin_luku, total_ocr_calls
    max_rotation = 6  # Nostetaan kuuteen
    max_retries, rerun, total_cycles = 17, 2, 0
    best_guess = 0
    
    cv2.setNumThreads(1)

    try:
        for cycle in range(1, rerun + 1):
            for attempt in range(1, max_retries + 1):
                mittaukset = []
                
                for x in range(max_rotation):
                    total_ocr_calls += 1
                    total_cycles += 1 
                    
                    # get_score() hoitaa logiikkasi mukaan eri variaatiot:
                    # x=0,1: Perus / x=2,3: Inversio / x=4: Harmaa / x=5: Harmaa-inversio
                    mittaus = get_score(api, indicator_id, player, attempts=attempt, rerun=cycle, pos=pos, rotation=x)
                    
                    if mittaus is not None and mittaus > 0:
                        mittaukset.append(int(mittaus))

                if not mittaukset:
                    continue

                mittaukset.sort()
                cnt = Counter(mittaukset)
                most_common_value, occurrences = cnt.most_common(1)[0]
                
                # 1. EXIT CONDITION: Täydellinen 6/6 osuma
                if occurrences == 6:
                    luku = most_common_value
                    if luku >= viimeisin_luku:
                        viimeisin_luku = luku
                        return luku, total_cycles

                # 2. SEURAAVA TASO: 5/6 osuma sallitaan jatkokäsittelyyn
                if occurrences >= 5:
                    luku = most_common_value
                    if luku >= viimeisin_luku:
                        if viimeisin_luku == 0 or luku <= viimeisin_luku * 100:
                            viimeisin_luku = luku
                            return luku, total_cycles

                # 3. BEST GUESS VARASTO: Jos saatiin vähintään 4/6 (valinnainen kynnys)
                # Voit pitää tämän 5/6:ssa jos haluat olla todella varma.
                if occurrences >= 5:
                    if most_common_value > best_guess:
                        best_guess = most_common_value

                gc.collect()

    except Exception as e:
        print(f"Error: {e}")

    # Jos mikään ei antanut 6/6 tai 5/6, palautetaan best guess jos se on validi
    if best_guess >= viimeisin_luku and best_guess > 0:
        viimeisin_luku = best_guess
        return best_guess, total_cycles

    return 0, total_cycles

def preprocess_with_hex_combined(img_bgr, pos, margin=10, min_black_ratio=0.001, debug=False):
    if img_bgr is None:
        raise ValueError("img_bgr is None")
    img = img_bgr.copy()
    h, w = img.shape[:2]

    def get_limits(base_colors, m):
        arr = np.array(base_colors, dtype=np.int16)
        lower = np.clip(arr - m, 0, 255).astype(np.uint8)
        upper = np.clip(arr + m, 0, 255).astype(np.uint8)
        return lower, upper

    # väriperusteinen maski tai löyhä Otsu fallback
    if pos not in (0,1,2,3):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5,5), 0)
        otsu_val, _ = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh_val = int(max(1, 0.6 * otsu_val))
        _, bw_loose = cv2.threshold(blur, thresh_val, 255, cv2.THRESH_BINARY)
        if (np.sum(bw_loose == 255) / bw_loose.size) < 0.5:
            bw_loose = cv2.bitwise_not(bw_loose)
        return bw_loose.astype(np.uint8)

    match pos:
        case 1:
            txt_min, txt_max = get_limits([12, 116, 194], margin)
        case 2:
            txt_min, txt_max = get_limits([168, 106, 92], margin)
        case 3:
            txt_min, txt_max = get_limits([82, 111, 171], margin)
        case 0:
            txt_min, txt_max = np.array([0,0,0], np.uint8), np.array([75,75,75], np.uint8)

    text_mask = cv2.inRange(img, txt_min, txt_max)

    # 1) Kontuuripohjainen: piirrä parentit, kaiverra childit pois
    contours, hierarchy = cv2.findContours(text_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    mask_cc = np.zeros_like(text_mask)
    if hierarchy is not None:
        hier = hierarchy[0]
        # piirrä parentit
        for i, cnt in enumerate(contours):
            if int(hier[i][3]) == -1 and cv2.contourArea(cnt) >= 1:
                cv2.drawContours(mask_cc, contours, i, 255, thickness=cv2.FILLED)
        # kaiverra childit pois (varovasti, area‑suodatus myöhemmin)
        for i, cnt in enumerate(contours):
            if int(hier[i][3]) != -1 and cv2.contourArea(cnt) >= 1:
                cv2.drawContours(mask_cc, contours, i, 0, thickness=cv2.FILLED)

    # 2) FloodFill‑varmistus: täytä tausta ja ota komplementti
    flood = mask_cc.copy()
    mask_ff = np.zeros((h+2, w+2), np.uint8)
    cv2.floodFill(flood, mask_ff, (0,0), 255)
    filled = cv2.bitwise_not(flood)  # objektit täytetty, reiät säilyvät

    # yhdistä kontuuri- ja floodFill‑tulokset (OR) — antaa redundanssia
    combined = cv2.bitwise_or(mask_cc, filled)

    # 3) komponenttisuodatus: dynaaminen min_area
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(combined, connectivity=8)
    clean = np.zeros_like(combined)
    abs_min = 20
    rel_min = int(min_black_ratio * w * h)
    min_area = max(abs_min, rel_min)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        # jos komponentti on pieni mutta sisältyy suureen parentiin, säilytä se (suojaus pienille rei'ille)
        x, y, ww, hh, _ = stats[i, :5]
        # etsi parent area (approx): etsi komponentit, jotka sisältävät tämän bboxin ja ovat suurempia
        parent_area = 0
        for j in range(1, num_labels):
            if j == i: continue
            xj, yj, wj, hj, aj = stats[j, :5]
            if x >= xj and y >= yj and (x+ww) <= (xj+wj) and (y+hh) <= (yj+hj):
                parent_area = max(parent_area, aj)
        # päätös: säilytä jos area >= min_area tai jos parent_area on merkittävä ja child on pieni reiän kaltainen
        if area >= min_area or (parent_area > 0 and area <= 0.02 * parent_area):
            clean[labels == i] = 255

    # 4) kevyt puhdistus
    clean = cv2.medianBlur(clean, 3)
    kernel = np.ones((2,2), np.uint8)
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, kernel)

    # 5) fallback jos liian vähän mustaa (suhteellinen)
    black_pixels = int(np.sum(clean == 0))
    if black_pixels < max(15, int(min_black_ratio * clean.size)):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return gray.astype(np.uint8)

    # 6) lopputulos: etuala = musta (0), tausta = valkoinen (255)
    processed = np.full((h,w), 255, dtype=np.uint8)
    processed[clean > 0] = 0

    if debug:
        return {
            "text_mask": text_mask,
            "mask_cc": mask_cc,
            "filled": filled,
            "combined": combined,
            "clean": clean,
            "processed": processed
        }
    return processed.astype(np.uint8)


def preprocess_with_hex(img_bgr, pos, margin=10):
    # Varmista BGR ja dtype
    if img_bgr is None:
        raise ValueError("img_bgr is None")
    img_bgr = img_bgr.copy()
    processed = np.full(img_bgr.shape[:2], 255, dtype=np.uint8)

    def get_limits(base_colors, m):
        arr = np.array(base_colors, dtype=np.int16)
        lower = np.clip(arr - m, 0, 255).astype(np.uint8)
        upper = np.clip(arr + m, 0, 255).astype(np.uint8)
        return lower, upper

    match pos:
        case 1:
            txt_min, txt_max = get_limits([12, 116, 194], margin)
        case 2:
            txt_min, txt_max = get_limits([168, 106, 92], margin)
        case 3:
            txt_min, txt_max = get_limits([82, 111, 171], margin)
        case 0:
            txt_min, txt_max = np.array([0,0,0], dtype=np.uint8), np.array([75,75,75], dtype=np.uint8)
        case _:
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5,5), 0)
            _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            if (np.sum(thresh == 255) / thresh.size) < 0.5:
                thresh = cv2.bitwise_not(thresh)
            return thresh  # grayscale uint8

    text_mask = cv2.inRange(img_bgr, txt_min, txt_max)
    processed[text_mask > 0] = 0
    processed = cv2.medianBlur(processed, 3)
    kernel = np.ones((2,2), np.uint8)
    processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel)
    black_pixels = int(np.sum(processed == 0))
    if black_pixels < 15:
        # Palautetaan grayscale versio alkuperäisestä, ei BGR
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        return gray

    return processed

#Uusi tessocr looppi
def get_score(api, indicator_id, player_name="unknown", attempts=1, rerun=1, pos=0, rotation=1):
    safe_name = "".join(c for c in str(player_name) if c.isalnum() or c in (' ', '_')).strip()
    
    # Alustetaan muuttujat, jotta ne voidaan siivota varmasti lopussa
    screenshot_bgr = None
    pre_processed = None
    processable = None
    final_img = None

    try:
        line = config.get('SCREEN_INDICATORS', indicator_id)
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 5:
            raise ValueError("SCREEN_INDICATORS line malformed")
        x1, y1, x2, y2 = map(int, parts[1:5])

        # 1. Kaappaus ja muunnos
        with ImageGrab.grab(bbox=(x1, y1, x2, y2)) as screenshot_pil:
            screenshot_bgr = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)

        # 2. Esikäsittely valinta
        if rerun < 2:
            pre_processed = preprocess_with_hex(screenshot_bgr, pos)
        else:
            pre_processed = preprocess_with_hex_combined(screenshot_bgr, pos)

        # 3. Skaalauslogiikka (tiivistetty sanakirjaan nopeuden vuoksi)
        scale_map = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6} if rerun == 1 else {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
        scale = scale_map.get(rotation, 2)

        if rerun == 1:
            tmp_scale = cv2.resize(pre_processed, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
            gaussian_blur = cv2.GaussianBlur(tmp_scale, (0, 0), 3)
            unsharp_image = cv2.addWeighted(tmp_scale, 1.5, gaussian_blur, -0.5, 0)
            resized = cv2.resize(unsharp_image, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            blurred = cv2.medianBlur(resized, 3)
            del tmp_scale, gaussian_blur, unsharp_image, resized
        else:
            resized = cv2.resize(pre_processed, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            blurred = cv2.blur(resized, (3, 3))
            del resized

        resized_orig = cv2.resize(screenshot_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

        # 4. Prosessointi
        kernel = np.ones((2, 2), np.uint8)
        processable = cv2.erode(blurred, kernel, iterations=1)
        del blurred

        if len(processable.shape) == 3:
            processable = cv2.cvtColor(processable, cv2.COLOR_BGR2GRAY)
        
        processable_u8 = processable.astype(np.uint8)
        processable_inv = cv2.bitwise_not(processable_u8)

        # 5. MATCH-CASE - Putki
        match attempts:
            case 1: final_img = resized_orig
            case 2: final_img = processable_u8
            case 3: _, final_img = cv2.threshold(processable_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            case 4 | 5:
                iters = 1 if attempts == 4 else 2
                _, thresh = cv2.threshold(processable_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=iters)
                del thresh
            case 6:
                k_sharp = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                sharp = cv2.filter2D(processable_u8, -1, k_sharp)
                _, thresh = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
                del sharp, thresh
            case 7 | 8:
                iters = 1 if attempts == 7 else 2
                _, thresh = cv2.threshold(processable_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.erode(thresh, np.ones((2, 2), np.uint8), iterations=iters)
                del thresh
            case 9: final_img = cv2.bitwise_not(screenshot_bgr)
            case 10: final_img = processable_inv
            case 11: _, final_img = cv2.threshold(processable_inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            case 12 | 13:
                iters = 1 if attempts == 12 else 2
                _, thresh = cv2.threshold(processable_inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=iters)
                del thresh
            case 14:
                k_sharp = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                sharp = cv2.filter2D(processable_inv, -1, k_sharp)
                _, thresh = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
                del sharp, thresh
            case 15 | 16:
                iters = 1 if attempts == 15 else 2
                _, thresh = cv2.threshold(processable_inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.erode(thresh, np.ones((2, 2), np.uint8), iterations=iters)
                del thresh
            case 17:
                if rerun == 2:
                    # Raskas Case 17 optimoituna
                    os_skel = cv2.resize(pre_processed, None, fx=12.0, fy=12.0, interpolation=cv2.INTER_LANCZOS4)
                    g_blur = cv2.GaussianBlur(os_skel, (0, 0), 3)
                    unsharp = cv2.addWeighted(os_skel, 1.5, g_blur, -0.5, 0)
                    gray = cv2.cvtColor(unsharp, cv2.COLOR_BGR2GRAY) if len(unsharp.shape) == 3 else unsharp
                    
                    k_th = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k_th)
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(tophat.astype(np.uint8))
                    _, bw = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    
                    if np.count_nonzero(bw) < (bw.size // 2): bw = cv2.bitwise_not(bw)
                    bw_sep = cv2.erode(bw, np.ones((2, 2), np.uint8), iterations=1)
                    
                    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bw_sep, connectivity=8)
                    mask = np.zeros(bw.shape, dtype=bool)
                    for i in range(1, num_labels):
                        if stats[i, cv2.CC_STAT_AREA] >= 20: mask[labels == i] = True
                    
                    if np.any(mask):
                        skel = (skeletonize(mask.astype(bool)).astype(np.uint8) * 255)
                        # Pruning (tiivistetty)
                        sk = (skel > 0).astype(np.uint8)
                        for _ in range(6):
                            neigh = cv2.filter2D(sk, -1, np.ones((3, 3), np.uint8))
                            endp = np.logical_and(sk == 1, neigh == 2)
                            if not np.any(endp): break
                            sk[endp] = 0
                        final_skel = (sk * 255).astype(np.uint8)
                    else:
                        final_skel = bw_sep

                    dil = cv2.dilate(final_skel, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)), iterations=3)
                    shrunk = cv2.resize(cv2.GaussianBlur(dil, (9, 9), 0), None, fx=(1.0/6.0), fy=(1.0/6.0), interpolation=cv2.INTER_AREA)
                    enh = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(shrunk.astype(np.uint8))
                    final_img = cv2.bitwise_not(cv2.morphologyEx(enh, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))))
                    del os_skel, g_blur, unsharp, tophat, clahe, bw, bw_sep, mask, dil, shrunk, enh
                else: return 0
            case _:
                _, final_img = cv2.threshold(processable_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 6. OCR suoritus
        if len(final_img.shape) == 3:
            final_img = cv2.cvtColor(final_img, cv2.COLOR_BGR2GRAY)
        
        final_img_u8 = final_img.astype(np.uint8)
        with Image.fromarray(final_img_u8) as pil_img:
            api.SetImage(pil_img)
            tulos_teksti = api.GetUTF8Text()
            api.Clear()

        if DEBUG:
            debug_attempt = attempts + (17 if rerun == 2 else 0)
            os.makedirs(DEBUG_DIR, exist_ok=True)
            cv2.imwrite(os.path.join(DEBUG_DIR, f"{safe_name}_proc_att{debug_attempt}.png"), final_img_u8)

        # 7. Loppusiivous ja palautus
        puhdas_numero = "".join(filter(str.isdigit, tulos_teksti))
        return int(puhdas_numero) if puhdas_numero else 0

    except Exception as e:
        print(f"get_score failed for {safe_name}: {e}")
        return None
    finally:
        # Pakotetaan suurten numpy-matriisien vapautus
        del screenshot_bgr, pre_processed, processable, final_img

""" #vanha pytesseract looppi
def get_score(indicator_id, player_name="unknown", attempts=1, rerun=1, pos=0, rotation=1):
    safe_name = "".join(c for c in str(player_name) if c.isalnum() or c in (' ', '_')).strip()
    try:
        line = config.get('SCREEN_INDICATORS', indicator_id)
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 5:
            raise ValueError("SCREEN_INDICATORS line malformed")
        x1, y1, x2, y2 = map(int, parts[1:5])

        # Ota screenshot ja käytä yhtenäistä BGR kuvaa
        screenshot_pil = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        screenshot_bgr = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)

        # Esikäsittely odottaa BGR ja palauttaa grayscale uint8
        if rerun < 2:
            pre_processed = preprocess_with_hex(screenshot_bgr, pos)
        else:
            pre_processed = preprocess_with_hex_combined(screenshot_bgr, pos)

        pre_prosessed_skeletor = pre_processed.copy()
        
        # DEBUG koodi
        os.makedirs(DEBUG_DIR, exist_ok=True)
        if DEBUG: cv2.imwrite(os.path.join(DEBUG_DIR, f"{safe_name}_ORIGINAL.png"), screenshot_bgr)
        # cv2.imwrite(os.path.join(DEBUG_DIR, f"{safe_name}_PRE_PROCESSED.png"), pre_processed)

        # Rerun-polku tai perusreitti
        if rerun == 1:
            # 1. Skaalataan reilusti yli (esim. 6x)
            if rotation == 0:
                scale = 2
            elif rotation == 1:
                scale = 3
            elif rotation == 2:
                scale = 4
            elif rotation == 3:
                scale = 5
            elif rotation == 4:
                scale = 6
            else: scale = 2
                
            overscaled = cv2.resize(pre_processed, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

            # 2. Vahva terävöinti (Unsharp Mask)
            gaussian_blur = cv2.GaussianBlur(overscaled, (0, 0), 3)
            unsharp_image = cv2.addWeighted(overscaled, 1.5, gaussian_blur, -0.5, 0)

            # 3. Skaalataan takaisin tavoitekokoosi (tässä nettona 3x verrattuna alkuun)
            resized = cv2.resize(unsharp_image, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
            blurred = cv2.medianBlur(resized, 3)
        else:
            # PERUSREITTI (Kierros 1)
            if rotation == 0:
                scale = 1
            elif rotation == 1:
                scale = 2
            elif rotation == 2:
                scale = 3
            elif rotation == 3:
                scale = 4
            elif rotation == 4:
                scale = 5
            else: scale = 2
            resized = cv2.resize(pre_processed, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            blurred = cv2.blur(resized, (3, 3))

        resized_orig = cv2.resize(screenshot_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)

        # Dynamiikka
        kernel = np.ones((2, 2), np.uint8)
        processable = cv2.erode(blurred, kernel, iterations=1)

        # Varmista grayscale
        if len(processable.shape) == 3:
            processable = cv2.cvtColor(processable, cv2.COLOR_BGR2GRAY)
        processable = processable.astype(np.uint8)

        # Default final_img
        final_img = processable.copy()
        # Invert uint8 (käytetään inverted-polkuja)
        processable_inverted = cv2.bitwise_not(processable)

        match attempts:
            case 1:
                # Palauta alkuperäinen screenshot (mutta muunna grayscale ennen OCR)
                final_img = resized_orig
            case 2:
                final_img = processable
            case 3:
                _, final_img = cv2.threshold(processable, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            case 4:
                _, thresh = cv2.threshold(processable, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
            case 5:
                _, thresh = cv2.threshold(processable, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=2)
            case 6:
                kernel_sharp = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                sharpened = cv2.filter2D(processable, -1, kernel_sharp)
                _, thresh = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
            case 7:
                _, thresh = cv2.threshold(processable, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.erode(thresh, np.ones((2, 2), np.uint8), iterations=1)
            case 8:
                _, thresh = cv2.threshold(processable, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.erode(thresh, np.ones((2, 2), np.uint8), iterations=2)
            case 9:
                screenshot_bgr_inverted = cv2.bitwise_not(screenshot_bgr)
                final_img = screenshot_bgr_inverted
            case 10:
                final_img = processable_inverted
            case 11:
                _, final_img = cv2.threshold(processable_inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            case 12:
                _, thresh = cv2.threshold(processable_inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
            case 13:
                _, thresh = cv2.threshold(processable_inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=2)
            case 14:
                kernel_sharp = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
                sharpened = cv2.filter2D(processable_inverted, -1, kernel_sharp)
                _, thresh = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.dilate(thresh, np.ones((2, 2), np.uint8), iterations=1)
            case 15:
                _, thresh = cv2.threshold(processable_inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.erode(thresh, np.ones((2, 2), np.uint8), iterations=1)
            case 16:
                _, thresh = cv2.threshold(processable_inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                final_img = cv2.erode(thresh, np.ones((2, 2), np.uint8), iterations=2)
            case 17:
                if rerun == 2:
                    # 1. Overscale
                    overscaled = cv2.resize(pre_prosessed_skeletor, None, fx=12.0, fy=12.0, interpolation=cv2.INTER_LANCZOS4)

                    # 2. Unsharp mask (terävöitys)
                    gaussian_blur = cv2.GaussianBlur(overscaled, (0, 0), 3)
                    unsharp_image = cv2.addWeighted(overscaled, 1.5, gaussian_blur, -0.5, 0)

                    # 3. Harmaasävy + TopHat
                    if len(unsharp_image.shape) == 3:
                        gray = cv2.cvtColor(unsharp_image, cv2.COLOR_BGR2GRAY)
                    else:
                        gray = unsharp_image.copy()

                    kernel_th = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                    tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel_th)

                    # 4. CLAHE + Otsu
                    clahe_init = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    enh_init = clahe_init.apply(tophat.astype(np.uint8))
                    _, bw = cv2.threshold(enh_init, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                    # 5. Varmista että etuala on valkoinen (korjattu ehto)
                    # Jos valkoisia pikseleitä on vähemmän kuin puolet, inverttoi jotta etuala on valkoinen
                    if np.count_nonzero(bw) < (bw.size // 2):
                        bw = cv2.bitwise_not(bw)

                    # 6. Pienten komponenttien poisto (kohinan suodatus)
                    bw_separated = cv2.erode(bw, np.ones((2, 2), np.uint8), iterations=1)
                    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bw_separated, connectivity=8)
                    mask = np.zeros(bw.shape, dtype=bool)
                    min_area = 20
                    for i in range(1, num_labels):
                        if stats[i, cv2.CC_STAT_AREA] >= min_area:
                            mask[labels == i] = True

                    # 7. Skeletonize & Pruning (muunna booleaniksi ennen skeletonize)
                    if np.any(mask):
                        skeleton_bool = skeletonize(mask.astype(bool))
                        skeleton_uint8 = (skeleton_bool.astype(np.uint8) * 255)
                    else:
                        skeleton_uint8 = bw_separated.copy()

                    def prune_skeleton(skel_uint8, iterations=6):
                        # skel_uint8: 0/255 uint8
                        sk = (skel_uint8 > 0).astype(np.uint8)  # 0/1
                        neigh_kernel = np.ones((3, 3), np.uint8)
                        for _ in range(iterations):
                            neigh = cv2.filter2D(sk, -1, neigh_kernel)  # laskee itse mukaan
                            # endpoint: itse=1 ja yhteensä 2 (itse + 1 naapuri)
                            endpoints = np.logical_and(sk == 1, neigh == 2)
                            if not np.any(endpoints):
                                break
                            sk[endpoints] = 0
                        return (sk * 255).astype(np.uint8)

                    pruned = prune_skeleton(skeleton_uint8, iterations=6)

                    # 8. Lihavointi (elliptinen kernel); pienennä iteraatioita jos massa kasvaa liikaa
                    kernel_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
                    dilated = cv2.dilate(pruned, kernel_dil, iterations=3)

                    # 9. Pehmennys & skaalaus takaisin (pienempi blur kuin alkuperäisessä)
                    blurred_final = cv2.GaussianBlur(dilated, (9, 9), 0)
                    final_scale = 1.0 / 6.0
                    shrunk = cv2.resize(blurred_final, None, fx=final_scale, fy=final_scale, interpolation=cv2.INTER_AREA)

                    # 10. Lopullinen kontrasti, closing ja invert (varmista uint8)
                    shrunk_u8 = shrunk.astype(np.uint8)
                    clahe_final = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
                    enhanced_final = clahe_final.apply(shrunk_u8)

                    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
                    final_img_tmp = cv2.morphologyEx(enhanced_final, cv2.MORPH_CLOSE, kernel_close)

                    # Tulos: musta teksti valkoisella pohjalla
                    final_img = cv2.bitwise_not(final_img_tmp)
                else:
                    return 0


            case _:
                # Jos tuntematon attempts, käytä perusthresholdia
                _, final_img = cv2.threshold(processable, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Varmista, että final_img on single-channel uint8 ennen OCR
        if len(final_img.shape) == 3:
            final_img = cv2.cvtColor(final_img, cv2.COLOR_BGR2GRAY)
        final_img = final_img.astype(np.uint8)

        # OCR ja postprocessing
        config_params = '--psm 7 -c tessedit_char_whitelist=0123456789.,'
        tulos_teksti = pytesseract.image_to_string(final_img, config=config_params)

        # debug_attempt erillisenä, jotta alkuperäinen attempts säilyy
        debug_attempt = attempts + (17 if rerun == 2 else 0)
        if DEBUG: cv2.imwrite(os.path.join(DEBUG_DIR, f"{safe_name}_proc_att{debug_attempt}.png"), final_img)

        # Poimi vain numerot (kokonaisluku)
        puhdas_numero_str = "".join(filter(str.isdigit, tulos_teksti))
        if puhdas_numero_str:
            return int(puhdas_numero_str)
        else:
            return 0

    except Exception as e:
        # Tulosta poikkeus ja palauta None, jotta virhe erotetaan nollatuloksesta
        print(f"get_score failed for {safe_name}: {e}")
        return None
"""
def capture_pfp(playerID):
    time.sleep(1)
    try:
        out("Capturing the pfp")
        screenshot_pil = ImageGrab.grab(bbox=(897, 283, 1661, 1052))
    except Exception as e:
        out(f"screen capture error {e}")
        return None
    try:
        out("converting pfp to BGR")
        screenshot_bgr = cv2.cvtColor(np.array(screenshot_pil), cv2.COLOR_RGB2BGR)
    except Exception as e:
        if screenshot_pil is None:
            out("image grab returned an empty array")
        out(f"pfp conversion error {e}")
        return None
    os.makedirs(PFP_PATH, exist_ok=True)
    try:
        out("Attempting to write the pfp to DEBUG folder")
        #playerID ="bobert_the_debugger"
        path = os.path.join(PFP_PATH, f"{playerID}_pfp.png")
        cv2.imwrite(path, screenshot_bgr)
    except Exception as e:
        out(f"pfp save error {e}")
        return None
    time.sleep(0.2)
    return path