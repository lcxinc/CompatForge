import CoreGraphics
import Foundation

let discoveryMode = (CommandLine.arguments.count == 4 || CommandLine.arguments.count == 5)
    && (CommandLine.arguments[1] == "--discover"
        || CommandLine.arguments[1] == "--discover-smallest")
let preferSmallest = discoveryMode && CommandLine.arguments[1] == "--discover-smallest"
guard discoveryMode || CommandLine.arguments.count == 8 else {
    fputs("usage: find-macos-window <owner> <title> <x> <y> <width> <height> <tolerance>\n", stderr)
    fputs("       find-macos-window --discover <owner> <title-token> [owner-pid]\n", stderr)
    fputs("       find-macos-window --discover-smallest <owner> <title-token> [owner-pid]\n", stderr)
    exit(2)
}

let expectedOwner = CommandLine.arguments[discoveryMode ? 2 : 1].lowercased()
let expectedTitle = CommandLine.arguments[discoveryMode ? 3 : 2]
let expectedPid = discoveryMode && CommandLine.arguments.count == 5
    ? Int(CommandLine.arguments[4])
    : nil
let expectedValues = discoveryMode ? [] : CommandLine.arguments[3...6].compactMap(Double.init)
let tolerance = discoveryMode ? 0 : (Double(CommandLine.arguments[7]) ?? 12)
guard discoveryMode || expectedValues.count == 4 else { exit(2) }
let expected = discoveryMode ? .zero : CGRect(
    x: expectedValues[0],
    y: expectedValues[1],
    width: expectedValues[2],
    height: expectedValues[3]
)

let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    exit(1)
}

struct Candidate {
    let id: CGWindowID
    let owner: String
    let title: String
    let bounds: CGRect
    let score: Double
}

let candidates = windows.compactMap { window -> Candidate? in
    guard let number = window[kCGWindowNumber as String] as? NSNumber,
          let owner = window[kCGWindowOwnerName as String] as? String,
          let boundsValue = window[kCGWindowBounds as String] else {
        return nil
    }
    let boundsDictionary = boundsValue as! CFDictionary
    guard let bounds = CGRect(dictionaryRepresentation: boundsDictionary) else { return nil }
    let title = window[kCGWindowName as String] as? String ?? ""
    let ownerMatches = owner.lowercased() == expectedOwner
        || (expectedOwner.contains("wine") && owner.lowercased().contains("wine"))
    guard ownerMatches else { return nil }
    if let expectedPid = expectedPid {
        guard let ownerPid = window[kCGWindowOwnerPID as String] as? NSNumber,
              ownerPid.intValue == expectedPid else {
            return nil
        }
    }
    if !expectedTitle.isEmpty {
        if discoveryMode && !title.localizedCaseInsensitiveContains(expectedTitle) { return nil }
        if !discoveryMode && title != expectedTitle { return nil }
    }

    let delta: Double
    if discoveryMode {
        guard bounds.width > 80, bounds.height > 80 else { return nil }
        let area = bounds.width * bounds.height
        delta = preferSmallest ? area : -area
    } else {
        delta = abs(bounds.minX - expected.minX)
            + abs(bounds.minY - expected.minY)
            + abs(bounds.width - expected.width)
            + abs(bounds.height - expected.height)
        guard delta <= tolerance * 4 else { return nil }
    }
    return Candidate(
        id: CGWindowID(number.uint32Value),
        owner: owner,
        title: title,
        bounds: bounds,
        score: delta
    )
}

guard let match = candidates.min(by: { $0.score < $1.score }) else { exit(1) }
print("\(match.id)\t\(match.owner)\t\(match.title)\t\(Int(match.bounds.minX))\t\(Int(match.bounds.minY))\t\(Int(match.bounds.width))\t\(Int(match.bounds.height))")
