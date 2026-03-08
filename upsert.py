import os
import csv
import psycopg2
import sqlite3
import gspread
import json
from datetime import datetime
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials

# --- KONFIGURAATION LATAUS ---
def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "DB_CONFIG.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Konfiguraatiotiedostoa {config_path} ei löydy!")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

# Erotetaan PostgreSQL-yhteystiedot omaan sanakirjaansa
DB_PARAMS = {k: CONFIG[k] for k in ["dbname", "user", "password", "host", "port"]}

class RoKDatabaseManager:
    def __init__(self):
        # Käytetään dynaamisesti ladattuja asetuksia
        self.pg_conn = psycopg2.connect(**DB_PARAMS)
        self.pg_cur = self.pg_conn.cursor()
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CONFIG['json_key_path'], scope)
        self.gc = gspread.authorize(creds)
        print("✅ Vaihe 0: Yhteydet avattu (JSON-konfiguraatio käytössä).")

    def normalize_id(self, pid):
        if not pid: return ""
        return str(pid).strip().upper().replace("-0O", "-00")

    def run_sync(self):
        now = datetime.now()
        master_data = defaultdict(lambda: {
            'name': 'Unknown', 'power': 0, 'kills': 0, 'donations': 0,
            'vs': {'mon': 0, 'tue': 0, 'wed': 0, 'thu': 0, 'fri': 0, 'sat': 0},
            't1': 0.0, 't2': 0.0
        })

        # 1. HAETAAN NIMET (SQLITE)
        sl_conn = sqlite3.connect(CONFIG['sqlite_path'])
        sl_cur = sl_conn.cursor()
        sl_cur.execute("SELECT player_id, name FROM players")
        name_registry = {self.normalize_id(pid): name.strip() for pid, name in sl_cur.fetchall() if pid}
        sl_conn.close()
        print(f"✅ Vaihe 1: Master-nimet ladattu ({len(name_registry)} kpl).")

        # 2. LUETAAN CSV-TIEDOSTOT
        day_map = {
            '_mon.csv': 'mon', '_tues.csv': 'tue', '_wed.csv': 'wed', 
            '_thur.csv': 'thu', '_fri.csv': 'fri', '_sat.csv': 'sat'
        }
        
        res_folder = CONFIG['results_folder']
        files = [f for f in os.listdir(res_folder) if f.endswith('.csv')]
        
        # Haetaan viikon numero tiedostonimestä tai nykyisestä päivästä
        week_num = next((int(f.split('_')[0]) for f in files if '_' in f and f.split('_')[0].isdigit()), now.isocalendar()[1])
        
        print(f"🚀 Vaihe 2: Luetaan CSV-data kansiosta {res_folder} (Viikko {week_num})...")
        for filename in files:
            tag = filename.lower()
            if "_wk" in tag or "week" in tag:
                continue

            path = os.path.join(res_folder, filename)
            with open(path, mode='r', encoding='utf-8') as f:
                content = f.read(2048)
                delim = ';' if ';' in content else ','
                f.seek(0)
                reader = csv.DictReader(f, delimiter=delim)
                
                for row in reader:
                    # Siivotaan sarakkeiden nimet (poistetaan erikoismerkit)
                    row = {str(k).encode('ascii', 'ignore').decode().strip().lower(): v for k, v in row.items() if k}
                    pid = self.normalize_id(row.get('player_id', ''))
                    if not pid: continue

                    master_data[pid]['name'] = name_registry.get(pid, row.get('playername') or row.get('name') or master_data[pid]['name'])
                    
                    val = self.safe_int(row.get('value') or row.get('score') or 0)
                    if "power_results" in tag: master_data[pid]['power'] = val
                    elif "kills_results" in tag: master_data[pid]['kills'] = val
                    elif "donations_results" in tag: master_data[pid]['donations'] = val
                    
                    for suffix, day_key in day_map.items():
                        if tag.endswith(suffix): master_data[pid]['vs'][day_key] = val

        # 3. SHEETS (T1/T2)
        print("📊 Vaihe 3: Haetaan T1/T2 arvot...")
        # Huom: Käytetään JSONista 'sheet_name' -asetusta
        sheet = self.gc.open(CONFIG['sheet_name']).worksheet("Upsert")
        for s_row in sheet.get_all_values():
            s_pid = self.normalize_id(s_row[0])
            if s_pid in master_data:
                master_data[s_pid]['t1'] = self.safe_float(s_row[2])
                master_data[s_pid]['t2'] = self.safe_float(s_row[3])

        # 4. TALLENNUS JA LEGACY (POSTGRESQL)
        print(f"💾 Vaihe 4: Kirjoitetaan kantaan ({len(master_data)} pelaajaa)...")
        power_ids = set()
        for pid, d in master_data.items():
            if d['power'] > 0: power_ids.add(pid)
            
            # Upsert active_players
            self.pg_cur.execute(
                "INSERT INTO active_players (player_id, name, last_seen) VALUES (%s, %s, %s) "
                "ON CONFLICT (player_id) DO UPDATE SET name = EXCLUDED.name, last_seen = EXCLUDED.last_seen", 
                (pid, d['name'], now)
            )

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
        
        # 5. LEGACY-TARKISTUS
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
    try:
        mgr = RoKDatabaseManager()
        mgr.run_sync()
    except Exception as e:
        print(f"❌ KRIITTINEN VIRHE: {e}")
    finally:
        if 'mgr' in locals():
            mgr.close()
    input("\nValmis...")