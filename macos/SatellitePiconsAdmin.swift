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
    private var statusMenuItem: NSMenuItem!
    private var pollTimer: Timer?
    private var launchTask: Process?
    private var openedBrowser = false

    init(repoPath: String) {
        self.repoPath = repoPath
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        setupMenuBar()
        refreshStatus()

        if !isAdminReachable() {
            startAdmin()
        } else {
            openAdmin()
        }

        pollTimer = Timer.scheduledTimer(
            timeInterval: 1.0,
            target: self,
            selector: #selector(refreshStatus),
            userInfo: nil,
            repeats: true
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        stopAdmin(wait: false)
    }

    private func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "tv", accessibilityDescription: "Satellite Picons Admin")
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

        stopItem = NSMenuItem(
            title: "Zastaviť Admin",
            action: #selector(stopAdminAction),
            keyEquivalent: ""
        )
        stopItem.target = self
        menu.addItem(stopItem)

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

    private func isAdminReachable() -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/curl")
        process.arguments = [
            "-fsS",
            "--connect-timeout", "1",
            "--max-time", "1",
            healthURL.absoluteString,
        ]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus == 0
        } catch {
            return false
        }
    }

    private func startAdmin() {
        statusMenuItem.title = "Spúšťam Admin…"
        stopItem.isEnabled = true
        openedBrowser = false

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [repoPath + "/admin.command"]
        process.currentDirectoryURL = URL(fileURLWithPath: repoPath)

        let logURL = URL(fileURLWithPath: "/tmp/satellite-picons-admin.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        if let handle = try? FileHandle(forWritingTo: logURL) {
            _ = try? handle.seekToEnd()
            process.standardOutput = handle
            process.standardError = handle
        }

        do {
            try process.run()
            launchTask = process
        } catch {
            showError("Admin sa nepodarilo spustiť: \(error.localizedDescription)")
        }
    }

    @objc private func refreshStatus() {
        let reachable = isAdminReachable()

        if reachable {
            statusMenuItem.title = "Admin beží"
            openItem.isEnabled = true
            stopItem.isEnabled = true

            if !openedBrowser {
                openedBrowser = true
                openAdmin()
            }
        } else if let task = launchTask, task.isRunning {
            statusMenuItem.title = "Spúšťam Admin…"
            openItem.isEnabled = false
            stopItem.isEnabled = true
        } else {
            launchTask = nil
            statusMenuItem.title = "Admin je zastavený"
            openItem.isEnabled = true
            stopItem.isEnabled = false
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

    private func stopAdmin(wait: Bool = true) {
        if let pid = readPid() {
            kill(pid, SIGTERM)

            if wait {
                let deadline = Date().addingTimeInterval(2.5)
                while Date() < deadline {
                    if kill(pid, 0) != 0 {
                        break
                    }
                    RunLoop.current.run(until: Date().addingTimeInterval(0.05))
                }

                if kill(pid, 0) == 0 {
                    kill(pid, SIGKILL)
                }
            }
        }

        if let task = launchTask, task.isRunning {
            task.terminate()
        }
        launchTask = nil

        try? FileManager.default.removeItem(at: pidFile)
        openedBrowser = false
    }

    private func openAdmin() {
        NSWorkspace.shared.open(adminURL)
    }

    @objc private func openAdminAction() {
        if isAdminReachable() {
            openAdmin()
        } else {
            startAdmin()
        }
    }

    @objc private func stopAdminAction() {
        stopAdmin()
        refreshStatus()
    }

    @objc private func quitApp() {
        stopAdmin()
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
