import os
import csv
import json
import time
from google import genai
from google.genai import types

# --- KONFIGURAATIO ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Polku JSON-tiedostoon
KEYS_PATH = os.path.join(BASE_DIR, 'DATA', 'Config', 'GeminiAPI.json')
def load_api_key():
    try:
        if not os.path.exists(KEYS_PATH):
            print(f"!!! VIRHE: API-avainta ei löytynyt polusta: {KEYS_PATH}")
            return None
        with open(KEYS_PATH, 'r') as f:
            data = json.load(f)
            return data.get("GEMINI_API_KEY")
    except Exception as e:
        print(f"!!! Virhe avaimen luvussa: {e}")
        return None

GEMINI_API_KEY = load_api_key()
UPLOAD_DIR = "UPLOADS"
RESULTS_DIR = "RESULTS"
# LISÄTTY: SATURDAY kategoriaan
CATEGORIES = ["POWER", "DONATIONS", "KILLS", "SATURDAY"]

# Alustetaan client
client = genai.Client(api_key=GEMINI_API_KEY)

def process_image_with_retry(image_path, category, retries=3):
    # MUOKATTU PROMPT: Lisätty ohjeistus klaanitagin ja liiton nimen sivuuttamisesta
    prompt = f"""
    Analyze this game ranking screenshot for the category: {category}.
    Extract: Rank (integer), Player Name (string), and the numerical Value (integer).
    
    IMPORTANT: 
    - When extracting the 'Player Name', IGNORE the alliance tag and name like '[FRB3] FireBringers'. 
    - Return only the player's own nickname.
    
    Return ONLY a JSON array of objects. 
    Example: [{{"rank": 1, "name": "Player1", "value": 1500000}}]
    """

    for attempt in range(retries):
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            response = client.models.generate_content(
                model='gemini-2.5-flash', # Huom: vaihdettu vakaaseen mallinimeen jos gemini-2.5 ei ole saatavilla
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                ]
            )
            
            raw_text = response.text.strip()
            
            # Puhdistetaan koodilohkot (```json ... ```)
            if "```" in raw_text:
                start = raw_text.find("[")
                end = raw_text.rfind("]") + 1
                if start != -1 and end != -1:
                    raw_text = raw_text[start:end]
            
            return json.loads(raw_text)
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "perday" in error_msg.replace(" ", ""):
                print("\n!!! PÄIVÄKIINTIÖ TÄYNNÄ. Ohjelma pysähtyy.")
                return "DAILY_QUOTA_REACHED"

            if "429" in error_msg or "quota" in error_msg:
                wait_time = 35
                print(f"      ! Kiintiö täynnä. Odotetaan {wait_time}s...")
                time.sleep(wait_time)
            else:
                if attempt < retries - 1:
                    print(f"      ! Virhe ({e}). Yritetään uudelleen...")
                    time.sleep(5)
                else:
                    print(f"      !!! Kuva epäonnistui: {image_path}")
    return []

def main():
    if not os.path.exists(RESULTS_DIR):
        os.makedirs(RESULTS_DIR)

    start_time = time.time()
    print(f"--- Aloitetaan ajo: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    total_processed = 0

    for cat in CATEGORIES:
        cat_path = os.path.join(UPLOAD_DIR, cat)
        if not os.path.exists(cat_path):
            continue

        print(f"\nKategoria: {cat}")
        files = [f for f in os.listdir(cat_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        all_entries = []

        if not files:
            print(f"   Ei kuvia kansiossa {cat}.")
            continue

        for i, filename in enumerate(sorted(files)):
            full_path = os.path.join(cat_path, filename)
            print(f"   [{i+1}/{len(files)}] Käsitellään: {filename}")
            
            data = process_image_with_retry(full_path, cat)
            
            if data == "DAILY_QUOTA_REACHED":
                return # Lopetetaan koko ajo

            if isinstance(data, list):
                all_entries.extend(data)
                total_processed += 1
            

        # DUPLIKAATTIEN POISTO JA JÄRJESTYS
        unique_data = {}
        for entry in all_entries:
            try:
                name = entry.get('name')
                if not name: continue
                
                # Puhdistetaan arvo
                val_raw = str(entry.get('value', '0'))
                val_clean = "".join(filter(str.isdigit, val_raw))
                current_val = int(val_clean) if val_clean else 0
                
                if name not in unique_data or current_val > unique_data[name]['value']:
                    entry['value'] = current_val
                    unique_data[name] = entry
            except:
                continue

        final_list = sorted(unique_data.values(), key=lambda x: x.get('value', 0), reverse=True)

        if final_list:
            output_file = os.path.join(RESULTS_DIR, f"{cat.lower()}_results.csv")
            with open(output_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["rank", "name", "value"], delimiter=";")
                writer.writeheader()
                writer.writerows(final_list)
            print(f"   >> Tallennettu {len(final_list)} pelaajaa tiedostoon {output_file}")

    duration = time.time() - start_time
    print(f"\n--- Valmis! ---")
    print(f"Käsitelty: {total_processed} kuvaa")
    print(f"Kesto: {duration:.1f} sekuntia")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nKeskeytetty käyttäjän toimesta.")
    except Exception as e:
        print(f"\nKRIITTINEN VIRHE: {e}")
    
    input("\nPaina Enter sulkeaksesi ikkunan...")