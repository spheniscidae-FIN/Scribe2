import customtkinter as ctk
import os
import configparser
from datetime import datetime
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Varmista, että tämä polku on oikein suhteessa tähän skriptiin
config_path = os.path.join(BASE_DIR, 'DATA', 'Config', 'STUFFnSHIET.ini')

class ScribeControlPanel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Scribe System Hub")
        self.geometry("700x700")
        
        self.config_path = config_path 
        self.config = configparser.ConfigParser()
        
        # --- UI Elementit ---
        self.label = ctk.CTkLabel(self, text="Scribe Configuration & Control", font=("Roboto", 20))
        self.label.pack(pady=10)

        # --- ASETUKSET (INI-tiedosto) ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.pack(pady=10, padx=20, fill="x")

        # Read Mode
        ctk.CTkLabel(self.settings_frame, text="Read Mode:").grid(row=0, column=0, padx=10, pady=5)
        self.read_mode_var = ctk.StringVar(value="daily")
        self.read_mode_menu = ctk.CTkOptionMenu(self.settings_frame, 
                                                values=["daily", "weekly", "weekend"],
                                                variable=self.read_mode_var)
        self.read_mode_menu.grid(row=0, column=1, padx=10, pady=5)

        # Day
        ctk.CTkLabel(self.settings_frame, text="Day:").grid(row=1, column=0, padx=10, pady=5)
        self.day_var = ctk.StringVar(value="mon")
        self.day_menu = ctk.CTkOptionMenu(self.settings_frame, 
                                          values=["mon", "tues", "wed", "thur", "fri", "SVS"],
                                          variable=self.day_var)
        self.day_menu.grid(row=1, column=1, padx=10, pady=5)

        # Debug-asetukset
        self.debug_logger_var = ctk.BooleanVar(value=True)
        self.debug_logger_switch = ctk.CTkSwitch(self.settings_frame, text="Debug Logger", variable=self.debug_logger_var)
        self.debug_logger_switch.grid(row=0, column=2, padx=20)

        self.debug_run_var = ctk.BooleanVar(value=False)
        self.debug_run_switch = ctk.CTkSwitch(self.settings_frame, text="Debug Run", variable=self.debug_run_var)
        self.debug_run_switch.grid(row=1, column=2, padx=20)

        self.save_btn = ctk.CTkButton(self.settings_frame, text="Save Config", command=self.save_config)
        self.save_btn.grid(row=2, column=0, columnspan=3, pady=10)

        # --- TOIMINTONAPIT ---
        self.run_frame = ctk.CTkFrame(self)
        self.run_frame.pack(pady=10, padx=20, fill="x")
        
        # Kutsutaan nappien luontia
        self.setup_buttons()

        # Loki-ikkuna
        self.log_text = ctk.CTkTextbox(self, width=650, height=300)
        self.log_text.pack(pady=10)

        # Lataa nykyiset asetukset
        self.load_config()

    def setup_buttons(self):
        scripts = [
            ("Daily VS (Scribe)", "scribe.py"),
            ("DB Manager", "database_viewer.py"),
            ("Scoreboard", "Score_viewer.py"),
            ("Capture Tool", "capture_tool.py"),
            ("CSV Convert", "convert.py"),
            ("DB Upsert", "upsert.py")
        ]
        
        for i, (label, script) in enumerate(scripts):
            btn = ctk.CTkButton(self.run_frame, text=label, 
                                command=lambda s=script: self.run_task(s))
            btn.grid(row=i//2, column=i%2, padx=10, pady=5, sticky="ew")

    def load_config(self):
        if not os.path.exists(self.config_path):
            self.log(f"Configia ei löytynyt polusta: {self.config_path}")
            return
        try:
            self.config.read(self.config_path)
            if 'READ_MODE' in self.config:
                self.read_mode_var.set(self.config.get('READ_MODE', 'read', fallback='daily'))
                self.day_var.set(self.config.get('READ_MODE', 'day', fallback='mon'))
            if 'DEBUG' in self.config:
                self.debug_logger_var.set(self.config.getboolean('DEBUG', 'debug_logger', fallback=True))
                self.debug_run_var.set(self.config.getboolean('DEBUG', 'debug_run', fallback=False))
            self.log("Asetukset ladattu.")
        except Exception as e:
            self.log(f"Virhe ladattaessa configia: {e}")

    def save_config(self):
        if not self.config.has_section('DEBUG'): self.config.add_section('DEBUG')
        if not self.config.has_section('READ_MODE'): self.config.add_section('READ_MODE')
        
        self.config.set('DEBUG', 'debug_logger', str(self.debug_logger_var.get()))
        self.config.set('DEBUG', 'debug_run', str(self.debug_run_var.get()))
        self.config.set('READ_MODE', 'read', self.read_mode_var.get())
        self.config.set('READ_MODE', 'day', self.day_var.get())
        
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
        self.log("Config tallennettu.")

    def log(self, message):
        self.log_text.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see("end")

    def run_task(self, script_name):
        thread = threading.Thread(target=self._execute_script, args=(script_name,), daemon=True)
        thread.start()

    def _execute_script(self, script_name):
        script_full_path = os.path.join(BASE_DIR, script_name)
        self.log(f"--- Käynnistetään: {script_name} ---")
        
        try:
            process = subprocess.Popen(
                ["python", script_full_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            for line in process.stdout:
                # Käytetään lambdaa, jotta UI-päivitys menee pääsäikeeseen (turvallisempi)
                self.after(0, lambda l=line: self.log(f"> {l.strip()}"))
            
            process.stdout.close()
            return_code = process.wait()
            self.after(0, lambda: self.log(f"--- {script_name} valmis (Koodi: {return_code}) ---"))
                
        except Exception as e:
            self.after(0, lambda: self.log(f"VIRHE: {str(e)}"))

# --- TÄMÄ OSA PUUTTUI JA KÄYNNISTÄÄ OHJELMAN ---
if __name__ == "__main__":
    app = ScribeControlPanel()
    app.mainloop()