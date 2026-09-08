from __future__ import print_function

import glob
import io
import json
import os
import shutil
import threading
import urllib.request
import zipfile

from enigma import eTimer
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Plugins.Plugin import PluginDescriptor
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen


PLUGIN_NAME = "Satellite Picons"
BASE_URL = "https://grgopitic.github.io/satellite-picons"
DESTINATIONS = [
    "/media/hdd/picon",
    "/media/usb/picon",
    "/usr/share/enigma2/picon",
]


def _get(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SatellitePicons-Enigma2Plugin/0.2"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _get_json(name):
    return json.loads(_get(BASE_URL.rstrip("/") + "/" + name).decode("utf-8"))


def _safe_destination():
    for path in DESTINATIONS:
        parent = os.path.dirname(path)
        if os.path.isdir(path) or os.path.isdir(parent):
            return path
    return "/usr/share/enigma2/picon"


def _service_identity_from_filename(filename):
    stem = os.path.basename(filename)
    if stem.lower().endswith(".png"):
        stem = stem[:-4]

    parts = stem.split("_")
    if len(parts) < 10:
        return None

    # 1_0_19_SID_TSID_ONID_NAMESPACE_0_0_0.png
    return "_".join(part.upper() for part in parts[3:7])


def _service_identity_from_reference(reference):
    parts = reference.strip().strip(":").split(":")
    if len(parts) < 7:
        return None
    return "_".join(part.upper() for part in parts[3:7])


def _bouquet_service_identities():
    identities = set()
    paths = []
    paths.extend(glob.glob("/etc/enigma2/userbouquet*.tv"))
    paths.extend(glob.glob("/etc/enigma2/userbouquet*.radio"))

    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if not line.startswith("#SERVICE "):
                        continue

                    reference = line[len("#SERVICE "):].strip()
                    # Ignore IPTV/URL and marker entries. DVB services have the
                    # SID/TSID/ONID/namespace fields needed for SRP matching.
                    if "://" in reference:
                        continue

                    identity = _service_identity_from_reference(reference)
                    if identity:
                        identities.add(identity)
        except (IOError, OSError):
            continue

    return identities


def _install_zip(package, destination, mode="all"):
    blob = _get(BASE_URL.rstrip("/") + "/" + package)
    os.makedirs(destination, exist_ok=True)

    bouquet_ids = None
    if mode == "bouquets":
        bouquet_ids = _bouquet_service_identities()
        if not bouquet_ids:
            raise RuntimeError(
                "V /etc/enigma2 sa nenašli žiadne DVB kanály v userbouquet súboroch."
            )

    installed = 0
    candidates = 0
    skipped = 0

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".png"):
                continue

            name = os.path.basename(info.filename)
            if not name:
                continue

            candidates += 1
            target = os.path.join(destination, name)

            if mode == "bouquets":
                identity = _service_identity_from_filename(name)
                if not identity or identity not in bouquet_ids:
                    skipped += 1
                    continue

            if mode == "existing" and not os.path.isfile(target):
                skipped += 1
                continue

            with archive.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            installed += 1

    return {
        "installed": installed,
        "candidates": candidates,
        "skipped": skipped,
        "mode": mode,
    }


class SatellitePiconsScreen(Screen):
    skin = """
    <screen name="SatellitePiconsScreen" position="center,center" size="980,600" title="Satellite Picons">
        <widget name="title" position="35,28" size="910,45" font="Regular;32" />
        <widget name="subtitle" position="35,78" size="910,34" font="Regular;20" foregroundColor="#9aa9b8" />

        <widget name="list" position="35,130" size="910,320" scrollbarMode="showOnDemand" />

        <widget name="status" position="35,470" size="910,40" font="Regular;20" foregroundColor="#9aa9b8" />

        <widget name="key_red" position="35,535" size="210,38" font="Regular;20" foregroundColor="#ff6565" />
        <widget name="key_green" position="255,535" size="220,38" font="Regular;20" foregroundColor="#6ee7a0" />
        <widget name="key_yellow" position="485,535" size="220,38" font="Regular;20" foregroundColor="#f4dc64" />
        <widget name="key_blue" position="715,535" size="230,38" font="Regular;20" foregroundColor="#6ba7ff" />
    </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)

        self.destination = _safe_destination()
        self.providers = []
        self.providers_by_label = {}
        self.version = None
        self.busy = False
        self.result = None
        self.result_lock = threading.Lock()

        self["title"] = Label("Satellite Picons")
        self["subtitle"] = Label("Balíky piconov podľa TV platformy")
        self["list"] = MenuList(["Načítavam zoznam platforiem…"])
        self["status"] = Label("Cieľ: %s" % self.destination)
        self["key_red"] = Label("Červená: Zavrieť")
        self["key_green"] = Label("Zelená/OK: Možnosti")
        self["key_yellow"] = Label("Žltá: Umiestnenie")
        self["key_blue"] = Label("Modrá: Všetky")

        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "DirectionActions"],
            {
                "ok": self.download_selected,
                "green": self.download_selected,
                "yellow": self.choose_destination,
                "blue": self.download_all,
                "cancel": self.close,
                "red": self.close,
            },
            -1,
        )

        self.timer = eTimer()
        try:
            self.timer.callback.append(self._poll_result)
            self._timer_connection = None
        except Exception:
            self._timer_connection = self.timer.timeout.connect(self._poll_result)

        self.onLayoutFinish.append(self.reload_catalog)
        self.onClose.append(self._cleanup)

    def _cleanup(self):
        try:
            self.timer.stop()
        except Exception:
            pass

    def _set_result(self, kind, payload):
        with self.result_lock:
            self.result = (kind, payload)

    def _take_result(self):
        with self.result_lock:
            result = self.result
            self.result = None
            return result

    def _start_worker(self, target):
        if self.busy:
            return
        self.busy = True
        self.timer.start(200, False)
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()

    def reload_catalog(self):
        self["status"].setText("Načítavam provider katalóg…")

        def worker():
            try:
                version = _get_json("version.json")
                catalog = _get_json(version.get("providers", "providers.json"))
                self._set_result("catalog", (version, catalog))
            except Exception as error:
                self._set_result(
                    "error",
                    "Nepodarilo sa načítať katalóg: %s" % error,
                )

        self._start_worker(worker)

    def _poll_result(self):
        result = self._take_result()
        if result is None:
            return

        self.busy = False
        kind, payload = result

        if kind == "catalog":
            self.version, catalog = payload
            self.providers = catalog.get("providers", [])
            self._render_providers()
            self["status"].setText("Cieľ: %s" % self.destination)
            return

        if kind == "download":
            label, stats = payload
            installed = stats["installed"]
            candidates = stats["candidates"]

            self["status"].setText(
                "Hotovo: %s · %d/%d piconov" % (
                    label,
                    installed,
                    candidates,
                )
            )
            self.session.open(
                MessageBox,
                "%s\n\nNainštalovaných: %d\nV balíku: %d\nPreskočených: %d\nCieľ: %s"
                % (
                    label,
                    installed,
                    candidates,
                    stats["skipped"],
                    self.destination,
                ),
                MessageBox.TYPE_INFO,
                timeout=8,
            )
            return

        self["status"].setText(str(payload))
        self.session.open(
            MessageBox,
            str(payload),
            MessageBox.TYPE_ERROR,
            timeout=8,
        )

    def _render_providers(self):
        rows = []
        self.providers_by_label = {}

        for provider in self.providers:
            name = provider.get("name") or provider.get("id") or "Provider"
            if provider.get("available"):
                label = "%s   ·   %s kanálov   ·   %s piconov" % (
                    name,
                    provider.get("channel_count", 0),
                    provider.get("picon_count", 0),
                )
            else:
                label = "%s   ·   PRIPRAVUJEME" % name

            rows.append(label)
            self.providers_by_label[label] = provider

        if not rows:
            rows = ["Žiadne provider balíky nie sú dostupné."]

        self["list"].setList(rows)

    def _current_provider(self):
        label = self["list"].getCurrent()
        return self.providers_by_label.get(label)

    def download_selected(self):
        if self.busy:
            return

        provider = self._current_provider()
        if not provider:
            return

        if not provider.get("available") or not provider.get("package"):
            self.session.open(
                MessageBox,
                "%s zatiaľ nemá hotový balík."
                % provider.get("name", "Provider"),
                MessageBox.TYPE_INFO,
                timeout=5,
            )
            return

        choices = [
            ("Celý balík platformy", "all"),
            ("Len moje kanály (bouquety)", "bouquets"),
            ("Aktualizovať iba existujúce picony", "existing"),
        ]
        self.session.openWithCallback(
            lambda choice: self._provider_mode_selected(provider, choice),
            ChoiceBox,
            title="%s – čo chceš stiahnuť?" % provider.get("name", "Provider"),
            list=choices,
        )

    def _provider_mode_selected(self, provider, choice):
        if not choice:
            return

        mode = choice[1]
        mode_label = {
            "all": "celý balík",
            "bouquets": "len moje kanály",
            "existing": "aktualizácia existujúcich",
        }.get(mode, mode)

        label = "%s – %s" % (
            provider.get("name") or provider["id"],
            mode_label,
        )
        self._download(provider["package"], label, mode=mode)

    def download_all(self):
        if self.busy:
            return

        if not self.version or not self.version.get("package"):
            self.session.open(
                MessageBox,
                "Globálny balík zatiaľ nie je pripravený.",
                MessageBox.TYPE_ERROR,
                timeout=5,
            )
            return

        self._download(
            self.version["package"],
            "Všetky platformy",
            mode="all",
        )

    def _download(self, package, label, mode="all"):
        self["status"].setText("Sťahujem: %s…" % label)

        def worker():
            try:
                stats = _install_zip(
                    package,
                    self.destination,
                    mode=mode,
                )
                self._set_result("download", (label, stats))
            except Exception as error:
                self._set_result(
                    "error",
                    "Sťahovanie zlyhalo: %s" % error,
                )

        self._start_worker(worker)

    def choose_destination(self):
        if self.busy:
            return

        choices = []
        for path in DESTINATIONS:
            suffix = " (aktuálne)" if path == self.destination else ""
            choices.append((path + suffix, path))

        self.session.openWithCallback(
            self._destination_selected,
            ChoiceBox,
            title="Kam ukladať picony?",
            list=choices,
        )

    def _destination_selected(self, choice):
        if not choice:
            return
        self.destination = choice[1]
        self["status"].setText("Cieľ: %s" % self.destination)


def main(session, **kwargs):
    session.open(SatellitePiconsScreen)


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name=PLUGIN_NAME,
            description="Sťahovanie picon balíkov podľa TV platformy",
            where=PluginDescriptor.WHERE_PLUGINMENU,
            fnc=main,
        )
    ]
