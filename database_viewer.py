import sys
import sqlite3
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableWidget,
    QTableWidgetItem, QPushButton, QVBoxLayout,
    QWidget, QLabel, QHBoxLayout, QMessageBox,
    QHeaderView, QLineEdit
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt


class DatabaseViewer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Scribe - Player Database")
        self.setMinimumSize(900, 600)

        # Polku kantaan
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.db_path = os.path.join(base_dir, "DATA", "DATABASE", "Players.db")

        # Keskuswidget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # --- YLÄPANEELI + HAKUKENTTÄ ---
        self.top_panel = QHBoxLayout()

        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Hae nimellä, tagilla, ID:llä tai päivämäärällä...")
        self.search_field.textChanged.connect(self.apply_filter)
        self.search_field.setStyleSheet("padding: 8px; font-size: 14px;")

        self.clear_db_btn = QPushButton("TYHJENNÄ KOKO TIETOKANTA")
        self.clear_db_btn.setStyleSheet(
            "background-color: #ff4444; color: white; font-weight: bold; padding: 10px;"
        )
        self.clear_db_btn.clicked.connect(self.clear_entire_db)

        self.top_panel.addWidget(self.search_field)
        self.top_panel.addStretch()
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

        # Muistiin ladattu data (hakua varten)
        self.all_rows = []

        # Lataa data
        self.load_data()

    # ---------------------------------------------------------
    # LATAUS
    # ---------------------------------------------------------
    def load_data(self):
        """Lataa pelaajat tietokannasta ja tallentaa ne muistiin."""
        self.table.setRowCount(0)
        self.all_rows = []

        if not os.path.exists(self.db_path):
            print(f"Tietokantaa ei löydy: {self.db_path}")
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT name, tag, player_id, join_date, pfp_path
                FROM players
            """)
            self.all_rows = cursor.fetchall()
            conn.close()

            self.populate_table(self.all_rows)

        except sqlite3.Error as e:
            print(f"Tietokantavirhe: {e}")

    # ---------------------------------------------------------
    # TAULUKON TÄYTTÖ
    # ---------------------------------------------------------
    def populate_table(self, rows):
        """Täyttää taulukon annetuilla riveillä."""
        self.table.setRowCount(len(rows))
        self.table.verticalHeader().setDefaultSectionSize(110)

        for row_idx, (name, tag, p_id, joined, pfp_path) in enumerate(rows):

            # Profiilikuva
            pfp_label = QLabel()
            pfp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if pfp_path and os.path.exists(pfp_path):
                pixmap = QPixmap(pfp_path)
                scaled_pixmap = pixmap.scaled(
                    100, 100,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                pfp_label.setPixmap(scaled_pixmap)
            else:
                pfp_label.setText("No Image")

            self.table.setCellWidget(row_idx, 0, pfp_label)

            # Tekstit
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(name)))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(tag)))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(p_id)))
            self.table.setItem(row_idx, 4, QTableWidgetItem(str(joined)))

            # Poistopainike
            delete_btn = QPushButton("X")
            delete_btn.setStyleSheet(
                "background-color: #444444; color: white; font-weight: bold;"
            )
            delete_btn.clicked.connect(lambda _, pid=p_id: self.delete_player(pid))
            self.table.setCellWidget(row_idx, 5, delete_btn)

    # ---------------------------------------------------------
    # HAKU / SUODATUS
    # ---------------------------------------------------------
    def apply_filter(self):
        """Suodattaa taulukon hakukentän perusteella."""
        query = self.search_field.text().lower().strip()

        if not query:
            self.populate_table(self.all_rows)
            return

        filtered = []
        for row in self.all_rows:
            name, tag, p_id, joined, pfp = row
            row_text = f"{name} {tag} {p_id} {joined}".lower()
            if query in row_text:
                filtered.append(row)

        self.populate_table(filtered)

    # ---------------------------------------------------------
    # POISTO
    # ---------------------------------------------------------
    def delete_player(self, player_id: str):
        reply = QMessageBox.question(
            self, "Vahvista poisto",
            f"Haluatko varmasti poistaa pelaajan {player_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            conn.commit()
            conn.close()

            self.load_data()

        except sqlite3.Error as e:
            print(f"Virhe poistettaessa: {e}")

    # ---------------------------------------------------------
    # KOKO KANNAN TYHJENNYS
    # ---------------------------------------------------------
    def clear_entire_db(self):
        reply = QMessageBox.question(
            self, "Vahvista tyhjennys",
            "Haluatko varmasti tyhjentää KOKO tietokannan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM players")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='players'")
            conn.commit()
            conn.close()

            self.load_data()

        except sqlite3.Error as e:
            print(f"Virhe tyhjennettäessä: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    app.setStyleSheet("""
        QMainWindow { background-color: #2b2b2b; }
        QTableWidget {
            background-color: #333333;
            color: white;
            gridline-color: #555555;
            border: none;
        }
        QHeaderView::section {
            background-color: #444444;
            color: white;
            padding: 4px;
            border: 1px solid #555555;
        }
        QTableWidget::item { padding: 5px; }
    """)

    window = DatabaseViewer()
    window.show()
    sys.exit(app.exec())
