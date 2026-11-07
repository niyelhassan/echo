import AppKit
import AVKit

final class Demo: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    let player = AVPlayer()
    let captions = NSTextView()
    let status = NSTextField(labelWithString: "Preparing local transcription…")
    let toneLabel = NSTextField(labelWithString: "Tone: waiting for speech…")
    let toneScores = NSTextField(labelWithString: "Happy —   Sad —   Angry —   Neutral —")
    var worker = Process()
    let replay = NSButton(title: "Replay demo", target: nil, action: nil)
    var buffer = Data()
    var boundaryObserver: Any?
    var clockObserver: Any?
    var clockInput: FileHandle?
    var playing = false
    var latestToneSegment = -1
    var rows: [Int: [String: Any]] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard window == nil else { return }
        let video = URL(fileURLWithPath: CommandLine.arguments[2])
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1000, height: 850),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Tone Caption — Live Emotion Demo"
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.spacing = 12
        stack.edgeInsets = NSEdgeInsets(top: 16, left: 20, bottom: 16, right: 20)
        stack.translatesAutoresizingMaskIntoConstraints = false
        window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor),
            stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor),
            stack.bottomAnchor.constraint(equalTo: window.contentView!.bottomAnchor)
        ])
        let title = NSTextField(labelWithString: "Expressive speech · live captions + vocal tone")
        title.font = .boldSystemFont(ofSize: 22)
        stack.addArrangedSubview(title)
        let view = AVPlayerView()
        view.player = player
        view.controlsStyle = .none
        stack.addArrangedSubview(view)
        view.heightAnchor.constraint(equalToConstant: 400).isActive = true
        view.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40).isActive = true
        let note = NSTextField(labelWithString: "Source: CREMA-D actors • local audio analysis • sarcasm not evaluated")
        note.textColor = .secondaryLabelColor
        stack.addArrangedSubview(note)
        toneLabel.font = .boldSystemFont(ofSize: 28)
        stack.addArrangedSubview(toneLabel)
        toneScores.font = .monospacedDigitSystemFont(ofSize: 15, weight: .medium)
        stack.addArrangedSubview(toneScores)
        let disclaimer = NSTextField(labelWithString: "Early estimates update as you listen. Scores are not certainty. Sarcasm is not evaluated.")
        disclaimer.textColor = .secondaryLabelColor
        stack.addArrangedSubview(disclaimer)
        replay.target = self
        replay.action = #selector(restartDemo)
        replay.isEnabled = false
        stack.addArrangedSubview(replay)
        stack.addArrangedSubview(status)
        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        captions.isEditable = false
        captions.font = .systemFont(ofSize: 19)
        captions.autoresizingMask = [.width]
        captions.textContainer?.widthTracksTextView = true
        scroll.documentView = captions
        stack.addArrangedSubview(scroll)
        scroll.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -40).isActive = true
        scroll.heightAnchor.constraint(greaterThanOrEqualToConstant: 160).isActive = true
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        player.replaceCurrentItem(with: AVPlayerItem(url: video))
        clockObserver = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 0.05, preferredTimescale: 600), queue: .main) { time in
            if self.playing { self.send(["playback": time.seconds]) }
        }
        NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: player.currentItem, queue: .main) { _ in
            self.send(["playback": self.player.currentItem?.duration.seconds ?? 60])
        }
        NotificationCenter.default.addObserver(forName: .AVPlayerItemPlaybackStalled, object: player.currentItem, queue: .main) { _ in
            FileHandle.standardError.write(Data("PLAYBACK_STALLED\n".utf8))
        }
        launchWorker()
        // Stop playback at the same one-minute maximum used by the worker.
        boundaryObserver = player.addBoundaryTimeObserver(forTimes: [NSValue(time: CMTime(seconds: 60, preferredTimescale: 600))], queue: .main) {
            self.player.pause()
        }
    }

    func launchWorker() {
        let root = URL(fileURLWithPath: CommandLine.arguments[1])
        let video = URL(fileURLWithPath: CommandLine.arguments[2])
        worker = Process()
        worker.executableURL = root.appendingPathComponent(".venv/bin/python")
        worker.arguments = [root.appendingPathComponent("video_demo.py").path, video.path, "--clock-stdin"]
        let segments = video.deletingLastPathComponent().appendingPathComponent("segments.json")
        if video.lastPathComponent == "expressive-speech.mp4" && FileManager.default.fileExists(atPath: segments.path) {
            worker.arguments! += ["--segments", segments.path]
        }
        worker.currentDirectoryURL = root
        let input = Pipe()
        worker.standardInput = input
        clockInput = input.fileHandleForWriting
        let pipe = Pipe()
        worker.standardOutput = pipe
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async { self.receive(data) }
        }
        do { try worker.run() }
        catch { status.stringValue = "Cannot start transcription: \(error.localizedDescription)" }
    }

    @objc func restartDemo() {
        replay.isEnabled = false
        playing = false
        captions.string = ""
        buffer.removeAll()
        rows.removeAll()
        latestToneSegment = -1
        toneLabel.stringValue = "Tone: waiting for speech…"
        toneLabel.textColor = .secondaryLabelColor
        toneScores.stringValue = "Happy —   Sad —   Angry —   Neutral —"
        player.seek(to: .zero, toleranceBefore: .zero, toleranceAfter: .zero) { _ in
            DispatchQueue.main.async {
                if self.worker.isRunning { self.send(["reset": true]) }
                else { self.launchWorker() }
            }
        }
    }

    func send(_ message: [String: Any]) {
        guard worker.isRunning, let data = try? JSONSerialization.data(withJSONObject: message) else { return }
        try? clockInput?.write(contentsOf: data + Data([10]))
    }

    func renderCaptions() {
        captions.string = rows.keys.sorted().compactMap { index in
            guard let row = rows[index], let text = row["text"] as? String, !text.isEmpty else { return nil }
            let seconds = row["start"] as? Double ?? 0
            let label = (row["tone"] as? [String: Any])?["label"] as? String ?? "Analyzing tone…"
            let partial = row["textFinal"] as? Bool == true ? "" : " …"
            return String(format: "[%02d:%02d]  ", Int(seconds)/60, Int(seconds)%60) + "[\(label)] " + text + partial
        }.joined(separator: "\n\n")
        captions.scrollToEndOfDocument(nil)
    }

    func receive(_ data: Data) {
        buffer.append(data)
        while let end = buffer.firstIndex(of: 10) {
            let line = buffer.subdata(in: 0..<end)
            buffer.removeSubrange(0...end)
            guard let event = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else { continue }
            if event["ready"] as? Bool == true {
                playing = true
                player.play()
                status.stringValue = "Live — listening to the video locally…"
            }
            let index = event["segment"] as? Int ?? -1
            if index >= 0 {
                rows[index, default: [:]]["start"] = event["start"]
                if let tone = event["tone"] { rows[index, default: [:]]["tone"] = tone }
                if let text = event["text"] {
                    rows[index, default: [:]]["text"] = text
                    rows[index, default: [:]]["textFinal"] = event["final"]
                }
                renderCaptions()
            }
            if let tone = event["tone"] as? [String: Any], index >= latestToneSegment {
                latestToneSegment = index
                let label = tone["label"] as? String ?? "Uncertain"
                let seconds = event["start"] as? Double ?? 0
                let end = event["end"] as? Double ?? seconds+5
                let phase = event["provisional"] as? Bool == true ? "Early tone" : "Tone"
                toneLabel.stringValue = String(format: "\(phase) [%.1f–%.1fs]: ", seconds, end) + label
                let colors: [String: NSColor] = ["Happy": .systemGreen, "Sad": .systemBlue,
                                               "Angry": .systemOrange, "Neutral": .secondaryLabelColor]
                toneLabel.textColor = label.hasPrefix("Possibly") ? (colors[tone["leading"] as? String ?? ""] ?? .labelColor) : .secondaryLabelColor
                let scores = tone["scores"] as? [String: Double] ?? [:]
                toneScores.stringValue = scores.sorted { $0.value > $1.value }.prefix(4).map {
                    "\($0.key) " + String(format: "%.0f%%", $0.value*100)
                }.joined(separator: "     ")
                FileHandle.standardError.write(Data("Tone received: \(label) \(scores)\n".utf8))
            }
            if let text = event["text"] as? String {
                FileHandle.standardError.write(Data("Caption received: \(text)\n".utf8))
            }
            if let delay = event["latency_seconds"] as? Double {
                status.stringValue = String(format: "Live · latest processing delay %.0f ms · captions and tone update independently", delay*1000)
                FileHandle.standardError.write(Data("Latency: \(delay) final=\(event["final"] ?? false)\n".utf8))
            }
            if let message = event["status"] as? String { status.stringValue = message }
            if event["done"] as? Bool == true { playing = false; player.pause(); replay.isEnabled = true }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        player.pause()
        if worker.isRunning { worker.terminate() }
    }
}

let app = NSApplication.shared
let delegate = Demo()
app.delegate = delegate
app.setActivationPolicy(.regular)
delegate.applicationDidFinishLaunching(Notification(name: NSApplication.didFinishLaunchingNotification))
app.run()
