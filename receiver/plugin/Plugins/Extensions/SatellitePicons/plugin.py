from __future__ import print_function

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
        headers={"User-Agent": "SatellitePicons-Enigma2Plugin/0.1"},
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


def _install_zip(package, destination):
    blob = _get(BASE_URL.rstrip("/") + "/" + package)
    os.makedirs(destination, exist_ok=True)

    installed = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".png"):
                continue

            name = os.path.basename(info.filename)
            if not name:
                continue

            target = os.path.join(destination, name)
            with archive.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            installed += 1

    return installed


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
        self["key_green"] = Label("Zelená/OK: Stiahnuť")
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
                self._set_result("error", "Nepodarilo sa načítať katalóg: %s" % error)

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
            label, installed = payload
            self["status"].setText("Hotovo: %s · %d piconov" % (label, installed))
            self.session.open(
                MessageBox,
                "%s\n\nNainštalovaných piconov: %d\nCieľ: %s" % (
                    label,
                    installed,
                    self.destination,
                ),
                MessageBox.TYPE_INFO,
                timeout=7,
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
                "%s zatiaľ nemá hotový balík." % provider.get("name", "Provider"),
                MessageBox.TYPE_INFO,
                timeout=5,
            )
            return

        self._download(provider["package"], provider.get("name") or provider["id"])

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

        self._download(self.version["package"], "Všetky platformy")

    def _download(self, package, label):
        self["status"].setText("Sťahujem: %s…" % label)

        def worker():
            try:
                installed = _install_zip(package, self.destination)
                self._set_result("download", (label, installed))
            except Exception as error:
                self._set_result("error", "Sťahovanie zlyhalo: %s" % error)

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
