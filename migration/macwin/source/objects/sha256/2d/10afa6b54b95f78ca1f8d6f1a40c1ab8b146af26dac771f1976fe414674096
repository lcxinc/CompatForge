import CoreGraphics
import Darwin
import Foundation
import ImageIO
import UniformTypeIdentifiers

guard CommandLine.arguments.count == 3,
      let windowID = UInt32(CommandLine.arguments[1]) else {
    fputs("usage: capture-macos-window <window-id> <output.png>\n", stderr)
    exit(2)
}

let framework = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
guard let handle = dlopen(framework, RTLD_LAZY),
      let symbol = dlsym(handle, "CGWindowListCreateImage") else {
    fputs("CGWindowListCreateImage is unavailable\n", stderr)
    exit(1)
}

typealias CaptureFunction = @convention(c) (
    CGRect,
    UInt32,
    UInt32,
    UInt32
) -> Unmanaged<CGImage>?

let capture = unsafeBitCast(symbol, to: CaptureFunction.self)
let optionIncludingWindow = UInt32(1 << 3)
let boundsIgnoreFraming = UInt32(1 << 0)
let bestResolution = UInt32(1 << 3)

guard let unmanagedImage = capture(
    .null,
    optionIncludingWindow,
    windowID,
    boundsIgnoreFraming | bestResolution
) else {
    fputs("could not capture window \(windowID)\n", stderr)
    exit(1)
}

let image = unmanagedImage.takeRetainedValue()
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
guard let destination = CGImageDestinationCreateWithURL(
    outputURL as CFURL,
    UTType.png.identifier as CFString,
    1,
    nil
) else {
    exit(1)
}
CGImageDestinationAddImage(destination, image, nil)
guard CGImageDestinationFinalize(destination) else { exit(1) }
print("captured \(image.width)x\(image.height)")
