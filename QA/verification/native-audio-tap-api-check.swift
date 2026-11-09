import Foundation
import CoreAudio

// Compile-only API sketch. No top-level audio calls; never executed.
@available(macOS 14.2, *)
func apiSketch(grokAudioProcess: AudioObjectID, outputDeviceUID: String) throws -> (AudioObjectID, AudioObjectID) {
    let tap = CATapDescription(stereoMixdownOfProcesses: [grokAudioProcess])
    tap.name = "Trendi generated speech tap"
    tap.isPrivate = false
    tap.muteBehavior = .mutedWhenTapped
    var tapID = AudioObjectID(kAudioObjectUnknown)
    guard AudioHardwareCreateProcessTap(tap, &tapID) == noErr else { throw NSError(domain: "TapCreation", code: 1) }
    let config: [String: Any] = [
        kAudioAggregateDeviceNameKey: "Trendi Generated Speech Input",
        kAudioAggregateDeviceUIDKey: "local.trendi.probe.\(UUID().uuidString)",
        kAudioAggregateDeviceIsPrivateKey: 0,
        kAudioAggregateDeviceSubDeviceListKey: [[kAudioSubDeviceUIDKey: outputDeviceUID]],
        kAudioAggregateDeviceMainSubDeviceKey: outputDeviceUID,
        kAudioAggregateDeviceTapListKey: [[kAudioSubTapUIDKey: tap.uuid.uuidString,
                                          kAudioSubTapDriftCompensationKey: 1]]
        // No TapAutoStart: Apple requires a PRIVATE aggregate for that key.
    ]
    var aggregateID = AudioObjectID(kAudioObjectUnknown)
    guard AudioHardwareCreateAggregateDevice(config as CFDictionary, &aggregateID) == noErr else {
        AudioHardwareDestroyProcessTap(tapID)
        throw NSError(domain: "AggregateCreation", code: 2)
    }
    return (tapID, aggregateID)
}
