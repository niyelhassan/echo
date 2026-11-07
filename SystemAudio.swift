import Foundation
import ScreenCaptureKit
import CoreMedia

// Only audio leaves this helper. Screen frames are discarded.
final class AudioSink: NSObject, SCStreamOutput, SCStreamDelegate {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid else { return }
        var retained: CMBlockBuffer?
        var list = AudioBufferList(mNumberBuffers: 1,
                                  mBuffers: AudioBuffer(mNumberChannels: 1, mDataByteSize: 0, mData: nil))
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer, bufferListSizeNeededOut: nil, bufferListOut: &list,
            bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
            flags: 0, blockBufferOut: &retained)
        guard status == noErr, let data = list.mBuffers.mData else { return }
        FileHandle.standardOutput.write(Data(bytes: data, count: Int(list.mBuffers.mDataByteSize)))
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write(Data("System capture stopped: \(error)\n".utf8))
        exit(1)
    }
}

@main
struct Capture {
    static func main() async {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            guard let display = content.displays.first else {
                throw NSError(domain: "SystemAudio", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "No display available for system capture"])
            }
            let config = SCStreamConfiguration()
            config.capturesAudio = true
            config.excludesCurrentProcessAudio = false
            config.sampleRate = 16000
            config.channelCount = 1
            config.width = 2
            config.height = 2
            config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
            let sink = AudioSink()
            let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
            let stream = SCStream(filter: filter, configuration: config, delegate: sink)
            let queue = DispatchQueue(label: "tone-caption.audio")
            try stream.addStreamOutput(sink, type: .audio, sampleHandlerQueue: queue)
            try stream.addStreamOutput(sink, type: .screen, sampleHandlerQueue: queue)
            try await stream.startCapture()
            FileHandle.standardError.write(Data("Native system-audio capture started. Play a meeting or video.\n".utf8))
            while true { try await Task.sleep(nanoseconds: 1_000_000_000) }
        } catch {
            FileHandle.standardError.write(Data("Cannot capture system audio: \(error)\nAllow this app in System Settings > Privacy & Security > Screen & System Audio Recording, then retry.\n".utf8))
            exit(1)
        }
    }
}
