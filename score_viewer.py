import sys
import os
import csv
import sqlite3
from collections import defaultdict

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QLabel,
    QMessageBox
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


# ---------------- NUMERIIKKAA TUKEVA ITEM INDEX- JA SCORE-KOLUMNILLE ----------------

class NumericItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return int(self.text()) < int(other.text())
        except ValueError:
            return super().__lt__(other)


# ---------------- PÄÄOHJELMA ----------------

class ResultsEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scribe – Results Editor")
        self.setMinimumSize(1200, 750)

        # Fontin zoomaus
        self.font_size = 12

        # Polut
        base = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base
        self.results_path = os.path.join(base, "results")
        self.players_db_path = os.path.join(base, "DATA", "DATABASE", "Players.db")

        # CSV-päätteet englanniksi
        self.patterns = {
            "MA": "_mon.csv",
            "TI": "_tues.csv",
            "KE": "_wed.csv",
            "TO": "_thur.csv",
            "PE": "_fri.csv",
            "LA": "_sat.csv",
            "VKO": "_wk.csv"
        }

        # Pelaajien ID:t Players.db:stä
        self.pfp_cache = set()
        self.load_player_ids()

        # UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Yläpalkki
        top = QHBoxLayout()

        self.generate_la_btn = QPushButton("Generoi LA")
        self.generate_la_btn.clicked.connect(self.generate_la_scores)

        self.save_csv_btn = QPushButton("Päivitä CSV")
        self.save_csv_btn.clicked.connect(self.save_active_csv)

        self.validate_btn = QPushButton("Validoi data")
        self.validate_btn.clicked.connect(self.validate_active_table)

        top.addWidget(self.generate_la_btn)
        top.addWidget(self.save_csv_btn)
        top.addWidget(self.validate_btn)
        top.addStretch()
        layout.addLayout(top)

        # Välilehdet
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Taulukot
        self.tables = {}
        for tab_name in ["MA", "TI", "KE", "TO", "PE", "LA", "VKO"]:
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["PFP", "Index", "Playername", "Score", "player_id"])
            table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)

            table.setSortingEnabled(True)
            table.verticalHeader().setDefaultSectionSize(90)

            header = table.horizontalHeader()
            header.setStretchLastSection(True)
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

    # ---------------- FONTIN ZOOMAUS CTRL + HIIRI ----------------

    def wheelEvent(self, event):
        if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.font_size += 1
            else:
                self.font_size -= 1
            self.font_size = max(6, min(40, self.font_size))
            self.update_table_fonts()
            event.accept()
        else:
            super().wheelEvent(event)

    def update_table_fonts(self):
        font = self.font()
        font.setPointSize(self.font_size)
        self.setFont(font)
        for table in self.tables.values():
            table.setFont(font)
            table.resizeRowsToContents()

    # ---------------- SCORE- JA INDEX-KOLUMNIN KORJAUS MUOKKAUKSEN JÄLKEEN ----------------

    def on_item_changed(self, item):
        if item.column() in (1, 3):  # 1 = Index, 3 = Score
            text = item.text()
            table = item.tableWidget()
            new_item = NumericItem(text)
            table.blockSignals(True)
            table.setItem(item.row(), item.column(), new_item)
            table.blockSignals(False)

    # ---------------- Players.db player_id-lataus ----------------

    def load_player_ids(self):
        if not os.path.exists(self.players_db_path):
            return
        try:
            conn = sqlite3.connect(self.players_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT player_id FROM players")
            for (pid,) in cursor.fetchall():
                if pid:
                    self.pfp_cache.add(str(pid))
            conn.close()
        except:
            pass

    # ---------------- Profiilikuvan polun rakentaminen ----------------

    def get_pfp_path(self, player_id: str):
        if not player_id:
            return None
        filename = f"{player_id}_pfp.png"
        folder = os.path.join(self.base_dir, "DATA", "Database", "Profile_pictures")
        full_path = os.path.join(folder, filename)
        return full_path if os.path.exists(full_path) else None

    # ---------------- CSV-lataus ----------------

    def find_csv(self, suffix: str):
        if not os.path.isdir(self.results_path):
            return None
        for fname in os.listdir(self.results_path):
            if fname.lower().endswith(suffix):
                return os.path.join(self.results_path, fname)
        return None

    def load_all_csv(self):
        for tab, suffix in self.patterns.items():
            table = self.tables[tab]
            path = self.find_csv(suffix)
            if path:
                self.load_csv_to_table(path, table)
            else:
                table.setRowCount(0)

    def load_csv_to_table(self, path: str, table: QTableWidget):
        table.setRowCount(0)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=';')
            for row in reader:
                if len(row) < 4:
                    continue
                index, name, score, pid = row
                if not index.isdigit():
                    continue

                row_index = table.rowCount()
                table.insertRow(row_index)

                pfp_label = QLabel()
                pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pfp_path = self.get_pfp_path(pid)
                if pfp_path:
                    pixmap = QPixmap(pfp_path)
                    scaled = pixmap.scaled(
                        75, 75,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    pfp_label.setPixmap(scaled)
                else:
                    pfp_label.setText("No\nImage")
                table.setCellWidget(row_index, 0, pfp_label)

                table.setItem(row_index, 1, NumericItem(index))
                table.setItem(row_index, 2, QTableWidgetItem(name))
                table.setItem(row_index, 3, NumericItem(score))
                table.setItem(row_index, 4, QTableWidgetItem(pid))

    # ---------------- CSV-TALLENNUS ----------------

    def save_active_csv(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        suffix = self.patterns.get(tab_name)
        if not suffix:
            return
        path = self.find_csv(suffix)
        if not path:
            return

        table = self.tables[tab_name]
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Index", "Playername", "Score", "player_id"])
            for row in range(table.rowCount()):
                index = table.item(row, 1).text()
                name = table.item(row, 2).text()
                score = table.item(row, 3).text()
                pid = table.item(row, 4).text()
                writer.writerow([index, name, score, pid])

    # ---------------- DATA VALIDOINNIN TOTEUTUS ----------------

    def validate_active_table(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        table = self.tables[tab_name]

        errors = []
        scores = []

        for row in range(table.rowCount()):
            item = table.item(row, 3)
            if item:
                try:
                    scores.append(int(item.text()))
                except:
                    errors.append(f"Rivi {row+1}: piste ei ole numero")

        for i in range(len(scores) - 1):
            if scores[i] < scores[i + 1]:
                errors.append(f"Virhe indeksissä {i+1} → {i+2}: {scores[i]} < {scores[i+1]}")

        if len(scores) > 1 and scores[0] < max(scores):
            errors.append("Ensimmäinen rivi ei ole suurin pistemäärä")

        msg = QMessageBox(self)
        if errors:
            msg.setWindowTitle("Data EI ole validia")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText("Data sisältää virheitä:")
            msg.setInformativeText("\n".join(errors))
        else:
            msg.setWindowTitle("Data on validia")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText("Kaikki pisteet ovat oikeassa järjestyksessä.")
        msg.exec()

    # ---------------- LA-laskenta ----------------

    def generate_la_scores(self):
        weekday_scores = defaultdict(int)

        for day in ["MA", "TI", "KE", "TO", "PE"]:
            table = self.tables[day]
            for row in range(table.rowCount()):
                name_item = table.item(row, 2)
                score_item = table.item(row, 3)
                if not name_item or not score_item:
                    continue
                name = name_item.text().strip()
                if not name:
                    continue
                try:
                    score = int(score_item.text())
                except:
                    continue
                weekday_scores[name] += score

        vko_scores = {}
        vko_ids = {}
        vko_table = self.tables["VKO"]

        for row in range(vko_table.rowCount()):
            name_item = vko_table.item(row, 2)
            score_item = vko_table.item(row, 3)
            pid_item = vko_table.item(row, 4)
            if not name_item or not score_item:
                continue
            name = name_item.text().strip()
            if not name:
                continue
            try:
                score = int(score_item.text())
            except:
                continue
            vko_scores[name] = score
            vko_ids[name] = pid_item.text() if pid_item else ""

        la_table = self.tables["LA"]
        la_table.setRowCount(0)

        row_idx = 0
        for name, total_week in vko_scores.items():
            weekday_sum = weekday_scores.get(name, 0)
            la_score = total_week - weekday_sum
            pid = vko_ids.get(name, "")

            la_table.insertRow(row_idx)

            pfp_label = QLabel()
            pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pfp_path = self.get_pfp_path(pid)
            if pfp_path:
                pixmap = QPixmap(pfp_path)
                scaled = pixmap.scaled(
                    75, 75,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                pfp_label.setPixmap(scaled)
            else:
                pfp_label.setText("No\nImage")
            la_table.setCellWidget(row_idx, 0, pfp_label)

            la_table.setItem(row_idx, 1, NumericItem(str(row_idx)))
            la_table.setItem(row_idx, 2, QTableWidgetItem(name))
            la_table.setItem(row_idx, 3, NumericItem(str(la_score)))
            la_table.setItem(row_idx, 4, QTableWidgetItem(pid))

            row_idx += 1


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ResultsEditor()
    window.show()
    sys.exit(app.exec())
