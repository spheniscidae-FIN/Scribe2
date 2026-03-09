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
        return {
            "dbname": "rok_stats", "user": "upsert_user", 
            "password": "", "host": "localhost", "port": "5432",
            "sheet_name": "Squadpower", "worksheet_name": "Database",
            "github_base_url": "", "sqlite_path": "Players.db",
            "json_key_path": "key.json"
        }
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()
DB_PARAMS = {k: CONFIG[k] for k in ["dbname", "user", "password", "host", "port"]}

# --- UUSI DIALOGI: POISTON VAHVISTUS ---
class DeleteConfirmationDialog(QDialog):
    def __init__(self, player_id, player_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vahvista poisto")
        self.setFixedWidth(400)
        layout = QVBoxLayout(self)

        header = QLabel(f"⚠️ Olet poistamassa pelaajaa:")
        header.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 16px;")
        layout.addWidget(header)

        info = QLabel(f"<b>Nimi:</b> {player_name}<br><b>ID:</b> {player_id}")
        info.setStyleSheet("background-color: #333; padding: 10px; border-radius: 5px;")
        layout.addWidget(info)

        warning_text = QLabel(
            "Tämä toiminto poistaa pelaajan:<br>"
            "1. Paikallisesta <b>SQLite</b>-tietokannasta<br>"
            "2. PostgreSQL-palvelimen <b>active_players</b>-taulusta<br>"
            "3. PostgreSQL-palvelimen <b>player_snapshots</b>-historiasta"
        )
        warning_text.setWordWrap(True)
        layout.addWidget(warning_text)

        btn_layout = QHBoxLayout()
        self.confirm_btn = QPushButton("POISTA KAIKKI TIEDOT")
        self.confirm_btn.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 10px;")
        self.confirm_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("PERUUTA")
        self.cancel_btn.setStyleSheet("padding: 10px;")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.confirm_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

# --- MUUT DIALOGIT (AddPlayerDialog, LegacyListDialog) ---
# (Pidetään samana kuin aiemmin...)
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
        return {"name": self.name_input.text().strip(), "tag": self.tag_input.text().strip(), "id": self.id_input.text().strip()}

class LegacyListDialog(QDialog):
    def __init__(self, players_to_remove, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Poistettavat Legacy-pelaajat")
        self.setMinimumSize(450, 500)
        layout = QVBoxLayout(self)
        self.list_widget = QTableWidget()
        self.list_widget.setColumnCount(2)
        self.list_widget.setHorizontalHeaderLabels(["Nimi", "Player ID"])
        self.list_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.list_widget.setRowCount(len(players_to_remove))
        for i, (name, pid) in enumerate(players_to_remove):
            self.list_widget.setItem(i, 0, QTableWidgetItem(name))
            self.list_widget.setItem(i, 1, QTableWidgetItem(pid))
        layout.addWidget(self.list_widget)
        self.confirm_btn = QPushButton("POISTA KAIKKI")
        self.confirm_btn.setStyleSheet("background-color: #c0392b; color: white; padding: 10px;")
        self.confirm_btn.clicked.connect(self.accept)
        layout.addWidget(self.confirm_btn)

# --- PÄÄIKKUNA ---
class DatabaseViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scribe - Player Database")
        self.setMinimumSize(1100, 700)

        # Polut JSONista
        self.db_path = CONFIG['sqlite_path']
        self.json_key = CONFIG['json_key_path']

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
        self.add_btn.setStyleSheet("background-color: #2980b9; color: white; padding: 10px;")
        self.add_btn.clicked.connect(self.add_player_manual)

        self.legacy_btn = QPushButton("SIIVOA LEGACY")
        self.legacy_btn.setStyleSheet("background-color: #f39c12; color: white; padding: 10px;")
        self.legacy_btn.clicked.connect(self.cleanup_legacy)

        self.sync_btn = QPushButton("SYNCHRONOI SHEETS")
        self.sync_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 10px;")
        self.sync_btn.clicked.connect(self.sync_to_google_sheets)

        self.top_panel.addWidget(self.search_field)
        self.top_panel.addWidget(self.add_btn)
        self.top_panel.addWidget(self.legacy_btn)
        self.top_panel.addWidget(self.sync_btn)
        self.layout.addLayout(self.top_panel)

        # --- TAULUKKO ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["PFP", "Name", "Tag", "ID", "Joined", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(5, 60)
        self.layout.addWidget(self.table)

        self.all_rows = []
        self.load_data()

    def load_data(self):
        self.table.setRowCount(0)
        if not os.path.exists(self.db_path): return
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name, tag, player_id, join_date, pfp_path FROM players")
            self.all_rows = cursor.fetchall()
            conn.close()
            self.populate_table(self.all_rows)
        except Exception as e:
            print(f"Latausvirhe: {e}")

    def populate_table(self, rows):
        self.table.setRowCount(len(rows))
        self.table.verticalHeader().setDefaultSectionSize(110)
        for i, (name, tag, p_id, joined, pfp_path) in enumerate(rows):
            pfp_label = QLabel()
            pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if pfp_path and os.path.exists(pfp_path):
                pfp_label.setPixmap(QPixmap(pfp_path).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio))
            else:
                pfp_label.setText("No Image")
            
            self.table.setCellWidget(i, 0, pfp_label)
            self.table.setItem(i, 1, QTableWidgetItem(str(name)))
            self.table.setItem(i, 2, QTableWidgetItem(str(tag)))
            self.table.setItem(i, 3, QTableWidgetItem(str(p_id)))
            self.table.setItem(i, 4, QTableWidgetItem(str(joined)))
            
            del_btn = QPushButton("X")
            del_btn.setStyleSheet("background-color: #444; color: white;")
            # Napataan sekä ID että Nimi dialogia varten
            del_btn.clicked.connect(lambda _, pid=p_id, n=name: self.confirm_delete(pid, n))
            self.table.setCellWidget(i, 5, del_btn)

    def confirm_delete(self, player_id, player_name):
        dialog = DeleteConfirmationDialog(player_id, player_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.execute_full_delete(player_id)

    def execute_full_delete(self, player_id):
        try:
            # 1. Poisto SQLite
            conn = sqlite3.connect(self.db_path)
            conn.cursor().execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            conn.commit()
            conn.close()

            # 2. Poisto PostgreSQL
            pg_conn = psycopg2.connect(**DB_PARAMS)
            pg_cur = pg_conn.cursor()
            # Poistetaan sekä aktiivisista että snapshot-historiasta
            pg_cur.execute("DELETE FROM player_snapshots WHERE player_id = %s", (player_id,))
            pg_cur.execute("DELETE FROM active_players WHERE player_id = %s", (player_id,))
            pg_conn.commit()
            pg_cur.close()
            pg_conn.close()

            self.load_data()
            QMessageBox.information(self, "Poistettu", f"Pelaaja {player_id} poistettu kaikista kannoista.")
        except Exception as e:
            QMessageBox.critical(self, "Virhe", f"Poisto epäonnistui:\n{str(e)}")

    def apply_filter(self):
        query = self.search_field.text().lower().strip()
        filtered = [r for r in self.all_rows if query in f"{r[0]} {r[1]} {r[2]}".lower()]
        self.populate_table(filtered)

    # (Loput metodit: add_player_manual, cleanup_legacy, sync_to_google_sheets pysyvät ennallaan)
    def add_player_manual(self):
        dialog = AddPlayerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data["name"] or not data["id"]: return
            conn = sqlite3.connect(self.db_path); cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            cursor.execute("INSERT INTO players (name, tag, player_id, join_date, pfp_path) VALUES (?, ?, ?, ?, ?)",
                           (data["name"], data["tag"], data["id"], now, ""))
            conn.commit(); conn.close(); self.load_data()

    def cleanup_legacy(self):
        try:
            pg_conn = psycopg2.connect(**DB_PARAMS); pg_cur = pg_conn.cursor()
            pg_cur.execute("SELECT player_id FROM legacy_players")
            legacy_ids = [str(row[0]) for row in pg_cur.fetchall()]
            pg_conn.close()
            if not legacy_ids: return
            conn = sqlite3.connect(self.db_path); cursor = conn.cursor()
            placeholders = ', '.join(['?'] * len(legacy_ids))
            cursor.execute(f"SELECT name, player_id FROM players WHERE player_id IN ({placeholders})", legacy_ids)
            to_rem = cursor.fetchall(); conn.close()
            if not to_rem: return
            if LegacyListDialog(to_rem, self).exec() == QDialog.DialogCode.Accepted:
                conn = sqlite3.connect(self.db_path); cursor = conn.cursor()
                cursor.executemany("DELETE FROM players WHERE player_id = ?", [(p[1],) for p in to_rem])
                conn.commit(); conn.close(); self.load_data()
        except Exception as e: QMessageBox.critical(self, "Virhe", str(e))

    def sync_to_google_sheets(self):
        try:
            sheet_data = [["player_id", "Name", "pfp-path"]]
            for name, tag, p_id, joined, pfp_path in self.all_rows:
                pfp_url = f"{CONFIG['github_base_url']}/{os.path.basename(pfp_path)}" if pfp_path else ""
                sheet_data.append([str(p_id), str(name), pfp_url])
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.json_key, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
            client = gspread.authorize(creds)
            sheet = client.open(CONFIG['sheet_name']).worksheet(CONFIG['worksheet_name'])
            sheet.clear(); sheet.update(sheet_data, 'A1')
            QMessageBox.information(self, "Ok", "Sheets päivitetty!")
        except Exception as e: QMessageBox.critical(self, "Virhe", str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("QMainWindow { background-color: #2b2b2b; } QTableWidget { background-color: #333; color: white; } QLabel { color: white; } QLineEdit { background-color: #444; color: white; }")
    window = DatabaseViewer()
    window.show()
    sys.exit(app.exec())