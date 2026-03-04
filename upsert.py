import os
import csv
import psycopg2
import sqlite3
import gspread
from datetime import datetime
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# --- KONFIGURAATIO ---
DB_CONFIG = {
    "dbname": "rok_stats", "user": "upsert_user", 
    "password": "Kissahemuli666!", "host": "192.168.68.63", "port": "5432"
}
PLAYERS_DB_SQLITE = "Q:/Skriptit/Scribe2/DATA/DATABASE/Players.db" 
RESULTS_FOLDER = "./results"
SHEET_NAME = "Squadpower"
JSON_KEY_PATH = "scribe-sync-488917-4d7c6c9d0021.json"

class RoKDatabaseManager:
    def __init__(self):
        self.pg_conn = psycopg2.connect(**DB_CONFIG)
        self.pg_cur = self.pg_conn.cursor()
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_PATH, scope)
        self.gc = gspread.authorize(creds)
        print("✅ Vaihe 0: Yhteydet avattu.")

    def normalize_id(self, pid):
        """Varmistaa, että 0 ja O eivät riko ID-vertailua."""
        if not pid: return ""
        # Pakotetaan kaikki muotoon, jossa käytetään nollaa (0) 'O':n sijaan kriittisessä kohdassa
        return str(pid).strip().upper().replace("-0O", "-00")

    def run_sync(self):
        now = datetime.now()
        master_data = defaultdict(lambda: {
            'name': 'Unknown', 'power': 0, 'kills': 0, 'donations': 0,
            'vs': {'mon': 0, 'tue': 0, 'wed': 0, 'thu': 0, 'fri': 0, 'sat': 0},
            't1': 0.0, 't2': 0.0
        })

        # 1. HAETAAN NIMET
        sl_conn = sqlite3.connect(PLAYERS_DB_SQLITE)
        sl_cur = sl_conn.cursor()
        sl_cur.execute("SELECT player_id, name FROM players")
        name_registry = {self.normalize_id(pid): name.strip() for pid, name in sl_cur.fetchall() if pid}
        sl_conn.close()
        print(f"✅ Vaihe 1: Master-nimet ladattu ({len(name_registry)} kpl).")

        # 2. LUETAAN CSV-TIEDOSTOT (Ilman viikkolistoja)
        day_map = {
            '_mon.csv': 'mon', '_tues.csv': 'tue', '_wed.csv': 'wed', 
            '_thur.csv': 'thu', '_fri.csv': 'fri', '_sat.csv': 'sat'
        }
        
        files = [f for f in os.listdir(RESULTS_FOLDER) if f.endswith('.csv')]
        week_num = next((int(f.split('_')[0]) for f in files if '_' in f and f.split('_')[0].isdigit()), now.isocalendar()[1])
        
        print(f"🚀 Vaihe 2: Luetaan CSV-data (Viikko {week_num})...")
        for filename in files:
            tag = filename.lower()
            # SKIPPATAAN VIIKKOLISTAT (Häröpallon välttämiseksi)
            if "_wk" in tag or "week" in tag:
                print(f"   - Ohitetaan turha viikkolista: {filename}")
                continue

            path = os.path.join(RESULTS_FOLDER, filename)
            with open(path, mode='r', encoding='utf-8') as f:
                content = f.read(2048)
                delim = ';' if ';' in content else ','
                f.seek(0)
                reader = csv.DictReader(f, delimiter=delim)
                
                for row in reader:
                    row = {str(k).encode('ascii', 'ignore').decode().strip().lower(): v for k, v in row.items() if k}
                    pid = self.normalize_id(row.get('player_id', ''))
                    if not pid: continue

                    # Asetetaan nimi master-rekisteristä
                    master_data[pid]['name'] = name_registry.get(pid, row.get('playername') or row.get('name') or master_data[pid]['name'])
                    
                    val = self.safe_int(row.get('value') or row.get('score') or 0)
                    if "power_results" in tag: master_data[pid]['power'] = val
                    elif "kills_results" in tag: master_data[pid]['kills'] = val
                    elif "donations_results" in tag: master_data[pid]['donations'] = val
                    
                    for suffix, day_key in day_map.items():
                        if tag.endswith(suffix): master_data[pid]['vs'][day_key] = val

        # 3. SHEETS (T1/T2)
        print("📊 Vaihe 3: Haetaan T1/T2 arvot...")
        sheet = self.gc.open(SHEET_NAME).worksheet("Upsert")
        for s_row in sheet.get_all_values():
            s_pid = self.normalize_id(s_row[0])
            if s_pid in master_data:
                master_data[s_pid]['t1'] = self.safe_float(s_row[2])
                master_data[s_pid]['t2'] = self.safe_float(s_row[3])

        # 4. TALLENNUS JA LEGACY
        print(f"💾 Vaihe 4: Kirjoitetaan kantaan ({len(master_data)} pelaajaa)...")
        power_ids = set()
        for pid, d in master_data.items():
            if d['power'] > 0: power_ids.add(pid)
            
            # Upsert active_players
            self.pg_cur.execute("INSERT INTO active_players (player_id, name, last_seen) VALUES (%s, %s, %s) "
                                "ON CONFLICT (player_id) DO UPDATE SET name = EXCLUDED.name, last_seen = EXCLUDED.last_seen", 
                                (pid, d['name'], now))

            # Upsert snapshots
            vs_total = sum(d['vs'].values())
            self.pg_cur.execute("""
                INSERT INTO player_snapshots (
                    player_id, year, week_number, snapshot_date, power_total, kills_total, donations_total, 
                    t1_power, t2_power, vs_mon, vs_tue, vs_wed, vs_thu, vs_fri, vs_sat, vs_weekly_total
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_id, year, week_number) DO UPDATE SET
                    power_total=EXCLUDED.power_total, kills_total=EXCLUDED.kills_total, donations_total=EXCLUDED.donations_total,
                    t1_power=EXCLUDED.t1_power, t2_power=EXCLUDED.t2_power, vs_mon=EXCLUDED.vs_mon, vs_tue=EXCLUDED.vs_tue,
                    vs_wed=EXCLUDED.vs_wed, vs_thu=EXCLUDED.vs_thu, vs_fri=EXCLUDED.vs_fri, vs_sat=EXCLUDED.vs_sat, 
                    vs_weekly_total=EXCLUDED.vs_weekly_total;
            """, (pid, now.year, week_num, now.date(), d['power'], d['kills'], d['donations'], d['t1'], d['t2'],
                  d['vs']['mon'], d['vs']['tue'], d['vs']['wed'], d['vs']['thu'], d['vs']['fri'], d['vs']['sat'], vs_total))
        
        self.pg_conn.commit()
        
        # LEGACY-TARKISTUS
        print("🧹 Vaihe 5: Legacy-tarkistus...")
        self.pg_cur.execute("SELECT player_id, name FROM active_players")
        for p_id, db_name in self.pg_cur.fetchall():
            pid_s = self.normalize_id(p_id)
            if pid_s not in power_ids:
                real_name = name_registry.get(pid_s, db_name)
                print(f"   👋 {real_name} (ID: {pid_s}) -> Legacyyn.")
                self.pg_cur.execute("INSERT INTO legacy_players (player_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (pid_s, real_name))
                self.pg_cur.execute("DELETE FROM active_players WHERE player_id = %s", (pid_s,))
        
        self.pg_conn.commit()
        print(f"✨ VALMIS. Viikko {week_num} synkattu.")

    def safe_int(self, v, d=0):
        try: return int(''.join(filter(str.isdigit, str(v)))) if v else d
        except: return d

    def safe_float(self, v, d=0.0):
        try: return float(str(v).replace(',', '.')) if v else d
        except: return d

    def close(self):
        self.pg_cur.close()
        self.pg_conn.close()

if __name__ == "__main__":
    mgr = RoKDatabaseManager()
    try:
        mgr.run_sync()
    finally:
        mgr.close()
    input("\nValmis...")

