"""Launch with python -m lilt, or use the packaged Lilt.exe."""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from .instance import InstanceLock
from .storage import Store
from .ui import Controller, MainWindow, STYLE


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .selftest import main as self_test
        return self_test(sys.argv[2])
    startup_launch = "--startup" in sys.argv[1:]
    app = QApplication(sys.argv)
    app.setApplicationName("Lilt")
    app.setOrganizationName("Lilt")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    store = Store()
    # A second launch brings the existing window forward instead of doubling hooks.
    lock = InstanceLock(store.data_dir)
    if not lock.acquire():
        if not startup_launch:
            lock.activate_existing()
        return 0
    controller = Controller(store)
    window = MainWindow(controller)
    activation_timer = QTimer()
    activation_timer.setInterval(200)
    def activate_if_requested():
        if lock.consume_activation():
            window.show_main()
    activation_timer.timeout.connect(activate_if_requested)
    activation_timer.start()
    def exception_hook(kind, value, tb):
        # Do not include user text or credentials in persistent crash logs.
        QMessageBox.critical(window, "Lilt ran into a problem", f"{kind.__name__}: {value}")
    sys.excepthook = exception_hook
    if not startup_launch or window.tray is None:
        window.show()
    result = app.exec()
    lock.release()
    return result


if __name__ == "__main__":
    sys.exit(main())
