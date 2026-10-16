"""Place the capture window beside the mouse on the active monitor."""
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QDialog


class CursorPopup(QDialog):
    GAP = 16

    def show_near_cursor(self):
        anchor = QPoint(QCursor.pos())
        screen = QGuiApplication.screenAt(anchor) or self.screen() or QGuiApplication.primaryScreen()
        self.ensurePolished()
        if self.layout():
            self.layout().activate()
        if screen:
            # Pre-position the hidden window so its first appearance is nearby.
            self._place_beside(anchor, screen.availableGeometry())
        self.showNormal()
        if screen:
            # Window decorations are known after the first native show.
            self._place_beside(anchor, screen.availableGeometry())
        QTimer.singleShot(0, self._keep_on_screen)

    def _place_beside(self, anchor, area):
        frame = self.frameGeometry()
        x = anchor.x() + self.GAP
        y = anchor.y() + self.GAP
        if x + frame.width() > area.right() + 1:
            x = anchor.x() - frame.width() - self.GAP
        if y + frame.height() > area.bottom() + 1:
            y = anchor.y() - frame.height() - self.GAP
        self.move(self._clamp(QPoint(x, y), frame.size(), area))

    @staticmethod
    def _clamp(position, size, area):
        # Oversized windows keep their title bar accessible even on small screens.
        max_x = max(area.left(), area.right() + 1 - size.width())
        max_y = max(area.top(), area.bottom() + 1 - size.height())
        return QPoint(max(area.left(), min(position.x(), max_x)),
                      max(area.top(), min(position.y(), max_y)))

    def _keep_on_screen(self):
        if not self.isVisible():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen:
            frame = self.frameGeometry()
            position = self._clamp(frame.topLeft(), frame.size(), screen.availableGeometry())
            if position != frame.topLeft():
                self.move(position)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            # Dictionary results can change the layout after translation finishes.
            # Preserve a user's chosen position, moving only to keep it on-screen.
            QTimer.singleShot(0, self._keep_on_screen)
