import sys
import sqlite3
import os
import psycopg2
import datetime
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget,
    QTableWidgetItem, QPushButton, QVBoxLayout,
    QWidget, QLabel, QHBoxLayout, QMessageBox,
    QHeaderView, QLineEdit, QDialog, QFormLayout
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

# --- KONFIGURAATION LATAUS ---
def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "DB_CONFIG.json")
    
    if not os.path.exists(config_path):
        print("VIRHE: DB_CONFIG.json ei löydy! Käytetään oletusarvoja.")
        return {
            "dbname": "rok_stats", "user": "upsert_user", 
            "password": "", "host": "localhost", "port": "5432",
            "sheet_name": "Squadpower", "worksheet_name": "Database",
            "github_base_url": ""
        }
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

# Erillinen sanakirja psycopg2:lle (sisältää vain yhteystiedot)
DB_PARAMS = {k: CONFIG[k] for k in ["dbname", "user", "password", "host", "port"]}

# --- DIALOGI: PELAAJAN LISÄÄMINEN KÄSIN ---
class AddPlayerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lisää pelaaja käsin")
        self.setFixedWidth(350)
        self.layout = QVBoxLayout(self)
        self.form = QFormLayout()

        self.name_input = QLineEdit()
        self.tag_input = QLineEdit()
        self.id_input = QLineEdit()
        
        self.form.addRow("Nimi:", self.name_input)
        self.form.addRow("Tag (esim. [ABC]):", self.tag_input)
        self.form.addRow("Player ID:", self.id_input)

        self.layout.addLayout(self.form)

        self.save_btn = QPushButton("TALLENNA")
        self.save_btn.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; padding: 10px;")
        self.save_btn.clicked.connect(self.accept)
        self.layout.addWidget(self.save_btn)

    def get_data(self):
        return {
            "name": self.name_input.text().strip(),
            "tag": self.tag_input.text().strip(),
            "id": self.id_input.text().strip()
        }

# --- DIALOGI: LEGACY-PELAAJIEN LISTAAMINEN ---
class LegacyListDialog(QDialog):
    def __init__(self, players_to_remove, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Poistettavat Legacy-pelaajat")
        self.setMinimumSize(450, 500)
        layout = QVBoxLayout(self)

        info_label = QLabel(f"<b>Löytyi {len(players_to_remove)} legacy-pelaajaa</b>, jotka ovat vielä paikallisessa kannassa:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.list_widget = QTableWidget()
        self.list_widget.setColumnCount(2)
        self.list_widget.setHorizontalHeaderLabels(["Nimi", "Player ID"])
        self.list_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.list_widget.setRowCount(len(players_to_remove))
        self.list_widget.setStyleSheet("background-color: #333; color: white;")

        for i, (name, pid) in enumerate(players_to_remove):
            self.list_widget.setItem(i, 0, QTableWidgetItem(name))
            self.list_widget.setItem(i, 1, QTableWidgetItem(pid))

        layout.addWidget(self.list_widget)

        warn_label = QLabel("Haluatko poistaa nämä kaikki?")
        warn_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        layout.addWidget(warn_label)

        self.btn_layout = QHBoxLayout()
        self.confirm_btn = QPushButton("POISTA KAIKKI")
        self.confirm_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 10px;")
        self.confirm_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("PERUUTA")
        self.cancel_btn.setStyleSheet("padding: 10px;")
        self.cancel_btn.clicked.connect(self.reject)
        
        self.btn_layout.addWidget(self.confirm_btn)
        self.btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(self.btn_layout)

# --- PÄÄIKKUNA ---
class DatabaseViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scribe - Player Database")
        self.setMinimumSize(1100, 700)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(base_dir, "DATA", "DATABASE", "Players.db")
        self.json_key = os.path.join(base_dir, "scribe-sync-488917-4d7c6c9d0021.json")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # --- YLÄPANEELI ---
        self.top_panel = QHBoxLayout()

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Hae nimellä, tagilla, ID:llä...")
        self.search_field.textChanged.connect(self.apply_filter)
        self.search_field.setStyleSheet("padding: 8px; font-size: 14px; color: white; background-color: #444;")

        self.add_btn = QPushButton("LISÄÄ PELAAJA")
        self.add_btn.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; padding: 10px; margin-left: 5px;")
        self.add_btn.clicked.connect(self.add_player_manual)

        self.legacy_btn = QPushButton("SIIVOA LEGACY")
        self.legacy_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 10px; margin-left: 5px;")
        self.legacy_btn.clicked.connect(self.cleanup_legacy)

        self.sync_btn = QPushButton("SYNCHRONOI SHEETS")
        self.sync_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 10px; margin-left: 5px;")
        self.sync_btn.clicked.connect(self.sync_to_google_sheets)

        self.clear_db_btn = QPushButton("TYHJENNÄ KANTA")
        self.clear_db_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 10px; margin-left: 5px;")
        self.clear_db_btn.clicked.connect(self.clear_entire_db)

        self.top_panel.addWidget(self.search_field)
        self.top_panel.addWidget(self.add_btn)
        self.top_panel.addWidget(self.legacy_btn)
        self.top_panel.addWidget(self.sync_btn)
        self.top_panel.addWidget(self.clear_db_btn)
        self.layout.addLayout(self.top_panel)

        # --- TAULUKKO ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["PFP", "Name", "Tag", "ID", "Joined", "Action"])
        
        header = self.table.horizontalHeader()
        self.table.setColumnWidth(0, 110)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 60)

        self.layout.addWidget(self.table)
        self.all_rows = []
        self.load_data()

    def add_player_manual(self):
        dialog = AddPlayerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"] or not data["id"]:
                QMessageBox.warning(self, "Virhe", "Nimi ja ID ovat pakollisia kenttiä.")
                return
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM players WHERE player_id = ?", (data["id"],))
                if cursor.fetchone():
                    QMessageBox.warning(self, "Virhe", f"ID {data['id']} on jo käytössä.")
                    conn.close()
                    return
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                cursor.execute(
                    "INSERT INTO players (name, tag, player_id, join_date, pfp_path) VALUES (?, ?, ?, ?, ?)",
                    (data["name"], data["tag"], data["id"], now, "")
                )
                conn.commit()
                conn.close()
                self.load_data()
                QMessageBox.information(self, "Onnistui", f"Pelaaja {data['name']} lisätty.")
            except Exception as e:
                QMessageBox.critical(self, "Virhe", f"Lisäys epäonnistui:\n{str(e)}")

    def cleanup_legacy(self):
        try:
            # Käyttää ladattua DB_PARAMS -konfiguraatiota
            pg_conn = psycopg2.connect(**DB_PARAMS)
            pg_cur = pg_conn.cursor()
            pg_cur.execute("SELECT player_id FROM legacy_players")
            legacy_ids = [str(row[0]) for row in pg_cur.fetchall()]
            pg_cur.close()
            pg_conn.close()

            if not legacy_ids:
                QMessageBox.information(self, "Siivous", "Legacy-kannassa ei ole poistettavia pelaajia.")
                return

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            placeholders = ', '.join(['?'] * len(legacy_ids))
            query = f"SELECT name, player_id FROM players WHERE player_id IN ({placeholders})"
            cursor.execute(query, legacy_ids)
            players_to_remove = cursor.fetchall()
            conn.close()

            if not players_to_remove:
                QMessageBox.information(self, "Siivous", "Paikallisessa kannassa ei ole legacy-pelaajia.")
                return

            dialog = LegacyListDialog(players_to_remove, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.executemany("DELETE FROM players WHERE player_id = ?", [(pid,) for _, pid in players_to_remove])
                removed = cursor.rowcount
                conn.commit()
                conn.close()
                self.load_data()
                QMessageBox.information(self, "Onnistui", f"Siivous valmis. Poistettu {removed} pelaajaa.")

        except Exception as e:
            QMessageBox.critical(self, "Virhe", f"Legacy-siivous epäonnistui:\n{str(e)}")

    def load_data(self):
        self.table.setRowCount(0)
        self.all_rows = []
        if not os.path.exists(self.db_path): return
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name, tag, player_id, join_date, pfp_path FROM players")
            self.all_rows = cursor.fetchall()
            conn.close()
            self.populate_table(self.all_rows)
        except sqlite3.Error as e:
            print(f"Tietokantavirhe: {e}")

    def populate_table(self, rows):
        self.table.setRowCount(len(rows))
        self.table.verticalHeader().setDefaultSectionSize(110)
        for row_idx, (name, tag, p_id, joined, pfp_path) in enumerate(rows):
            pfp_label = QLabel()
            pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if pfp_path and os.path.exists(pfp_path):
                pixmap = QPixmap(pfp_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                pfp_label.setPixmap(pixmap)
            else:
                pfp_label.setText("No Image")
            
            self.table.setCellWidget(row_idx, 0, pfp_label)
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(name)))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(tag)))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(p_id)))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(joined)))
            
            del_btn = QPushButton("X")
            del_btn.setStyleSheet("background-color: #444; color: white;")
            del_btn.clicked.connect(lambda _, pid=p_id: self.delete_player(pid))
            self.table.setCellWidget(row_idx, 5, del_btn)

    def apply_filter(self):
        query = self.search_field.text().lower().strip()
        if not query:
            self.populate_table(self.all_rows)
            return
        filtered = [r for r in self.all_rows if query in f"{r[0]} {r[1]} {r[2]}".lower()]
        self.populate_table(filtered)

    def delete_player(self, player_id):
        reply = QMessageBox.question(self, "Vahvista", f"Poistetaanko {player_id}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(self.db_path)
            conn.cursor().execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            conn.commit()
            conn.close()
            self.load_data()

    def clear_entire_db(self):
        reply = QMessageBox.question(self, "Vahvista", "Tyhjennetäänkö KOKO kanta?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(self.db_path)
            conn.cursor().execute("DELETE FROM players")
            conn.commit()
            conn.close()
            self.load_data()

    def sync_to_google_sheets(self):
        if not os.path.exists(self.json_key):
            QMessageBox.critical(self, "Virhe", "JSON-avain puuttuu.")
            return
        try:
            sheet_data = [["player_id", "Name", "pfp-path"]]
            for name, tag, p_id, joined, pfp_path in self.all_rows:
                filename = os.path.basename(pfp_path) if pfp_path else "default.png"
                pfp_url = f"{CONFIG['github_base_url']}/{filename}"
                sheet_data.append([str(p_id), str(name), pfp_url])

            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.json_key, scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open(CONFIG['sheet_name'])
            sheet = spreadsheet.worksheet(CONFIG['worksheet_name'])
            sheet.clear()
            sheet.update(sheet_data, 'A1')

            QMessageBox.information(self, "Onnistui", f"Sheets päivitetty! ({len(self.all_rows)} pelaajaa)")
        except Exception as e:
            QMessageBox.critical(self, "Virhe", f"Synkronointi epäonnistui:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow { background-color: #2b2b2b; } 
        QTableWidget { background-color: #333; color: white; border: none; }
        QLabel { color: white; }
        QLineEdit { color: white; background-color: #444; border: 1px solid #555; }
        QDialog { background-color: #2b2b2b; }
        QFormLayout QLabel { color: white; }
    """)
    window = DatabaseViewer()
    window.show()
    sys.exit(app.exec())