// Isolated synthetic-only experiment. Never changes the system audio defaults,
// records files, includes a microphone, or taps any process except its own child.
// Source: developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps
import Foundation
import CoreAudio
import AVFoundation

func check(_ status: OSStatus, _ operation: String) throws {
    if status != noErr { throw NSError(domain: operation, code: Int(status)) }
}
func address(_ selector: AudioObjectPropertySelector, _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
}
func uintProperty(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) throws -> UInt32 {
    var a = address(selector), size = UInt32(MemoryLayout<UInt32>.size), value: UInt32 = 0
    try check(AudioObjectGetPropertyData(object, &a, 0, nil, &size, &value), "uint property")
    return value
}
func stringProperty(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) throws -> String {
    var a = address(selector), size = UInt32(MemoryLayout<CFString>.size)
    var value: CFString = "" as CFString
    try check(withUnsafeMutablePointer(to: &value) {
        AudioObjectGetPropertyData(object, &a, 0, nil, &size, $0)
    }, "string property")
    return value as String
}
func objects(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) throws -> [AudioObjectID] {
    var a = address(selector), size: UInt32 = 0
    try check(AudioObjectGetPropertyDataSize(object, &a, 0, nil, &size), "object size")
    var result = [AudioObjectID](repeating: 0, count: Int(size)/MemoryLayout<AudioObjectID>.size)
    try check(result.withUnsafeMutableBytes { AudioObjectGetPropertyData(object, &a, 0, nil, &size, $0.baseAddress!) }, "objects")
    return result
}
func channels(_ object: AudioObjectID, _ scope: AudioObjectPropertyScope) throws -> UInt32 {
    var a = address(kAudioDevicePropertyStreamConfiguration, scope), size: UInt32 = 0
    try check(AudioObjectGetPropertyDataSize(object, &a, 0, nil, &size), "channel size")
    let storage = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: 16)
    defer { storage.deallocate() }
    try check(AudioObjectGetPropertyData(object, &a, 0, nil, &size, storage), "channels")
    return UnsafeMutableAudioBufferListPointer(storage.assumingMemoryBound(to: AudioBufferList.self)).reduce(0) { $0 + $1.mNumberChannels }
}
func defaults() throws -> [UInt32] {
    try [kAudioHardwarePropertyDefaultInputDevice, kAudioHardwarePropertyDefaultOutputDevice,
         kAudioHardwarePropertyDefaultSystemOutputDevice].map { try uintProperty(AudioObjectID(kAudioObjectSystemObject), $0) }
}
func emit(_ value: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!); fflush(stdout)
}
func runLoop(_ seconds: Double) { RunLoop.current.run(until: Date().addingTimeInterval(seconds)) }

func tone(_ signal: String) throws {
    let engine = AVAudioEngine()
    let format = engine.outputNode.inputFormat(forBus: 0)
    var phase = 0.0, active = false
    let source = AVAudioSourceNode { _, _, count, list -> OSStatus in
        let buffers = UnsafeMutableAudioBufferListPointer(list)
        for frame in 0..<Int(count) {
            let sample: Float = active ? Float(sin(phase) * 0.004) : 0
            phase += 2 * Double.pi * 997 / format.sampleRate
            if phase > 2 * Double.pi { phase -= 2 * Double.pi }
            for buffer in buffers {
                guard let data = buffer.mData?.assumingMemoryBound(to: Float.self) else { continue }
                for channel in 0..<Int(buffer.mNumberChannels) { data[frame * Int(buffer.mNumberChannels) + channel] = sample }
            }
        }
        return noErr
    }
    engine.attach(source); engine.connect(source, to: engine.mainMixerNode, format: format)
    try engine.start(); defer { engine.stop() }
    let deadline = Date().addingTimeInterval(55)
    while Date() < deadline {
        active = FileManager.default.fileExists(atPath: signal)
        runLoop(0.05)
    }
}

func readInput(_ uid: String, _ ready: String) throws {
    // HAL object IDs belong to each client. Resolve the public UID afresh in
    // the independent reader instead of passing the creator's object ID.
    let available = try objects(AudioObjectID(kAudioObjectSystemObject), kAudioHardwarePropertyDevices)
    guard let device = try available.first(where: { try stringProperty($0, kAudioDevicePropertyDeviceUID) == uid }) else {
        throw NSError(domain: "Public aggregate invisible to separate reader", code: 1)
    }
    // The only input must be the stereo process tap. Physical microphone input
    // is forbidden even if a future configuration accidentally includes one.
    guard try channels(device, kAudioObjectPropertyScopeInput) == 2 else {
        throw NSError(domain: "Expected exactly two synthetic tap channels", code: 1)
    }
    var a = address(kAudioDevicePropertyStreamFormat, kAudioObjectPropertyScopeInput)
    var format = AudioStreamBasicDescription(), size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
    try check(AudioObjectGetPropertyData(device, &a, 0, nil, &size, &format), "input format")
    guard format.mFormatID == kAudioFormatLinearPCM && format.mBitsPerChannel == 32 && format.mFormatFlags & kAudioFormatFlagIsFloat != 0 else {
        throw NSError(domain: "Expected Float32 PCM", code: 1)
    }
    var io: AudioDeviceIOProcID?, sum = 0.0, count = 0, crossings = 0, previous: Float = 0, peak: Float = 0
    try check(AudioDeviceCreateIOProcIDWithBlock(&io, device, nil) { _, input, _, output, _ in
        // Never feed captured input back to an output.
        for b in UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: output)) {
            if let data = b.mData { memset(data, 0, Int(b.mDataByteSize)) }
        }
        let buffers = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: input))
        guard let b = buffers.first, let data = b.mData?.assumingMemoryBound(to: Float.self), b.mNumberChannels > 0 else { return }
        let stride = Int(b.mNumberChannels)
        for n in Swift.stride(from: 0, to: Int(b.mDataByteSize)/4, by: stride) {
            let value = data[n]
            sum += Double(value * value); count += 1; peak = max(peak, abs(value))
            if previous <= 0 && value > 0 { crossings += 1 }; previous = value
        }
    }, "create reader")
    defer { if let io { AudioDeviceDestroyIOProcID(device, io) } }
    try check(AudioDeviceStart(device, io), "start reader")
    defer { AudioDeviceStop(device, io) }
    try Data().write(to: URL(fileURLWithPath: ready))
    runLoop(6)
    let rms = count > 0 ? sqrt(sum/Double(count)) : 0
    emit(["reader_pid": getpid(), "frames": count, "rms": rms, "peak": peak,
          "sample_rate": format.mSampleRate, "positive_crossings": crossings,
          "synthetic_signal_detected": rms > 0.001 && crossings > 4000])
}

func coordinator(_ folder: String) throws {
    let before = try defaults()
    let system = AudioObjectID(kAudioObjectSystemObject)
    // Use a speaker-only subdevice: never include physical input channels.
    let devices = try objects(system, kAudioHardwarePropertyDevices)
    guard let speaker = try devices.first(where: {
        try channels($0, kAudioObjectPropertyScopeInput) == 0 && channels($0, kAudioObjectPropertyScopeOutput) >= 2
    }) else { throw NSError(domain: "No speaker-only output device", code: 1) }
    let outputUID = try stringProperty(speaker, kAudioDevicePropertyDeviceUID)
    let signal = folder + "/tone-start", ready = folder + "/reader-ready"
    for path in [signal, ready] { try? FileManager.default.removeItem(atPath: path) }
    let child = Process(); child.executableURL = URL(fileURLWithPath: CommandLine.arguments[0]); child.arguments = ["--tone", signal]
    try child.run()
    defer { if child.isRunning { child.terminate() }; child.waitUntilExit() }
    var pid = child.processIdentifier, process: AudioObjectID = 0
    for _ in 0..<50 {
        var a = address(kAudioHardwarePropertyTranslatePIDToProcessObject), size = UInt32(MemoryLayout<AudioObjectID>.size)
        try check(AudioObjectGetPropertyData(system, &a, UInt32(MemoryLayout<pid_t>.size), &pid, &size, &process), "tone process")
        if process != 0 { break }; runLoop(0.05)
    }
    guard process != 0 else { throw NSError(domain: "Tone audio process missing", code: 1) }
    let description = CATapDescription(stereoMixdownOfProcesses: [process])
    description.name = "Trendi synthetic tone only"; description.isPrivate = false
    description.muteBehavior = .mutedWhenTapped
    var tap: AudioObjectID = 0
    try check(AudioHardwareCreateProcessTap(description, &tap), "create synthetic tap")
    defer { emit(["tap_destroy_status": AudioHardwareDestroyProcessTap(tap)]) }
    let uid = "local.trendi.synthetic-probe." + UUID().uuidString
    let config: [String: Any] = [kAudioAggregateDeviceNameKey: "Trendi Synthetic Probe Input",
        kAudioAggregateDeviceUIDKey: uid, kAudioAggregateDeviceIsPrivateKey: 0,
        kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputUID]],
        kAudioAggregateDeviceMainSubDeviceKey: outputUID,
        kAudioAggregateDeviceTapListKey: [[kAudioSubTapUIDKey: description.uuid.uuidString, kAudioSubTapDriftCompensationKey: 1]]]
    // TapAutoStart is intentionally absent: Apple restricts it to private devices.
    var aggregate: AudioObjectID = 0
    try check(AudioHardwareCreateAggregateDevice(config as CFDictionary, &aggregate), "create public input")
    defer {
        emit(["aggregate_destroy_status": AudioHardwareDestroyAggregateDevice(aggregate),
              "defaults_preserved": (try? defaults()) == before])
    }
    emit(["public_aggregate": aggregate, "tone_pid": pid, "coordinator_pid": getpid(),
          "physical_input_channels": try channels(speaker, kAudioObjectPropertyScopeInput),
          "aggregate_input_channels": try channels(aggregate, kAudioObjectPropertyScopeInput)])
    let reader = Process(); reader.executableURL = child.executableURL; reader.arguments = ["--read", uid, ready]
    try reader.run()
    defer { if reader.isRunning { reader.terminate() }; reader.waitUntilExit() }
    let deadline = Date().addingTimeInterval(45)
    while Date() < deadline && reader.isRunning {
        if FileManager.default.fileExists(atPath: ready) { break }; runLoop(0.05)
    }
    guard FileManager.default.fileExists(atPath: ready) else { throw NSError(domain: "Reader permission or startup blocked", code: 1) }
    try Data().write(to: URL(fileURLWithPath: signal))
    while reader.isRunning && Date() < deadline { runLoop(0.1) }
    try? FileManager.default.removeItem(atPath: signal)
    guard !reader.isRunning && reader.terminationStatus == 0 else { throw NSError(domain: "Reader did not finish", code: 1) }
}

do {
    switch CommandLine.arguments.dropFirst().first {
    case "--tone": try tone(CommandLine.arguments[2])
    case "--read": try readInput(CommandLine.arguments[2], CommandLine.arguments[3])
    case "--probe": try coordinator(CommandLine.arguments[2])
    default: throw NSError(domain: "Use --probe with an existing private temporary directory", code: 1)
    }
} catch { emit(["error": String(describing: error)]); exit(1) }
