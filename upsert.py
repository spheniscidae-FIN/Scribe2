import os
import csv
import psycopg2
import gspread
import traceback
from datetime import datetime
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
DB_CONFIG = {
    "dbname": "rok_stats",
    "user": "upsert_user",
    "password": "Kissahemuli666!",  # Vaihda tämä turvallisesti
    "host": "192.168.68.63",
    "port": "5432"
}

SHEET_NAME = "Squadpower"
JSON_KEY_PATH = "scribe-sync-488917-4d7c6c9d0021.json"
RESULTS_FOLDER = "./results"

def safe_int(val, default=0):
    try:
        if val is None:
            return default
        s = str(val).strip()
        if s == "":
            return default
        # Poista mahdolliset ei-numeraaliset merkit
        s = ''.join(ch for ch in s if ch.isdigit() or ch == '-' )
        return int(s) if s != "" else default
    except Exception:
        return default

def safe_number_from_text(val, default=0):
    try:
        if val is None:
            return default
        s = str(val).strip()
        if s == "":
            return default
        # Korvaa pilkku pisteeksi, poista muut merkit paitsi numerot ja piste
        s = s.replace(',', '.')
        cleaned = ''.join(ch for ch in s if ch.isdigit() or ch == '.' or ch == '-')
        # Jos useita pisteitä, pidetään viimeinen piste desimaalierottimena
        if cleaned.count('.') > 1:
            parts = cleaned.split('.')
            cleaned = ''.join(parts[:-1]).replace('.', '') + '.' + parts[-1]
        return float(cleaned)
    except Exception:
        return default

class RoKDatabaseManager:
    def __init__(self):
        self.pg_conn = None
        self.pg_cur = None
        self.gc = None

        # 1. PostgreSQL Yhteys
        try:
            print("DEBUG: Yritetään avata tietokantayhteys...")
            self.pg_conn = psycopg2.connect(**DB_CONFIG)
            self.pg_cur = self.pg_conn.cursor()
            print(" OK: Tietokantayhteys avattu.")
        except Exception as e:
            print("ERROR: Virhe tietokantayhteydessä:")
            traceback.print_exc()
            # älä exit() — anna kutsujan käsitellä
            raise

        # 2. Google Sheets Yhteys
        try:
            print("DEBUG: Yritetään avata Google Sheets -yhteys...")
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_PATH, scope)
            self.gc = gspread.authorize(creds)
            print(" OK: Google Sheets yhteys avattu.")
        except Exception as e:
            print("ERROR: Virhe Google Sheets -yhteydessä:")
            traceback.print_exc()
            raise

    def get_squad_powers_from_sheets(self):
        """Hakee T1/T2 tiedot Sheetsistä (A: ID, B: Time, C: T1, D: T2)"""
        try:
            print(f"DEBUG: Avataan sheet: {SHEET_NAME} / Upsert")
            sheet = self.gc.open(SHEET_NAME).worksheet("Upsert")
            rows = sheet.get_all_values()[1:]  # Hypätään otsikko yli
            print(f"DEBUG: Sheets rivit haettu: {len(rows)}")
            
            squad_map = {}
            for row in rows:
                if not row or not row[0]:
                    continue
                p_id = str(row[0]).strip()
                # C = T1 (index 2), D = T2 (index 3)
                t1 = safe_number_from_text(row[2]) if len(row) > 2 else 0
                t2 = safe_number_from_text(row[3]) if len(row) > 3 else 0
                squad_map[p_id] = (t1, t2)
            return squad_map
        except Exception:
            print("ERROR: Sheets-haku epäonnistui:")
            traceback.print_exc()
            return {}

    def collect_ocr_data(self):
        """Yhdistää kaikki CSV-tiedostot results-kansiosta"""
        combined = defaultdict(lambda: {
            'name': 'Unknown', 'power': 0, 'kills': 0, 'donations': 0,
            'vs': {'mon': 0, 'tue': 0, 'wed': 0, 'thu': 0, 'fri': 0, 'sat': 0}
        })

        day_map = {
            '_mon': 'mon',
            '_tues': 'tue',
            '_wed': 'wed',
            '_thur': 'thu',
            '_fri': 'fri',
            '_sat': 'sat'
        }

        if not os.path.exists(RESULTS_FOLDER):
            print(f"ERROR: Kansiota {RESULTS_FOLDER} ei löydy.")
            return {}

        files = [f for f in os.listdir(RESULTS_FOLDER) if f.endswith('.csv')]
        print(f"DEBUG: Löydettiin {len(files)} tiedostoa: {files}")

        for filename in files:
            path = os.path.join(RESULTS_FOLDER, filename)
            tag = filename.lower()
            try:
                with open(path, mode='r', encoding='utf-8') as f:
                    content = f.read(4096)
                    dialect_delim = ';' if ';' in content else ','
                    f.seek(0)
                    reader = csv.DictReader(f, delimiter=dialect_delim)
                    for row in reader:
                        # Siivotaan sarakkeiden nimet (poistetaan mahdolliset välilyönnit)
                        row = { (k.strip().lower() if k else k): v for k, v in row.items() }
                        p_id = (row.get('player_id') or '').strip()
                        if not p_id:
                            continue
                        if 'name' in row and row.get('name'):
                            combined[p_id]['name'] = row.get('name')
                        # 1. Tarkistetaan Power, Kills, Donations
                        if 'power' in tag:
                            combined[p_id]['power'] = safe_int(row.get('power', 0))
                        elif 'kills' in tag:
                            combined[p_id]['kills'] = safe_int(row.get('kills', 0))
                        elif 'donations' in tag:
                            combined[p_id]['donations'] = safe_int(row.get('donations', 0))
                        # 2. VS-päivät tiedostonimen perusteella
                        for suffix, day_key in day_map.items():
                            if suffix in tag:
                                score_raw = row.get('score') or row.get('points') or row.get('vs') or 0
                                combined[p_id]['vs'][day_key] = safe_int(score_raw)
            except Exception:
                print(f"ERROR: Virhe käsiteltäessä tiedostoa {filename}:")
                traceback.print_exc()
                continue

        return combined

    def run_sync(self):
        now = datetime.now()
        year, week_num, _ = now.isocalendar()
        print(f"DEBUG: Aloitetaan synkronointi: Vuosi {year}, Viikko {week_num}")

        ocr_data = self.collect_ocr_data()
        squad_data = self.get_squad_powers_from_sheets()

        if not ocr_data:
            print("INFO: Ei ladattavaa OCR-dataa. Tarkista results-kansio.")
            return

        for p_id, data in ocr_data.items():
            t1, t2 = squad_data.get(p_id, (0, 0))
            vs = data['vs']

            try:
                # 1. Päivitä Active Players
                self.pg_cur.execute(
                    """
                    INSERT INTO active_players (player_id, name, last_seen)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (player_id) DO UPDATE
                    SET name = EXCLUDED.name, last_seen = EXCLUDED.last_seen;
                    """,
                    (p_id, data['name'], now)
                )

                # 2. Päivitä Snapshot
                self.pg_cur.execute(
                    """
                    INSERT INTO player_snapshots (
                        player_id, year, week_number, snapshot_date,
                        power_total, kills_total, donations_total, t1_power, t2_power,
                        vs_mon, vs_tue, vs_wed, vs_thu, vs_fri, vs_sat
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (player_id, year, week_number) DO UPDATE SET
                        power_total = EXCLUDED.power_total,
                        kills_total = EXCLUDED.kills_total,
                        donations_total = EXCLUDED.donations_total,
                        t1_power = EXCLUDED.t1_power,
                        t2_power = EXCLUDED.t2_power,
                        vs_mon = EXCLUDED.vs_mon, vs_tue = EXCLUDED.vs_tue, vs_wed = EXCLUDED.vs_wed,
                        vs_thu = EXCLUDED.vs_thu, vs_fri = EXCLUDED.vs_fri, vs_sat = EXCLUDED.vs_sat;
                    """,
                    (
                        p_id, year, week_num, now.date(),
                        data['power'], data['kills'], data['donations'], t1, t2,
                        vs['mon'], vs['tue'], vs['wed'], vs['thu'], vs['fri'], vs['sat']
                    )
                )
            except Exception:
                print(f"ERROR: Virhe pelaajan {p_id} kohdalla:")
                traceback.print_exc()
                self.pg_conn.rollback()
                continue

        self.pg_conn.commit()
        print(f"OK: Valmis! {len(ocr_data)} pelaajan tiedot päivitetty.")

    def close(self):
        try:
            if self.pg_cur:
                self.pg_cur.close()
            if self.pg_conn:
                self.pg_conn.close()
            print("DEBUG: Tietokantayhteys suljettu.")
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    print("--- ALOITETAAN DIAGNOOSI ---")
    try:
        manager = None
        try:
            manager = RoKDatabaseManager()
        except Exception as e:
            print("CRITICAL: Alustus epäonnistui. Katso yllä oleva stacktrace.")
            raise

        files = [f for f in os.listdir(RESULTS_FOLDER) if f.endswith('.csv')]
        print(f"1. Löytyneet CSV-tiedostot kansiosta '{RESULTS_FOLDER}': {files}")

        if not files:
            print(" VIRHE: Kansiossa ei ole .csv tiedostoja!")
        else:
            manager.run_sync()

    except Exception as e:
        print(" KRIITTINEN VIRHE (pääohjelmassa):")
        traceback.print_exc()
    finally:
        if 'manager' in locals() and manager:
            try:
                manager.close()
            except Exception:
                pass

    input("\nPAINA ENTER SULKEAKSESI TÄMÄN IKKUNAN...")
