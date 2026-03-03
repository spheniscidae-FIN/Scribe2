import psycopg2
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

class RoKUniverseManager:
    def __init__(self, pg_host, pg_password, json_key_path):
        # 1. PostgreSQL Yhteys (upsert_user)
        self.pg_conn = psycopg2.connect(
            dbname="rok_stats",
            user="upsert_user",
            password=pg_password,
            host=pg_host,
            port="5432"
        )
        self.pg_cur = self.pg_conn.cursor()

        # 2. Google Sheets Yhteys (Scribe-sync)
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, scope)
        self.gc = gspread.authorize(creds)
        
    def get_squad_powers_from_sheets(self):
        """Hakee T1 ja T2 tiedot 'Upsert'-välilehdeltä."""
        try:
            # Avataan oikea välilehti
            sheet = self.gc.open("Squadpower").worksheet("Upsert")
            
            # Haetaan kaikki data (aloitetaan riviltä 2, jotta otsikot hypätään yli)
            # A=ID, B=T1, C=T2
            list_of_lists = sheet.get_all_values()[1:] 
            
            squad_map = {}
            for row in list_of_lists:
                if not row[0]: # Hypätään yli jos ID puuttuu
                    continue
                    
                p_id = str(row[0]).strip()
                
                # T1 käsittely (sarake B)
                t1 = int(row[1]) if len(row) > 1 and str(row[1]).isdigit() else 0
                
                # T2 käsittely (sarake C), voi olla tyhjä
                t2 = int(row[2]) if len(row) > 2 and str(row[2]).isdigit() else 0
                
                squad_map[p_id] = (t1, t2)
                
            return squad_map
        except Exception as e:
            print(f"Sheets-virhe: {e}")
            return {}

    def run_weekly_upsert(self, ocr_results):
        """
        Yhdistää OCR-datan ja Sheets-datan PostgreSQL:ään.
        ocr_results: Lista sanakirjoja Gemini OCR:ltä.
        """
        now = datetime.now()
        year, week_num, _ = now.isocalendar()
        
        # Haetaan T1/T2 arvot Upsert-taulusta
        squad_powers = self.get_squad_powers_from_sheets()

        for data in ocr_results:
            p_id = str(data['id']).strip()
            # Jos ID löytyy Sheetsistä, käytetään sieltä saatuja T-arvoja, muuten 0
            t1, t2 = squad_powers.get(p_id, (0, 0))

            try:
                # 1. Päivitä Active_players (nimi ja last_seen)
                self.pg_cur.execute("""
                    INSERT INTO active_players (player_id, name, last_seen)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (player_id) DO UPDATE 
                    SET name = EXCLUDED.name, last_seen = EXCLUDED.last_seen;
                """, (p_id, data['name'], now))

                # 2. Päivitä viikkosnapshot mukaan lukien T1/T2
                self.pg_cur.execute("""
                    INSERT INTO player_snapshots (
                        player_id, year, week_number, snapshot_date, 
                        power_total, kills_total, t1_power, t2_power,
                        vs_mon, vs_tue, vs_wed, vs_thu, vs_fri, vs_sat, vs_sun
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (player_id, year, week_number) DO UPDATE SET 
                        power_total = EXCLUDED.power_total,
                        kills_total = EXCLUDED.kills_total,
                        t1_power = EXCLUDED.t1_power,
                        t2_power = EXCLUDED.t2_power,
                        vs_mon = EXCLUDED.vs_mon, vs_tue = EXCLUDED.vs_tue, 
                        vs_wed = EXCLUDED.vs_wed, vs_thu = EXCLUDED.vs_thu, 
                        vs_fri = EXCLUDED.vs_fri, vs_sat = EXCLUDED.vs_sat, 
                        vs_sun = EXCLUDED.vs_sun;
                """, (
                    p_id, year, week_num, now.date(),
                    data['power'], data['kills'], t1, t2,
                    data.get('vs_mon', 0), data.get('vs_tue', 0), data.get('vs_wed', 0),
                    data.get('vs_thu', 0), data.get('vs_fri', 0), data.get('vs_sat', 0),
                    data.get('vs_sun', 0)
                ))
            except Exception as e:
                print(f"Virhe pelaajan {p_id} ({data['name']}) tallennuksessa: {e}")
                self.pg_conn.rollback()
                continue
        
        self.pg_conn.commit()
        print(f"Viikon {week_num} data päivitetty onnistuneesti.")

    def close(self):
        self.pg_cur.close()
        self.pg_conn.close()