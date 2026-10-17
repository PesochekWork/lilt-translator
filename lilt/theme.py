"""Restrained charcoal and orange styling for Lilt's native Qt widgets."""

from pathlib import Path


_CHECK_URL = (Path(__file__).resolve().parent / "assets" / "check.svg").as_posix()
_DOWN_URL = (Path(__file__).resolve().parent / "assets" / "down.svg").as_posix()

STYLE = """
QWidget {
    font-family: 'Segoe UI';
    font-size: 13px;
    color: #eeeeec;
    selection-background-color: #ff9a21;
    selection-color: #111111;
}
QMainWindow, QDialog, QMessageBox, QWidget#body {
    background-color: #1b1b1b;
}
QLabel { background: transparent; }
QWidget#sidebar {
    background-color: #151515;
    border-right: 1px solid #484848;
}
QLabel#brand {
    color: #ff9a21;
    font-size: 25px;
    font-weight: 700;
    letter-spacing: -0.5px;
}
QLabel#heading {
    color: #f6f6f3;
    font-size: 25px;
    font-weight: 600;
}
QLabel#muted { color: #b3b3ae; font-size: 12px; }
QLabel#eyebrow {
    color: #cfcec8;
    font-family: 'Consolas';
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}
QFrame#panel {
    background-color: #232323;
    border: 1px solid #414141;
    border-top-color: #555555;
    border-left-color: #4b4b4b;
    border-bottom-color: #101010;
    border-right-color: #101010;
    border-radius: 1px;
}
QLabel#banner {
    color: #ffbd70;
    background-color: #30271c;
    border: 1px solid #6c4c25;
    border-left: 3px solid #ff9a21;
    border-radius: 1px;
    padding: 9px 12px;
}
QLabel#banner[error="true"] {
    color: #ffb89f;
    background-color: #34231d;
    border-color: #89533c;
    border-left-color: #ff9568;
}
QTextEdit, QPlainTextEdit {
    color: #f1f1ed;
    background-color: #232323;
    border: 1px solid transparent;
    border-radius: 1px;
    padding: 5px;
    font-size: 19px;
    selection-background-color: #ff9a21;
    selection-color: #111111;
}
QTextEdit:focus, QPlainTextEdit:focus { border-color: #ff9a21; }
QTextEdit#translation { color: #ffb45a; }
QTextEdit#details {
    font-size: 18px;
    background: transparent;
    border: none;
    padding: 0;
}
QTextEdit#context {
    font-size: 13px;
    background-color: #191919;
    border: 1px solid #505050;
    border-top-color: #0b0b0b;
    border-left-color: #0b0b0b;
    padding: 7px;
}
QTextEdit#context:focus { border-color: #ff9a21; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    color: #f1f1ed;
    background-color: #191919;
    border: 1px solid #505050;
    border-top-color: #090909;
    border-left-color: #090909;
    border-radius: 1px;
    padding: 7px 10px;
    selection-background-color: #ff9a21;
    selection-color: #111111;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #ff9a21;
}
QLineEdit:disabled, QComboBox:disabled, QTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: #9d9d97;
    background-color: #242424;
    border-color: #3c3c3c;
}
QComboBox { min-height: 19px; padding-right: 25px; }
QComboBox:editable { padding-left: 7px; }
QComboBox QLineEdit {
    color: #f1f1ed;
    background-color: #191919;
    border: none;
    padding: 0;
}
QComboBox::drop-down {
    background-color: #303030;
    border-left: 1px solid #4a4a4a;
    width: 22px;
}
QComboBox::drop-down:hover { background-color: #414141; }
QComboBox::down-arrow {
    width: 8px;
    height: 5px;
    border: none;
    image: url("__DOWN_URL__");
}
QComboBox QAbstractItemView, QAbstractItemView {
    color: #eeeeec;
    background-color: #242424;
    alternate-background-color: #2c2c2c;
    border: 1px solid #62625a;
    outline: 0;
    selection-background-color: #ff9a21;
    selection-color: #111111;
}
QComboBox QAbstractItemView::item { min-height: 25px; padding: 3px 8px; }
QComboBox QAbstractItemView::item:selected {
    background-color: #ff9a21;
    color: #111111;
}
QPushButton, QToolButton {
    color: #ededE8;
    background-color: #333333;
    border: 1px solid #171717;
    border-top-color: #60605a;
    border-left-color: #53534f;
    border-radius: 1px;
    padding: 8px 12px;
    font-weight: 600;
}
QPushButton:hover, QToolButton:hover {
    background-color: #41413d;
    color: #ffffff;
    border-top-color: #77776d;
    border-left-color: #686860;
}
QPushButton:pressed, QToolButton:pressed {
    background-color: #292929;
    border-top-color: #101010;
    border-left-color: #101010;
    border-bottom-color: #55554e;
    border-right-color: #55554e;
}
QPushButton:focus, QToolButton:focus { border-color: #ff9a21; }
QPushButton:disabled, QToolButton:disabled {
    color: #a0a09a;
    background-color: #292929;
    border-color: #3a3a37;
}
QPushButton#primary {
    color: #121212;
    background-color: #ff9a21;
    border-top-color: #ffc273;
    border-left-color: #ffbd68;
    border-bottom-color: #8b4b05;
    border-right-color: #8b4b05;
}
QPushButton#primary:hover { color: #0b0b0b; background-color: #ffac45; }
QPushButton#primary:pressed {
    color: #101010;
    background-color: #e88913;
    border-top-color: #7c4205;
    border-left-color: #7c4205;
    border-bottom-color: #ffc16b;
    border-right-color: #ffc16b;
}
QPushButton#primary:focus { border-color: #fff1db; }
QPushButton#primary:disabled {
    color: #c9b69d;
    background-color: #66513a;
    border-color: #74614a;
}
QPushButton#nav {
    text-align: left;
    color: #c1c1ba;
    background: transparent;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    padding: 11px 11px;
    font-weight: 500;
}
QPushButton#nav:hover { background-color: #292929; color: #ffffff; }
QPushButton#nav:checked {
    color: #ffad49;
    background-color: #30281d;
    border-color: #4b4030;
    border-left-color: #ff9a21;
}
QPushButton#nav:focus { border-color: #ff9a21; }
QPushButton#quiet {
    color: #d3d2c9;
    background: transparent;
    border: 1px solid transparent;
    padding: 5px 8px;
}
QPushButton#quiet:hover { color: #ffb45a; background-color: #33312b; }
QPushButton#quiet:focus { border-color: #ff9a21; }
QPushButton#quiet:disabled { color: #92928d; background: transparent; }
QCheckBox {
    color: #eeeeec;
    background: transparent;
    spacing: 10px;
    padding: 3px 0;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 0;
    border: 1px solid #60605a;
    border-top-color: #080808;
    border-left-color: #080808;
    background-color: #191919;
}
QCheckBox::indicator:hover { border-color: #ff9a21; }
QCheckBox::indicator:checked {
    background-color: #ff9a21;
    border-color: #ff9a21;
    image: url("__CHECK_URL__");
}
QCheckBox::indicator:checked:hover {
    background-color: #ffad45;
    border-color: #ffd49a;
}
QCheckBox:focus { color: #ffc578; }
QCheckBox::indicator:focus { border-color: #ffe0b3; }
QCheckBox:disabled { color: #a0a09a; }
QCheckBox::indicator:disabled { background-color: #292929; border-color: #484844; }
QCheckBox::indicator:checked:disabled {
    background-color: #8b683c;
    border-color: #9b784b;
    image: url("__CHECK_URL__");
}
QMenu, QMenuBar {
    color: #eeeeec;
    background-color: #242424;
    border: 1px solid #575750;
    padding: 3px;
}
QMenu::item { padding: 7px 24px 7px 13px; background: transparent; }
QMenu::item:selected, QMenuBar::item:selected {
    color: #111111;
    background-color: #ff9a21;
}
QMenu::item:disabled { color: #969690; }
QMenu::separator { height: 1px; background-color: #484844; margin: 4px 8px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background-color: #1b1b1b; }
QScrollBar:vertical {
    width: 10px;
    background-color: #171717;
    margin: 0;
    border-left: 1px solid #333330;
}
QScrollBar::handle:vertical {
    background-color: #595952;
    border: 1px solid #6b6b62;
    border-right-color: #30302b;
    border-bottom-color: #30302b;
    min-height: 24px;
    border-radius: 0;
}
QScrollBar::handle:vertical:hover { background-color: #a37033; border-color: #ff9a21; }
QScrollBar:horizontal {
    height: 10px;
    background-color: #171717;
    margin: 0;
    border-top: 1px solid #333330;
}
QScrollBar::handle:horizontal {
    background-color: #595952;
    border: 1px solid #6b6b62;
    border-right-color: #30302b;
    border-bottom-color: #30302b;
    min-width: 24px;
    border-radius: 0;
}
QScrollBar::handle:horizontal:hover { background-color: #a37033; border-color: #ff9a21; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QAbstractScrollArea::corner { background-color: #1b1b1b; border: none; }
QToolTip {
    color: #f4f0e7;
    background-color: #292720;
    border: 1px solid #ff9a21;
    padding: 6px 8px;
}
QSizeGrip { background-color: #1b1b1b; }
QDialogButtonBox { background: transparent; }
""".replace("__CHECK_URL__", _CHECK_URL).replace("__DOWN_URL__", _DOWN_URL)
