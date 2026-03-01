import os
import numpy as np
import configparser
from ctypes import wintypes as wt
import csv
import sqlite3
import random
from datetime import datetime, timedelta


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, 'DATA', 'Config', 'STUFFnSHIET.ini')
DEBUG_LOG_PATH = os.path.join(BASE_DIR, 'DATA' ,'Logs', 'debug_log.txt')
RESULTS_LOG_PATH = os.path.join(BASE_DIR, 'DATA' ,'Logs', 'results.txt')
DB_PATH = os.path.join(BASE_DIR, 'DATA' ,'DATABASE', 'Players.db')

config = configparser.ConfigParser()
config.optionxform = str
config.read(config_path)

DEBUG = config.getboolean('DEBUG', 'debug_logger', fallback=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            tag TEXT,
            player_id TEXT,
            join_date TEXT,
            pfp_path TEXT  -- Tallennetaan se capture_pfp:n palauttama polku tähän
        )
    """)
    conn.commit()
    conn.close()

def player_exists_check(tag):
    """
    Tarkistaa löytyykö annettu tag jo tietokannasta.
    Palauttaa player_id:n (str) jos löytyy, muuten None.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Haetaan suoraan player_id tagin perusteella
        cursor.execute("SELECT player_id FROM players WHERE tag = ? LIMIT 1", (tag,))
        result = cursor.fetchone()
        
        conn.close()

        # Jos tulos löytyi, result on tuple (player_id,), palautetaan merkkijono
        if result:
            return result[0]
        return None

    except sqlite3.Error as e:
        out(f"Tietokantavirhe tarkistuksessa: {e}")
        return None



def add_player_to_db(tag, name, joindate, playerID, profilepicture):
    conn = sqlite3.connect(DB_PATH) # Käytä tätä muuttujaa, jonka määrittelit alussa!
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO players (tag, name, join_date, player_id, pfp_path)
        VALUES (?, ?, ?, ?, ?)
    """, (tag, name, joindate, playerID, profilepicture))

    conn.commit()
    conn.close()
    return True


def format_time_centis(now: datetime) -> str:
    centis = int(round(now.microsecond / 1e6 * 100))
    hour, minute, sec = now.hour, now.minute, now.second
    if centis >= 100:
        centis = 0
        sec += 1
        if sec >= 60:
            sec = 0
            minute += 1
            if minute >= 60:
                minute = 0
                hour = (hour + 1) % 24
    return f"{hour:02d}:{minute:02d}:{sec:02d}.{centis:02d}"

def out(message: str = "", data=None, log: str = DEBUG_LOG_PATH):
    if not DEBUG:
        return
        
    now = datetime.now()
    timestamp = format_time_centis(now)
    
    # Rakennetaan viesti: "AIKA : VIESTI -> DATA" (jos dataa on)
    line = f"[{timestamp}] : {message}"
    if data is not None:
        line += f" -> {data}"

    # Tulostus konsoliin
    print(line)

    # Kirjoitus lokiin (täsmälleen sama rivi)
    with open(log, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def tallenna_tulokset(ndx, score, player, cycle, player_id):
    # 'a' tarkoittaa append-tilaa
    # tästäkin tuotetaan joka päivälle oma tiedostonsa jotta tarkistus on helppoa
    # kaipaa vielä validointia, eli lista on luettava siten läpi että edellinen luku on sama tai pienempi,
    # kuin tarkasteltava mutta pienempi tai yhtäsuuri kuin seuraava.
    log = RESULTS_LOG_PATH
    now = datetime.now()
    timestamp = format_time_centis(now)

    # Rakennetaan viesti: "AIKA : VIESTI -> DATA" (jos dataa on)
    line = f"{ndx:03d} |-->{score} - {player} - Onnistunut lukukierros: {cycle} | pelaaja ID {player_id}\n"

    # Kirjoitus lokiin (täsmälleen sama rivi)
    with open(log, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def tallenna_lopulliset_tulokset(tuloslista, day="MON"):
    # Haetaan viikkonumero ja luodaan tiedostonimi
    vk_nbr = datetime.now().isocalendar().week
    lukumäärä = len(tuloslista)
    filename = f"{vk_nbr}_{day}.csv"
    
    # Jos haluat käyttää aiemmin määriteltyä RESULTS-polkua:
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'RESULTS')
    os.makedirs(results_dir, exist_ok=True)
    full_path = os.path.join(results_dir, filename)
    
    # Käytetään "w" (write), joka ylikirjoittaa tiedoston jos se on jo olemassa
    with open(full_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        
        # Kirjoitetaan otsikot (tämä ajetaan nyt aina, koska tiedosto on uusi)
        writer.writerow(["Index", "Playername", "Score", "player_id"])

        # Kirjoitetaan data
        for i, data in enumerate(tuloslista, start=1):
            # Lasketaan oikea indeksi: (lukumäärä + 1) - juokseva numero
            oikea_indeksi = (lukumäärä + 1) - i
            writer.writerow([oikea_indeksi, data["pelaaja"], data["pisteet"], data["player_id"]])
            
    print(f">>> Tulokset tallennettu: {full_path}")
    print(f">>> Rivimäärä: {lukumäärä}")

