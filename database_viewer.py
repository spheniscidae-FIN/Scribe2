import sys
import sqlite3
import os

# Google Sheets kirjastot (Asenna: pip install gspread oauth2client)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget,
    QTableWidgetItem, QPushButton, QVBoxLayout,
    QWidget, QLabel, QHBoxLayout, QMessageBox,
    QHeaderView, QLineEdit
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

# --- ASETUKSET ---
SHEET_NAME = "Squadpower"  # Google Sheets tiedoston nimi
WORKSHEET_NAME = "Database"    # Välilehden nimi
# GitHub-osoite, jonne profiilikuvat tallentuvat
GITHUB_BASE_URL = "https://spheniscidae-fin.github.io/Scribe2/DATA/Database/Profile_pictures"

class DatabaseViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scribe - Player Database")
        self.setMinimumSize(950, 650)

        # Polut
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(base_dir, "DATA", "DATABASE", "Players.db")
        # Varmista, että tämä tiedosto on samassa kansiossa kuin koodi
        self.json_key = os.path.join(base_dir, "scribe-sync-488917-4d7c6c9d0021.json")

        # Keskuswidget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # --- YLÄPANEELI ---
        self.top_panel = QHBoxLayout()

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Hae nimellä, tagilla, ID:llä tai päivämäärällä...")
        self.search_field.textChanged.connect(self.apply_filter)
        self.search_field.setStyleSheet("padding: 8px; font-size: 14px; color: white; background-color: #444;")

        # SYNCHRONOINTI-PAINIKE
        self.sync_btn = QPushButton("SYNCHRONOI SHEETS")
        self.sync_btn.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 10px; margin-left: 10px;"
        )
        self.sync_btn.clicked.connect(self.sync_to_google_sheets)

        self.clear_db_btn = QPushButton("TYHJENNÄ KANTA")
        self.clear_db_btn.setStyleSheet(
            "background-color: #c0392b; color: white; font-weight: bold; padding: 10px; margin-left: 10px;"
        )
        self.clear_db_btn.clicked.connect(self.clear_entire_db)

        self.top_panel.addWidget(self.search_field)
        self.top_panel.addWidget(self.sync_btn)
        self.top_panel.addWidget(self.clear_db_btn)
        self.layout.addLayout(self.top_panel)

        # --- TAULUKKO ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["PFP", "Name", "Tag", "ID", "Joined", "Action"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 110)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 60)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.layout.addWidget(self.table)

        self.all_rows = []
        self.load_data()

    def load_data(self):
        """Lataa pelaajat tietokannasta ja tallentaa ne muistiin."""
        self.table.setRowCount(0)
        self.all_rows = []

        if not os.path.exists(self.db_path):
            return

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
        """Täyttää taulukon annetuilla riveillä."""
        self.table.setRowCount(len(rows))
        self.table.verticalHeader().setDefaultSectionSize(110)

        for row_idx, (name, tag, p_id, joined, pfp_path) in enumerate(rows):
            pfp_label = QLabel()
            pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if pfp_path and os.path.exists(pfp_path):
                pixmap = QPixmap(pfp_path)
                scaled_pixmap = pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                pfp_label.setPixmap(scaled_pixmap)
            else:
                pfp_label.setText("No Image")

            self.table.setCellWidget(row_idx, 0, pfp_label)
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(name)))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(tag)))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(p_id)))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(joined)))

            delete_btn = QPushButton("X")
            delete_btn.setStyleSheet("background-color: #444; color: white; font-weight: bold;")
            delete_btn.clicked.connect(lambda _, pid=p_id: self.delete_player(pid))
            self.table.setCellWidget(row_idx, 5, delete_btn)

    def apply_filter(self):
        query = self.search_field.text().lower().strip()
        if not query:
            self.populate_table(self.all_rows)
            return
        filtered = [r for r in self.all_rows if query in f"{r[0]} {r[1]} {r[2]} {r[3]}".lower()]
        self.populate_table(filtered)

    def delete_player(self, player_id: str):
        reply = QMessageBox.question(self, "Vahvista poisto", f"Poistetaanko pelaaja {player_id}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(self.db_path)
            conn.cursor().execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            conn.commit()
            conn.close()
            self.load_data()

    def clear_entire_db(self):
        reply = QMessageBox.question(self, "Vahvista tyhjennys", "Haluatko varmasti tyhjentää KOKO tietokannan?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM players")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='players'")
            conn.commit()
            conn.close()
            self.load_data()

    # ---------------------------------------------------------
    # GOOGLE SHEETS SYNCHRONOINTI
    # ---------------------------------------------------------
    def sync_to_google_sheets(self):
        """Vie pelaajatietokannan Sheetsiin (A: player_id, B: Name, C: pfp-path)."""
        if not os.path.exists(self.json_key):
            QMessageBox.critical(self, "Virhe", f"service_account.json puuttuu polusta:\n{self.json_key}")
            return

        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.json_key, scope)
            client = gspread.authorize(creds)
            
            spreadsheet = client.open(SHEET_NAME)
            sheet = spreadsheet.worksheet(WORKSHEET_NAME)

            # Hae olemassa olevat ID:t Sheetsistä välttääksemme duplikaatit
            existing_ids = sheet.col_values(1)[1:] 

            new_entries = []
            for name, tag, p_id, joined, pfp_path in self.all_rows:
                if str(p_id) not in existing_ids:
                    # Muunnetaan paikallinen polku URL-muotoon
                    filename = os.path.basename(pfp_path)
                    pfp_url = f"{GITHUB_BASE_URL}/{filename}"
                    
                    # Sarakejärjestys: A: player_id, B: Name, C: pfp-path
                    new_entries.append([str(p_id), str(name), pfp_url])

            if new_entries:
                sheet.append_rows(new_entries)
                QMessageBox.information(self, "Onnistui", f"Synkronoitu {len(new_entries)} uutta pelaajaa Sheetsiin!")
            else:
                QMessageBox.information(self, "Valmis", "Sheets on jo ajan tasalla.")

        except Exception as e:
            QMessageBox.critical(self, "Virhe", f"Synkronointi epäonnistui:\n{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QMainWindow { background-color: #2b2b2b; }
        QTableWidget { background-color: #333; color: white; gridline-color: #555; border: none; }
        QHeaderView::section { background-color: #444; color: white; padding: 4px; border: 1px solid #555; }
    """)
    window = DatabaseViewer()
    window.show()
    sys.exit(app.exec())