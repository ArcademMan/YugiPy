"""YugiPy Desktop Launcher – PySide6 dark-themed window with server control."""

import json
import logging
import os
import socket
import sys
import textwrap
from pathlib import Path

from PySide6.QtCore import QProcess, QSize, Qt, QTimer, Slot
from PySide6.QtGui import QColor, QIcon, QPalette, QPixmap, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSystemTrayIcon,
    QMenu,
    QVBoxLayout,
    QWidget,
)

PORT = 8000
# When frozen (PyInstaller), bundled data is in sys._MEIPASS; otherwise use script dir
BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
BASE_DIR = Path(__file__).resolve().parent
CERT_DIR = BASE_DIR / "certs"
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"
ICON_PATH = BUNDLE_DIR / "assets" / "icon.png"
EXTENSION_DIR = BUNDLE_DIR / "extension"
EXTENSION_XPI = BUNDLE_DIR / "assets" / "yugipy-price-sync.xpi"

LOG = logging.getLogger("launcher")

# ── Settings persistence ──────────────────────────────────────

if sys.platform == "darwin":
    SETTINGS_DIR = Path.home() / "Library" / "Application Support" / "AmMstools" / "YugiPy"
elif sys.platform == "win32":
    SETTINGS_DIR = Path(os.environ.get("APPDATA", Path.home())) / "AmMstools" / "YugiPy"
else:
    SETTINGS_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AmMstools" / "YugiPy"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

_DEFAULTS = {
    "protocol": "https",
    "window_width": 478,
    "window_height": 489,
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_settings(settings: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def _deploy_bundled_data():
    """Copy bundled data files (ONNX model, hash DB) to user data dir on first run."""
    if not getattr(sys, 'frozen', False):
        return  # dev mode — files already in user data dir
    bundled_data = BUNDLE_DIR / "data"
    if not bundled_data.exists():
        return
    import shutil
    data_dir = SETTINGS_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("clip_visual.onnx", "card_hashes.db"):
        src = bundled_data / filename
        dst = data_dir / filename
        if src.exists() and not dst.exists():
            LOG.info("Deploying bundled %s to %s", filename, dst)
            shutil.copy2(str(src), str(dst))


def _has_browser(name: str) -> bool:
    """Check if a browser is installed. name: 'firefox' or 'chrome'."""
    import shutil
    if name == "firefox":
        if shutil.which("firefox"):
            return True
        if sys.platform == "darwin":
            return Path("/Applications/Firefox.app").exists()
        if sys.platform == "win32":
            return any(
                Path(p).exists() for p in [
                    os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
                ]
            )
    elif name == "chrome":
        if shutil.which("google-chrome") or shutil.which("google-chrome-stable"):
            return True
        if sys.platform == "darwin":
            return Path("/Applications/Google Chrome.app").exists()
        if sys.platform == "win32":
            return any(
                Path(p).exists() for p in [
                    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                ]
            )
    return False


def _ext_install_links() -> str:
    """Build HTML install links based on which browsers are available."""
    links = []
    if _has_browser("firefox"):
        links.append('<a href="ext://firefox" style="color:#29b6f6;">Firefox</a>')
    if _has_browser("chrome"):
        links.append('<a href="ext://chrome" style="color:#29b6f6;">Chrome</a>')
    if not links:
        links.append('<a href="ext://install" style="color:#29b6f6;">Install</a>')
    return "Install extension: " + " · ".join(links) if links else ""


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_all_local_ips() -> list[str]:
    """Return all local IPv4 addresses (excluding loopback)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and ip != "127.0.0.1":
                ips.append(ip)
    except Exception:
        pass
    return ips


def _cert_needs_regen() -> bool:
    """Check if the existing cert's SANs cover localhost + current local IPs."""
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        return True
    try:
        from cryptography import x509 as x509mod
        cert = x509mod.load_pem_x509_certificate(CERT_FILE.read_bytes())
        ext = cert.extensions.get_extension_for_class(x509mod.SubjectAlternativeName)
        san_dns = set(ext.value.get_values_for_type(x509mod.DNSName))
        san_ips = {str(ip) for ip in ext.value.get_values_for_type(x509mod.IPAddress)}
        needed_ips = {"127.0.0.1"} | set(_get_all_local_ips())
        return not ({"localhost"} <= san_dns and needed_ips <= san_ips)
    except Exception:
        return True


def _ensure_certs():
    """Generate self-signed SSL cert with SANs for localhost + all local IPs."""
    CERT_DIR.mkdir(exist_ok=True)
    if not _cert_needs_regen():
        return
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    import ipaddress

    local_ips = _get_all_local_ips()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "yugipy-local"),
    ])

    san_names = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for ip in local_ips:
        san_names.append(x509.IPAddress(ipaddress.ip_address(ip)))

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_names), critical=False)
        .sign(key, hashes.SHA256())
    )
    KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _load_icon() -> QIcon:
    if ICON_PATH.exists():
        return QIcon(str(ICON_PATH))
    return QIcon()


# ── Dark palette ──────────────────────────────────────────────

def _apply_dark_theme(app: QApplication):
    palette = QPalette()
    C = QColor
    palette.setColor(QPalette.ColorRole.Window, C("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, C("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Base, C("#181818"))
    palette.setColor(QPalette.ColorRole.AlternateBase, C("#2a2a2a"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, C("#252526"))
    palette.setColor(QPalette.ColorRole.ToolTipText, C("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Text, C("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.Button, C("#2d2d2d"))
    palette.setColor(QPalette.ColorRole.ButtonText, C("#d4d4d4"))
    palette.setColor(QPalette.ColorRole.BrightText, C("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, C("#264f78"))
    palette.setColor(QPalette.ColorRole.HighlightedText, C("#ffffff"))
    app.setPalette(palette)

    app.setStyleSheet(textwrap.dedent("""\
        QMainWindow { background: #161616; }
        QMenu { background: #1e1e1e; color: #ccc; border: 1px solid #333; }
        QMenu::item:selected { background: #264f78; }

        QPushButton {
            background: transparent; color: #999; border: 1px solid #333;
            border-radius: 8px; padding: 8px 20px; font-weight: 500; font-size: 9pt;
        }
        QPushButton:hover { background: #1e1e1e; color: #ccc; border-color: #444; }
        QPushButton:pressed { background: #111; }
        QPushButton:disabled { color: #444; border-color: #222; }

        QPushButton#toggleBtn {
            font-size: 11pt; font-weight: 600; padding: 12px 40px;
            border-radius: 10px;
        }
        QPushButton#toggleBtn[running="false"] {
            background: #4caf50; color: #fff; border: none;
        }
        QPushButton#toggleBtn[running="false"]:hover { background: #5cbf60; }
        QPushButton#toggleBtn[running="true"] {
            background: transparent; color: #e53935; border: 1px solid #e53935;
        }
        QPushButton#toggleBtn[running="true"]:hover { background: #2a1515; }
        QPushButton#toggleBtn[running="stopping"] {
            background: transparent; color: #ffa726; border: 1px solid #ffa726;
        }

        QPushButton#browserBtn {
            border-color: #29b6f6; color: #29b6f6;
        }
        QPushButton#browserBtn:hover { background: #112030; }
        QPushButton#browserBtn:disabled { border-color: #222; color: #444; }

        QPushButton#logToggleBtn {
            border: none; color: #555; font-size: 8pt; padding: 4px 0;
            font-weight: 400;
        }
        QPushButton#logToggleBtn:hover { color: #999; }

        QPlainTextEdit {
            background: #111; color: #888; border: 1px solid #222;
            border-radius: 8px; font-family: 'Cascadia Code', Consolas, monospace;
            font-size: 8pt; selection-background-color: #264f78; padding: 8px;
        }

        QLabel { color: #ccc; }

        QLabel#statusDot {
            font-size: 9pt; font-weight: 600; padding: 4px 12px;
            border-radius: 10px;
        }

        QLabel#addrLabel {
            color: #555; font-size: 9pt;
            font-family: 'Cascadia Code', Consolas, monospace;
        }

        QLabel#extLabel { color: #444; font-size: 8pt; }
        QLabel#extLabel a { color: #29b6f6; text-decoration: none; }

        QComboBox {
            background: #1e1e1e; color: #999; border: 1px solid #333;
            border-radius: 6px; padding: 4px 10px; font-size: 8pt;
        }
        QComboBox::drop-down { border: none; }
        QComboBox QAbstractItemView {
            background: #1e1e1e; color: #ccc;
            selection-background-color: #264f78;
        }
    """))


# ── Main Window ───────────────────────────────────────────────

class LauncherWindow(QMainWindow):
    MAX_LOG_LINES = 2000

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AmMstools - YugiPy")
        self.setMinimumSize(400, 300)

        self._settings = load_settings()
        self.resize(self._settings["window_width"], self._settings["window_height"])

        self._icon = _load_icon()
        self.setWindowIcon(self._icon)

        self._process: QProcess | None = None
        self._local_ip = _get_local_ip()
        self._ext_connected = False

        # Poll extension status every 5s while server is running
        self._ext_timer = QTimer(self)
        self._ext_timer.timeout.connect(self._check_extension)
        self._ext_timer.setInterval(5000)

        self._build_ui()
        self._build_tray()

        # Restore saved protocol
        idx = self._proto_combo.findData(self._settings["protocol"])
        if idx >= 0:
            self._proto_combo.setCurrentIndex(idx)

        self._update_state()

    # ── UI ──

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(32, 28, 32, 20)
        layout.setSpacing(0)

        # ── Header: logo + title ──
        logo_label = QLabel()
        if ICON_PATH.exists():
            pixmap = QPixmap(str(ICON_PATH)).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo_label)

        layout.addSpacing(8)

        title = QLabel("YugiPy")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16pt; font-weight: 700; color: #fff;")
        layout.addWidget(title)

        layout.addSpacing(4)

        # ── Status pill ──
        self._status_label = QLabel("Stopped")
        self._status_label.setObjectName("statusDot")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(4)

        # ── Server address ──
        self._addr_label = QLabel("")
        self._addr_label.setObjectName("addrLabel")
        self._addr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._addr_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._addr_label)

        layout.addSpacing(20)

        # ── Primary action ──
        self._toggle_btn = QPushButton("Start server")
        self._toggle_btn.setObjectName("toggleBtn")
        self._toggle_btn.setProperty("running", "false")
        self._toggle_btn.setFixedWidth(200)
        self._toggle_btn.clicked.connect(self._toggle_server)
        layout.addWidget(self._toggle_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(8)

        # ── Secondary actions row ──
        actions_row = QHBoxLayout()
        actions_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions_row.setSpacing(8)

        self._browser_btn = QPushButton("Open in browser")
        self._browser_btn.setObjectName("browserBtn")
        self._browser_btn.clicked.connect(self._open_browser)
        actions_row.addWidget(self._browser_btn)

        self._proto_combo = QComboBox()
        self._proto_combo.addItem("HTTPS", "https")
        self._proto_combo.addItem("HTTP", "http")
        self._proto_combo.currentIndexChanged.connect(self._on_proto_changed)
        actions_row.addWidget(self._proto_combo)

        layout.addLayout(actions_row)

        layout.addSpacing(12)

        # ── Extension status ──
        self._ext_label = QLabel("")
        self._ext_label.setObjectName("extLabel")
        self._ext_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ext_label.setTextFormat(Qt.TextFormat.RichText)
        self._ext_label.setOpenExternalLinks(False)
        self._ext_label.linkActivated.connect(self._on_ext_link)
        layout.addWidget(self._ext_label)

        layout.addStretch()

        # ── Log (collapsed by default) ──
        self._log_toggle_btn = QPushButton("Show logs")
        self._log_toggle_btn.setObjectName("logToggleBtn")
        self._log_toggle_btn.clicked.connect(self._toggle_log)
        layout.addWidget(self._log_toggle_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(self.MAX_LOG_LINES)
        self._log.setVisible(False)
        layout.addWidget(self._log)

    def _build_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._icon if not self._icon.isNull()
                           else self.style().standardIcon(
                               self.style().StandardPixmap.SP_ComputerIcon))
        self._tray.setToolTip("YugiPy")

        menu = QMenu()
        self._tray_toggle = menu.addAction("Start server")
        self._tray_toggle.triggered.connect(self._toggle_server)
        menu.addSeparator()
        tray_browser = menu.addAction("Open in browser")
        tray_browser.triggered.connect(self._open_browser)
        menu.addSeparator()
        tray_show = menu.addAction("Show window")
        tray_show.triggered.connect(self._show_window)
        tray_quit = menu.addAction("Quit")
        tray_quit.triggered.connect(self._quit)
        self._tray.setContextMenu(menu)

        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    # ── Log toggle ──

    @Slot()
    def _toggle_log(self):
        visible = not self._log.isVisible()
        self._log.setVisible(visible)
        self._log_toggle_btn.setText("Hide logs" if visible else "Show logs")
        # Resize window to accommodate log
        if visible:
            self.resize(self.width(), max(self.height(), 520))

    # ── Protocol ──

    @Slot()
    def _on_proto_changed(self):
        self._save_settings()

    @property
    def _use_https(self) -> bool:
        return self._proto_combo.currentData() == "https"

    @property
    def _server_url(self) -> str:
        scheme = "https" if self._use_https else "http"
        return f"{scheme}://{self._local_ip}:{PORT}"

    # ── Server control ──

    @Slot()
    def _start_server(self):
        if self._process is not None:
            return

        if self._use_https:
            _ensure_certs()

        self._process = QProcess(self)
        self._process.setWorkingDirectory(str(BASE_DIR))
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        exe = sys.executable
        if getattr(sys, 'frozen', False):
            # Frozen PyInstaller exe: re-launch ourselves with --server flag
            args = [
                "--server",
                "--host", "0.0.0.0",
                "--port", str(PORT),
            ]
        else:
            args = [
                "-m", "uvicorn",
                "backend.app.main:app",
                "--host", "0.0.0.0",
                "--port", str(PORT),
            ]
        if self._use_https:
            args += ["--ssl-keyfile", str(KEY_FILE), "--ssl-certfile", str(CERT_FILE)]

        self._log.clear()
        proto_name = "HTTPS" if self._use_https else "HTTP"
        self._append_log(f"Starting server ({proto_name})...", "#4caf50")
        self._process.start(exe, args)
        self._update_state()

    @Slot()
    def _stop_server(self):
        if self._process is None:
            return
        self._toggle_btn.setEnabled(False)
        self._toggle_btn.setText("Stopping...")
        self._toggle_btn.setProperty("running", "stopping")
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)
        self._status_label.setText("Stopping server...")
        self._status_label.setStyleSheet("color: #ffa726;")
        self._append_log("Stopping server...", "#ffa726")
        self._process.terminate()
        QTimer.singleShot(5000, self._force_kill)

    def _force_kill(self):
        if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()

    @Slot()
    def _toggle_server(self):
        if self._process is not None:
            self._stop_server()
        else:
            self._start_server()

    # ── Process signals ──

    @Slot()
    def _on_stdout(self):
        if self._process is None:
            return
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            if not line.strip():
                continue
            lower = line.lower()
            if "error" in lower or "traceback" in lower:
                self._append_log(line, "#e53935")
            elif "warning" in lower or "warn" in lower:
                self._append_log(line, "#ffa726")
            else:
                self._append_log(line)

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self._append_log("Server stopped.", "#ffa726")
        else:
            self._append_log(f"Server exited with code {exit_code}", "#e53935")
            if self._tray.isVisible():
                self._tray.showMessage(
                    "YugiPy",
                    f"Server stopped unexpectedly (exit code {exit_code})",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000,
                )
        self._process = None
        self._toggle_btn.setEnabled(True)
        self._update_state()

    @Slot(QProcess.ProcessError)
    def _on_error(self, error):
        self._append_log(f"Process error: {error}", "#e53935")
        self._process = None
        self._toggle_btn.setEnabled(True)
        self._update_state()

    # ── UI helpers ──

    def _append_log(self, text: str, color: str | None = None):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color or "#d4d4d4"))
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def _update_state(self):
        running = self._process is not None

        self._toggle_btn.setProperty("running", "true" if running else "false")
        self._toggle_btn.setText("Stop server" if running else "Start server")
        # Force style refresh after dynamic property change
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)

        self._browser_btn.setEnabled(running)
        self._proto_combo.setEnabled(not running)

        if running:
            self._status_label.setText("Running")
            self._status_label.setStyleSheet(
                "color: #4caf50; background: #1b2e1b; border-radius: 10px;"
                " padding: 4px 14px; font-size: 9pt; font-weight: 600;")
            self._addr_label.setText(self._server_url)
            self._tray_toggle.setText("Stop server")
            self._tray.setToolTip(f"YugiPy – running ({self._server_url})")
            self._ext_timer.start()
            QTimer.singleShot(2000, self._check_extension)
        else:
            self._status_label.setText("Stopped")
            self._status_label.setStyleSheet(
                "color: #666; background: #1e1e1e; border-radius: 10px;"
                " padding: 4px 14px; font-size: 9pt; font-weight: 600;")
            self._addr_label.setText("")
            self._ext_label.setText(_ext_install_links())
            self._ext_connected = False
            self._tray_toggle.setText("Start server")
            self._tray.setToolTip("YugiPy – stopped")
            self._ext_timer.stop()

    @Slot()
    def _check_extension(self):
        """Poll the server to check if the Firefox extension is connected."""
        if self._process is None:
            return
        import urllib.request
        import ssl
        import json as _json

        scheme = "https" if self._use_https else "http"
        ctx = None
        if self._use_https:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        try:
            url = f"{scheme}://127.0.0.1:{PORT}/api/extension/status"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2, context=ctx) as resp:
                data = _json.loads(resp.read())
                connected = data.get("connected", False)
        except Exception:
            connected = False

        self._ext_connected = connected
        if connected:
            self._ext_label.setText(
                '<span style="color:#4caf50;">Extension connected</span>')
        else:
            self._ext_label.setText(
                '<span style="color:#444;">Extension not connected</span>'
                ' · ' + _ext_install_links())

    @Slot(str)
    def _on_ext_link(self, url):
        """Install the browser extension (Firefox .xpi or Chrome unpacked)."""
        import webbrowser
        if url == "ext://firefox":
            if EXTENSION_XPI.exists():
                webbrowser.open(EXTENSION_XPI.as_uri())
        elif url == "ext://chrome":
            # Chrome doesn't allow direct .crx install — open extensions page
            # and the extension folder so the user can "Load unpacked"
            webbrowser.open("chrome://extensions/")
            self._open_folder(EXTENSION_DIR)
        else:
            # Legacy / single "install" link — detect best option
            if _has_browser("firefox"):
                if EXTENSION_XPI.exists():
                    webbrowser.open(EXTENSION_XPI.as_uri())
            elif _has_browser("chrome"):
                webbrowser.open("chrome://extensions/")
                self._open_folder(EXTENSION_DIR)
            else:
                self._open_folder(EXTENSION_DIR)

    @staticmethod
    def _open_folder(path: Path):
        import subprocess
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    @Slot()
    def _open_browser(self):
        import webbrowser
        webbrowser.open(self._server_url)

    @Slot()
    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    # ── Settings persistence ──

    def _save_settings(self):
        self._settings["protocol"] = self._proto_combo.currentData() or "https"
        size = self.size()
        self._settings["window_width"] = size.width()
        self._settings["window_height"] = size.height()
        save_settings(self._settings)

    # ── Window lifecycle ──

    def closeEvent(self, event):
        """Minimize to tray on close instead of quitting."""
        self._save_settings()
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "YugiPy",
            "Application minimized to system tray.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    @Slot()
    def _quit(self):
        self._save_settings()
        if self._process is not None:
            self._process.terminate()
            self._process.waitForFinished(3000)
            if self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning:
                self._process.kill()
        QApplication.quit()


# ── Entry point ───────────────────────────────────────────────

def _acquire_single_instance():
    """Ensure only one instance of the launcher is running.

    Windows: named mutex via kernel32.
    macOS/Linux: file lock via fcntl.flock (held for process lifetime).
    Returns a handle/fd to keep alive, or None if another instance exists.
    """
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex_name = "Global\\AmMstools_YugiPy_Launcher"
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        last_error = kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return None
        return handle
    else:
        import fcntl
        lock_path = SETTINGS_DIR / ".launcher.lock"
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        fd = open(lock_path, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fd.write(str(os.getpid()))
            fd.flush()
            return fd  # keep fd open — lock released when process exits
        except OSError:
            fd.close()
            return None


def _run_server():
    """Run uvicorn directly (used when launched with --server from frozen exe)."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--ssl-keyfile", default=None)
    parser.add_argument("--ssl-certfile", default=None)
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
    )


def main():
    # If launched with --server, run uvicorn instead of the GUI
    if "--server" in sys.argv:
        _run_server()
        return

    _deploy_bundled_data()

    mutex = _acquire_single_instance()
    if mutex is None:
        # Another instance is already running — show a message and exit
        app = QApplication(sys.argv)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, "YugiPy", "YugiPy is already running.")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("YugiPy")
    app.setQuitOnLastWindowClosed(False)

    icon = _load_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    _apply_dark_theme(app)

    window = LauncherWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
