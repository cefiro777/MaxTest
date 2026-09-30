"""Окно «Поддержать проект».

QR-код показывается в отдельном окне, а не на главном экране: карточка банка
вытянутая, на главном она заняла бы половину высоты и оттеснила рабочие
кнопки. На главном остаётся скромная ссылка.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core.resources import read_bytes

QR_FILE = "donate_qr.png"
QR_MAX_HEIGHT = 420


class DonateDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Поддержать проект")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Спасибо, что пользуетесь MaxTest")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        note = QLabel(
            "Программа бесплатная и останется такой. Если она сэкономила вам "
            "время, поддержать разработку можно переводом через СБП — "
            "отсканируйте код камерой в приложении своего банка."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(note)

        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pixmap = self._load_qr()
        if self._pixmap is None:
            self.qr.setText("QR-код недоступен в этой сборке")
            self.qr.setObjectName("warningNote")
        else:
            self.qr.setPixmap(self._pixmap)
        layout.addWidget(self.qr)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Сохранить картинку…")
        self.save_button.setToolTip(
            "Сохранить QR-код файлом, чтобы отсканировать с другого устройства"
        )
        self.save_button.clicked.connect(self.save_qr)
        self.save_button.setEnabled(self._pixmap is not None)
        buttons.addWidget(self.save_button)
        buttons.addStretch(1)

        close = QPushButton("Закрыть")
        close.setProperty("class", "primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------ QR

    @staticmethod
    def _load_qr() -> QPixmap | None:
        blob = read_bytes(QR_FILE)
        if not blob:
            return None
        pixmap = QPixmap()
        if not pixmap.loadFromData(blob):
            return None
        if pixmap.height() > QR_MAX_HEIGHT:
            pixmap = pixmap.scaledToHeight(
                QR_MAX_HEIGHT, Qt.TransformationMode.SmoothTransformation
            )
        return pixmap

    def save_qr(self) -> None:
        if self._pixmap is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить QR-код",
            str(Path.home() / "MaxTest-донат.png"),
            "Изображения (*.png)",
        )
        if not path:
            return
        blob = read_bytes(QR_FILE)
        try:
            # Пишем исходный файл, а не уменьшенную копию с экрана: печатать и
            # сканировать лучше полное разрешение.
            Path(path).write_bytes(blob or b"")
        except OSError as exc:
            QMessageBox.critical(self, "Не удалось сохранить", str(exc))
            return
        QMessageBox.information(self, "Сохранено", f"QR-код сохранён:\n{path}")
