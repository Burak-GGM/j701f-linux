#!/usr/bin/env python3
"""Touch-sized local network toolbox for Plasma Mobile."""
from __future__ import annotations

import sys
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMainWindow,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget, QLineEdit)

import backend


class Toolbox(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Burak · Network Toolbox")
        self.process: QProcess | None = None
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(self.stop_action)
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setSpacing(12)
        heading = QLabel("Network Toolbox")
        heading.setAlignment(Qt.AlignCenter)
        heading.setFont(QFont("Sans", 23, QFont.Bold))
        box.addWidget(heading)
        self.hint = QLabel("Local device tools")
        self.hint.setWordWrap(True)
        box.addWidget(self.hint)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Monospace", 12))
        box.addWidget(self.output, 1)
        actions = (("Refresh", self.refresh), ("Wi-Fi", lambda: self.run_action("wifi")),
                   ("LAN", lambda: self.run_action("lan")),
                   ("Bluetooth", lambda: self.run_action("bluetooth")),
                   ("Capture", lambda: self.run_action("capture")))
        for row_actions in (actions[:3], actions[3:]):
            row = QHBoxLayout()
            for title, callback in row_actions:
                button = QPushButton(title)
                button.setMinimumHeight(68)
                button.setFont(QFont("Sans", 15))
                button.clicked.connect(callback)
                row.addWidget(button)
            box.addLayout(row)
        port_row = QHBoxLayout()
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("LAN host IP (for example 192.168.1.1)")
        self.host_input.setMinimumHeight(58)
        self.host_input.setFont(QFont("Sans", 14))
        port_row.addWidget(self.host_input, 1)
        ports = QPushButton("Ports")
        ports.setMinimumHeight(58)
        ports.clicked.connect(lambda: self.run_action("ports"))
        port_row.addWidget(ports)
        box.addLayout(port_row)
        usb_row = QHBoxLayout()
        for title, name in (("USB net on", "network-on"), ("USB net off", "network-off"),
                            ("HID on", "hid-on"), ("HID off", "hid-off")):
            button = QPushButton(title)
            button.setMinimumHeight(64)
            button.setFont(QFont("Sans", 12))
            button.clicked.connect(lambda checked=False, action=name: self.run_action(action))
            usb_row.addWidget(button)
        box.addLayout(usb_row)
        hid_row = QHBoxLayout()
        self.hid_input = QLineEdit()
        self.hid_input.setMaxLength(160)
        self.hid_input.setPlaceholderText("Text to type on attached PC (US layout)")
        self.hid_input.setMinimumHeight(58)
        self.hid_input.setFont(QFont("Sans", 14))
        hid_row.addWidget(self.hid_input, 1)
        send = QPushButton("USB type")
        send.setMinimumHeight(58)
        send.clicked.connect(lambda: self.run_action("hid-type"))
        hid_row.addWidget(send)
        box.addLayout(hid_row)
        self.stop = QPushButton("Stop current task")
        self.stop.setMinimumHeight(56)
        self.stop.clicked.connect(self.stop_action)
        self.stop.setEnabled(False)
        box.addWidget(self.stop)
        self.setCentralWidget(panel)
        self.resize(720, 1040)
        self.refresh()

    def refresh(self) -> None:
        if self.process is not None:
            return
        self.hint.setText("Current device status")
        self.output.setPlainText(backend.status())

    def run_action(self, name: str) -> None:
        if self.process is not None:
            return
        hid_data = None
        if name == "hid-type":
            if not self.hid_input.text():
                self.hint.setText("Enter text to send")
                return
            try:
                hid_data = self.hid_input.text().encode("ascii")
            except UnicodeEncodeError:
                self.hint.setText("This USB keyboard supports US ASCII text only")
                return
        try:
            argv, seconds, description = backend.action(name, self.host_input.text() if name == "ports" else None)
        except (OSError, ValueError) as exc:
            self.hint.setText(str(exc))
            return
        self.hint.setText(description)
        self.output.setPlainText(description + "\n\n")
        proc = QProcess(self)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self.read_output)
        proc.errorOccurred.connect(lambda err: self.hint.setText(f"Process error: {err}"))
        proc.finished.connect(self.finished)
        self.process = proc
        self.stop.setEnabled(True)
        proc.start()
        if hid_data is not None:
            proc.write(hid_data)
            proc.closeWriteChannel()
        self.deadline.start(seconds * 1000)

    def read_output(self) -> None:
        if self.process is not None:
            chunk = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
            self.output.insertPlainText(chunk)
            self.output.ensureCursorVisible()

    def finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self.read_output()
        self.deadline.stop()
        self.hint.setText(f"Finished (exit status {code})")
        if self.process is not None:
            self.process.deleteLater()
        self.process = None
        self.stop.setEnabled(False)

    def stop_action(self) -> None:
        proc = self.process
        if proc is not None and proc.state() != QProcess.NotRunning:
            proc.terminate()
            QTimer.singleShot(1500, lambda: proc.kill() if proc.state() != QProcess.NotRunning else None)

    def closeEvent(self, event) -> None:
        self.stop_action()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Toolbox()
    window.show()
    sys.exit(app.exec())
