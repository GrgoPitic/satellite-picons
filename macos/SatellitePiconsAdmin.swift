import AppKit
import Foundation
import Darwin

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let adminURL = URL(string: "http://127.0.0.1:8765")!
    private let healthURL = URL(string: "http://127.0.0.1:8765/health")!
    private let pidFile = URL(fileURLWithPath: "/tmp/satellite-picons-admin.pid")
    private let repoPath: String

    private var statusItem: NSStatusItem!
    private var openItem: NSMenuItem!
    private var stopItem: NSMenuItem!
    private var restartItem: NSMenuItem!
    private var statusMenuItem: NSMenuItem!
    private var pollTimer: Timer?
    private var launchTask: Process?
    private var openedBrowser = false
    private var healthCheckInFlight = false
    private var startupDecisionMade = false
    private var isStopping = false

    init(repoPath: String) {
        self.repoPath = repoPath
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Menu-bar utility: no empty Dock app and no "application is not responding"
        // impression while the local admin server starts.
        NSApp.setActivationPolicy(.accessory)
        setupMenuBar()
        setStatus("Kontrolujem stav…", canOpen: false, canStop: false)

        refreshStatus(startIfNeeded: true)

        pollTimer = Timer.scheduledTimer(
            timeInterval: 1.5,
            target: self,
            selector: #selector(timerRefreshStatus),
            userInfo: nil,
            repeats: true
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        pollTimer = nil
        stopAdminImmediately()
    }

    private func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.image = NSImage(
                systemSymbolName: "antenna.radiowaves.left.and.right",
                accessibilityDescription: "Satellite Picons Admin"
            ) ?? NSImage(systemSymbolName: "tv", accessibilityDescription: "Satellite Picons Admin")
        }

        let menu = NSMenu()

        statusMenuItem = NSMenuItem(title: "Kontrolujem stav…", action: nil, keyEquivalent: "")
        statusMenuItem.isEnabled = false
        menu.addItem(statusMenuItem)

        menu.addItem(.separator())

        openItem = NSMenuItem(
            title: "Otvoriť Admin",
            action: #selector(openAdminAction),
            keyEquivalent: "o"
        )
        openItem.target = self
        menu.addItem(openItem)

        restartItem = NSMenuItem(
            title: "Reštartovať Admin",
            action: #selector(restartAdminAction),
            keyEquivalent: "r"
        )
        restartItem.target = self
        menu.addItem(restartItem)

        stopItem = NSMenuItem(
            title: "Zastaviť Admin",
            action: #selector(stopAdminAction),
            keyEquivalent: ""
        )
        stopItem.target = self
        menu.addItem(stopItem)

        menu.addItem(.separator())

        let logItem = NSMenuItem(
            title: "Zobraziť log",
            action: #selector(openLogAction),
            keyEquivalent: ""
        )
        logItem.target = self
        menu.addItem(logItem)

        menu.addItem(.separator())

        let quitItem = NSMenuItem(
            title: "Ukončiť Satellite Picons Admin",
            action: #selector(quitApp),
            keyEquivalent: "q"
        )
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    private func setStatus(_ title: String, canOpen: Bool, canStop: Bool) {
        statusMenuItem.title = title
        openItem.isEnabled = canOpen
        stopItem.isEnabled = canStop
        restartItem.isEnabled = canStop || canOpen
    }

    private func checkHealth(completion: @escaping (Bool) -> Void) {
        if healthCheckInFlight {
            return
        }
        healthCheckInFlight = true

        var request = URLRequest(url: healthURL)
        request.timeoutInterval = 0.8
        request.cachePolicy = .reloadIgnoringLocalCacheData

        URLSession.shared.dataTask(with: request) { _, response, _ in
            let ok = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.healthCheckInFlight = false
                completion(ok)
            }
        }.resume()
    }

    @objc private func timerRefreshStatus() {
        refreshStatus(startIfNeeded: false)
    }

    private func refreshStatus(startIfNeeded: Bool) {
        guard !isStopping else { return }

        checkHealth { [weak self] reachable in
            guard let self else { return }

            if reachable {
                self.startupDecisionMade = true
                self.setStatus("Admin beží", canOpen: true, canStop: true)

                if !self.openedBrowser {
                    self.openedBrowser = true
                    self.openAdmin()
                }
                return
            }

            if let task = self.launchTask, task.isRunning {
                self.setStatus("Spúšťam Admin…", canOpen: false, canStop: true)
                return
            }

            self.launchTask = nil
            self.setStatus("Admin je zastavený", canOpen: true, canStop: false)

            if startIfNeeded && !self.startupDecisionMade {
                self.startupDecisionMade = true
                self.startAdmin()
            }
        }
    }

    private func startAdmin() {
        guard !isStopping else { return }
        if let task = launchTask, task.isRunning {
            return
        }

        setStatus("Spúšťam Admin…", canOpen: false, canStop: true)
        openedBrowser = false

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [repoPath + "/admin.command"]
        process.currentDirectoryURL = URL(fileURLWithPath: repoPath)

        let logURL = URL(fileURLWithPath: "/tmp/satellite-picons-admin.log")
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: nil)
        }

        if let handle = try? FileHandle(forWritingTo: logURL) {
            _ = try? handle.seekToEnd()
            process.standardOutput = handle
            process.standardError = handle
        }

        process.terminationHandler = { [weak self] task in
            DispatchQueue.main.async {
                guard let self else { return }
                if self.launchTask === task {
                    self.launchTask = nil
                }
                if !self.isStopping {
                    self.refreshStatus(startIfNeeded: false)
                }
            }
        }

        do {
            try process.run()
            launchTask = process
        } catch {
            launchTask = nil
            setStatus("Admin sa nespustil", canOpen: true, canStop: false)
            showError("Admin sa nepodarilo spustiť: \(error.localizedDescription)")
        }
    }

    private func readPid() -> pid_t? {
        guard let text = try? String(contentsOf: pidFile, encoding: .utf8)
            .trimmingCharacters(in: .whitespacesAndNewlines),
              let value = Int32(text),
              value > 1
        else {
            return nil
        }
        return value
    }

    private func stopAdminImmediately() {
        if let pid = readPid() {
            _ = kill(pid, SIGTERM)
        }

        if let task = launchTask, task.isRunning {
            task.terminate()
        }

        launchTask = nil
        try? FileManager.default.removeItem(at: pidFile)
        openedBrowser = false
    }

    private func stopAdminAsync(completion: (() -> Void)? = nil) {
        guard !isStopping else {
            completion?()
            return
        }

        isStopping = true
        setStatus("Zastavujem Admin…", canOpen: false, canStop: false)

        let pid = readPid()
        let task = launchTask

        DispatchQueue.global(qos: .userInitiated).async {
            if let pid {
                _ = kill(pid, SIGTERM)

                let deadline = Date().addingTimeInterval(1.2)
                while Date() < deadline && kill(pid, 0) == 0 {
                    usleep(50_000)
                }

                if kill(pid, 0) == 0 {
                    _ = kill(pid, SIGKILL)
                }
            }

            if let task, task.isRunning {
                task.terminate()
            }

            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.launchTask = nil
                try? FileManager.default.removeItem(at: self.pidFile)
                self.openedBrowser = false
                self.isStopping = false
                self.setStatus("Admin je zastavený", canOpen: true, canStop: false)
                completion?()
            }
        }
    }

    private func openAdmin() {
        NSWorkspace.shared.open(adminURL)
    }

    @objc private func openAdminAction() {
        checkHealth { [weak self] reachable in
            guard let self else { return }
            if reachable {
                self.openAdmin()
            } else {
                self.startAdmin()
            }
        }
    }

    @objc private func stopAdminAction() {
        stopAdminAsync()
    }

    @objc private func restartAdminAction() {
        stopAdminAsync { [weak self] in
            self?.startAdmin()
        }
    }

    @objc private func openLogAction() {
        let logURL = URL(fileURLWithPath: "/tmp/satellite-picons-admin.log")
        if !FileManager.default.fileExists(atPath: logURL.path) {
            FileManager.default.createFile(atPath: logURL.path, contents: Data())
        }
        NSWorkspace.shared.open(logURL)
    }

    @objc private func quitApp() {
        // Quitting must never wait on networking or on the Flask process.
        pollTimer?.invalidate()
        pollTimer = nil
        isStopping = true
        stopAdminImmediately()
        NSApp.terminate(nil)
    }

    private func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "Satellite Picons Admin"
        alert.informativeText = message
        alert.alertStyle = .critical
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

let repoPath = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : FileManager.default.currentDirectoryPath

let app = NSApplication.shared
let delegate = AppDelegate(repoPath: repoPath)
app.delegate = delegate
app.run()
