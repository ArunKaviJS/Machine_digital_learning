"""System-tray presence: Bro lives here when hidden ("on_demand" presence).

Left/double-click calls Bro; the tray menu has Call / Quit. Nothing on the
desktop until called or until Bro has something to say.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from client.placeholder_svg import character_svg


def droplet_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(character_svg("idle").encode()))
    box = renderer.viewBoxF()
    width = size * box.width() / box.height() if box.height() else size
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF((size - width) / 2, 0, width, size))
    painter.end()
    return QIcon(pixmap)


class BroTray(QObject):
    call = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, hotkey_text: str):
        super().__init__()
        self.tray = QSystemTrayIcon(droplet_icon())
        hint = f" ({hotkey_text})" if hotkey_text else ""
        self.tray.setToolTip(f"Bro — click to call me{hint}")
        self.tray.activated.connect(self._on_activated)
        self._menu = QMenu()
        self._menu.addAction("Call Bro").triggered.connect(self.call)
        self._menu.addAction("Quit Bro").triggered.connect(self.quit_requested)
        self.tray.setContextMenu(self._menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.call.emit()

    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def notify(self, title: str, message: str) -> None:
        self.tray.showMessage(title, message, self.tray.icon(), 6000)
