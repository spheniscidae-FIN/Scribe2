import sys
import os
import csv
import sqlite3
import difflib  # Lisätty difflib import tähän alkuun selkeyden vuoksi
from collections import defaultdict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QLabel,
    QMessageBox
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

# --- POIKKEUSTAPAUSLISTA (ALIAS-VERTAILU) ---
# Tänne lisätään parit: 'ocr_tunnistus': 'oikea_nimi_tietokannassa'
NAME_ALIASES = {
    'tapi': 'ᴛᴀᴘɪ',
    'tap1': 'ᴛᴀᴘɪ',
    'chick': 'chicken',
    # Voit täyttää tätä tarpeen mukaan
}

# ---------------- NUMERIIKKAA TUKEVA ITEM ----------------

class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            val_self = int(self.text().replace(" ", "").replace(".", ""))
            val_other = int(other.text().replace(" ", "").replace(".", ""))
            return val_self < val_other
        except ValueError:
            return super().__lt__(other)

# ---------------- PÄÄOHJELMA ----------------

class ResultsEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scribe – Results Editor (AI Enhanced)")
        self.setMinimumSize(1250, 800)

        self.font_size = 12
        base = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base
        self.results_path = os.path.join(base, "results")
        self.players_db_path = os.path.join(base, "DATA", "DATABASE", "Players.db")

        self.patterns = {
            "MA": "_mon.csv", "TI": "_tues.csv", "KE": "_wed.csv",
            "TO": "_thur.csv", "PE": "_fri.csv", "LA": "_sat.csv",
            "VKO": "_wk.csv",
            "POWER": "power_results.csv",
            "DONATIONS": "donations_results.csv",
            "KILLS": "kills_results.csv"
        }

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.refresh_btn = QPushButton("Update all")
        self.refresh_btn.clicked.connect(self.load_all_csv)
        self.generate_la_btn = QPushButton("Generate Saturday")
        self.generate_la_btn.clicked.connect(self.generate_la_scores)
        self.generate_vko_btn = QPushButton("Generate Week")
        self.generate_vko_btn.clicked.connect(self.generate_weekly_summary)
        self.save_csv_btn = QPushButton("Save active tab as CSV")
        self.save_csv_btn.clicked.connect(self.save_active_csv)
        self.validate_btn = QPushButton("Validate Data")
        self.validate_btn.clicked.connect(self.validate_active_table)

        top.addWidget(self.refresh_btn)
        top.addWidget(self.generate_la_btn)
        top.addWidget(self.generate_vko_btn)
        top.addWidget(self.save_csv_btn)
        top.addWidget(self.validate_btn)
        top.addStretch()
        layout.addLayout(top)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tables = {}
        all_tab_names = ["MA", "TI", "KE", "TO", "PE", "LA", "VKO", "POWER", "DONATIONS", "KILLS"]
        
        for tab_name in all_tab_names:
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["PFP", "Rank", "Playername", "Value", "player_id"])
            table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
            table.setSortingEnabled(True)
            
            is_ai = tab_name in ["POWER", "DONATIONS", "KILLS"]
            table.verticalHeader().setDefaultSectionSize(45 if is_ai else 90)

            header = table.horizontalHeader()
            header.setSectionResizeMode(0, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, header.ResizeMode.Stretch)
            header.setSectionResizeMode(3, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, header.ResizeMode.ResizeToContents)

            table.itemChanged.connect(self.on_item_changed)
            self.tables[tab_name] = table

            tab_widget = QWidget()
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.addWidget(table)
            self.tabs.addTab(tab_widget, tab_name)

        self.load_all_csv()
        self.update_table_fonts()

    # ---------------- APUFUNKTIOT ----------------

    def get_all_names_from_db(self):
        if not os.path.exists(self.players_db_path): return {}
        try:
            conn = sqlite3.connect(self.players_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name, player_id FROM players")
            data = {row[0]: str(row[1]) for row in cursor.fetchall() if row[0]}
            conn.close()
            return data
        except: return {}

    def find_pid_by_name(self, name: str):
        """Hakee player_id:n hyödyntäen aliaksia, tarkkaa hakua ja fuzzy matchia."""
        if not name: return None
        raw_name = name.strip()
        search_name = raw_name.lower()
        
        # 1. TARKISTETAAN ALIAS-LISTA (Poikkeustapaukset)
        if search_name in NAME_ALIASES:
            raw_name = NAME_ALIASES[search_name] # Vaihdetaan etsittävä nimi viralliseen muotoon
            print(f"Alias Match: '{name}' -> '{raw_name}'")

        # 2. Yritetään tarkkaa hakua tietokannasta (NOCASE huomioi t-kirjaimet jne)
        if os.path.exists(self.players_db_path):
            try:
                conn = sqlite3.connect(self.players_db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT player_id FROM players WHERE name = ? COLLATE NOCASE", (raw_name,))
                result = cursor.fetchone()
                conn.close()
                if result: return str(result[0])
            except: pass

        # 3. Fuzzy Match (viimeinen oljenkorsi)
        db_players = self.get_all_names_from_db() # { "Nimi": "ID" }
        if not db_players: return None
        
        all_db_names = list(db_players.keys())
        matches = difflib.get_close_matches(raw_name, all_db_names, n=1, cutoff=0.6)
        
        if matches:
            best_match = matches[0]
            print(f"Fuzzy Match: '{name}' -> '{best_match}'")
            return db_players[best_match]
            
        return None

    def get_pfp_path(self, player_id: str):
        if not player_id: return None
        folder = os.path.join(self.base_dir, "DATA", "DATABASE", "Profile_pictures")
        path = os.path.join(folder, f"{player_id}_pfp.png")
        return path if os.path.exists(path) else None

    def get_current_week_prefix(self):
        if not os.path.isdir(self.results_path): return ""
        for fname in os.listdir(self.results_path):
            if "_" in fname and fname.split("_")[0].isdigit():
                return fname.split("_")[0] + "_"
        return ""

    def update_table_fonts(self):
        font = self.font()
        font.setPointSize(self.font_size)
        self.setFont(font)
        for table in self.tables.values():
            table.setFont(font)
            table.resizeRowsToContents()

    def on_item_changed(self, item):
        if not item or item.column() not in (1, 3): return
        table = item.tableWidget()
        table.blockSignals(True)
        if not isinstance(item, NumericItem):
            table.setItem(item.row(), item.column(), NumericItem(item.text()))
        table.blockSignals(False)

    # ---------------- CSV-LATAUS ----------------

    def find_csv(self, pattern: str):
        if not os.path.isdir(self.results_path): return None
        if "_results.csv" in pattern:
            p = os.path.join(self.results_path, pattern)
            return p if os.path.exists(p) else None
        for fname in os.listdir(self.results_path):
            if fname.lower().endswith(pattern.lower()):
                return os.path.join(self.results_path, fname)
        return None

    def load_all_csv(self):
        for tab, pattern in self.patterns.items():
            path = self.find_csv(pattern)
            if path: self.load_csv_to_table(path, self.tables[tab])
            else: self.tables[tab].setRowCount(0)

    def load_csv_to_table(self, path: str, table: QTableWidget):
        table.setRowCount(0)
        table.blockSignals(True)
        tab_name = next(k for k, v in self.tables.items() if v == table)
        is_ai = tab_name in ["POWER", "DONATIONS", "KILLS"]

        try:
            try:
                with open(path, "r", encoding="utf-8-sig") as f: content = f.read()
            except:
                with open(path, "r", encoding="cp1252") as f: content = f.read()
            
            reader = csv.reader(content.splitlines(), delimiter=';')
            next(reader, None)

            for row in reader:
                if not row: continue
                row_idx = table.rowCount()
                table.insertRow(row_idx)
                pid = None

                if is_ai:
                    rank, name, value = row[0], row[1], row[2]
                    pid = row[3] if len(row) > 3 and row[3].strip() else self.find_pid_by_name(name)
                    table.setItem(row_idx, 1, NumericItem(rank))
                    table.setItem(row_idx, 2, QTableWidgetItem(name))
                    table.setItem(row_idx, 3, NumericItem(value))
                    table.setItem(row_idx, 4, QTableWidgetItem(pid if pid else ""))
                else:
                    if len(row) < 4: continue
                    idx, name, score, pid = row
                    table.setItem(row_idx, 1, NumericItem(idx))
                    table.setItem(row_idx, 2, QTableWidgetItem(name))
                    table.setItem(row_idx, 3, NumericItem(score))
                    table.setItem(row_idx, 4, QTableWidgetItem(pid))

                pfp_label = QLabel()
                pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                p_path = self.get_pfp_path(pid)
                if p_path:
                    size = 40 if is_ai else 75
                    pix = QPixmap(p_path).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    pfp_label.setPixmap(pix)
                table.setCellWidget(row_idx, 0, pfp_label)

        except Exception as e: print(f"Error {path}: {e}")
        finally:
            table.blockSignals(False)
            table.resizeRowsToContents()

    def save_active_csv(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        pattern = self.patterns.get(tab_name)
        path = self.find_csv(pattern)
        if not path:
            prefix = self.get_current_week_prefix() or "1_"
            fname = pattern if "_results" in pattern else f"{prefix}{pattern.lstrip('_')}"
            path = os.path.join(self.results_path, fname)

        table = self.tables[tab_name]
        is_ai = tab_name in ["POWER", "DONATIONS", "KILLS"]

        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter=';')
                if is_ai: writer.writerow(["rank", "name", "value", "player_id"])
                else: writer.writerow(["Index", "Playername", "Score", "player_id"])
                for r in range(table.rowCount()):
                    row_data = [
                        table.item(r, 1).text() if table.item(r, 1) else "",
                        table.item(r, 2).text() if table.item(r, 2) else "",
                        table.item(r, 3).text() if table.item(r, 3) else "",
                        table.item(r, 4).text() if table.item(r, 4) else ""
                    ]
                    writer.writerow(row_data)
            QMessageBox.information(self, "Success", f"Saved to:\n{os.path.basename(path)}")
        except Exception as e: QMessageBox.critical(self, "Error", str(e))

    def generate_la_scores(self):
        weekday_scores = defaultdict(int)
        for day in ["MA", "TI", "KE", "TO", "PE"]:
            table = self.tables[day]
            for row in range(table.rowCount()):
                try: weekday_scores[table.item(row, 2).text().strip()] += int(table.item(row, 3).text())
                except: pass

        vko_t = self.tables["VKO"]
        la_t = self.tables["LA"]
        la_t.setRowCount(0)
        la_t.blockSignals(True)

        for row in range(vko_t.rowCount()):
            name = vko_t.item(row, 2).text()
            total = int(vko_t.item(row, 3).text())
            pid = vko_t.item(row, 4).text()
            la_score = total - weekday_scores.get(name, 0)
            idx = la_t.rowCount()
            la_t.insertRow(idx)
            la_t.setItem(idx, 1, NumericItem(str(idx + 1)))
            la_t.setItem(idx, 2, QTableWidgetItem(name))
            la_t.setItem(idx, 3, NumericItem(str(la_score)))
            la_t.setItem(idx, 4, QTableWidgetItem(pid))
            pfp_l = QLabel()
            pfp_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            p_path = self.get_pfp_path(pid)
            if p_path: pfp_l.setPixmap(QPixmap(p_path).scaled(75, 75, Qt.AspectRatioMode.KeepAspectRatio))
            la_t.setCellWidget(idx, 0, pfp_l)
            
        la_t.blockSignals(False)
        self.tabs.setCurrentIndex(5)

    def generate_weekly_summary(self):
        weekly_data = defaultdict(lambda: {"name": "", "total": 0})
        for day in ["MA", "TI", "KE", "TO", "PE", "LA"]:
            table = self.tables[day]
            for row in range(table.rowCount()):
                pid = table.item(row, 4).text()
                if pid:
                    weekly_data[pid]["name"] = table.item(row, 2).text()
                    weekly_data[pid]["total"] += int(table.item(row, 3).text())

        sorted_res = sorted(weekly_data.items(), key=lambda x: x[1]["total"], reverse=True)
        vko_t = self.tables["VKO"]
        vko_t.setRowCount(0)
        vko_t.blockSignals(True)
        for i, (pid, data) in enumerate(sorted_res):
            vko_t.insertRow(i)
            vko_t.setItem(i, 1, NumericItem(str(i + 1)))
            vko_t.setItem(i, 2, QTableWidgetItem(data["name"]))
            vko_t.setItem(i, 3, NumericItem(str(data["total"])))
            vko_t.setItem(i, 4, QTableWidgetItem(pid))
            pfp_l = QLabel()
            pfp_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            p_path = self.get_pfp_path(pid)
            if p_path: pfp_l.setPixmap(QPixmap(p_path).scaled(75, 75, Qt.AspectRatioMode.KeepAspectRatio))
            vko_t.setCellWidget(i, 0, pfp_l)
        vko_t.blockSignals(False)
        self.tabs.setCurrentIndex(6)

    def validate_active_table(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        table = self.tables[tab_name]
        errs = []
        last_val = 999999999999
        for r in range(table.rowCount()):
            try:
                val = int(table.item(r, 3).text().replace(" ", "").replace(".", ""))
                if val > last_val: errs.append(f"Row {r+1}: Order error")
                last_val = val
            except: errs.append(f"Row {r+1}: NaN")
        QMessageBox.information(self, "Validation", "OK" if not errs else "\n".join(errs))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ResultsEditor()
    window.show()
    sys.exit(app.exec())