import CoreGraphics
import Darwin
import Foundation
import ImageIO
import UniformTypeIdentifiers

guard CommandLine.arguments.count == 6,
      let x = Double(CommandLine.arguments[1]),
      let y = Double(CommandLine.arguments[2]),
      let width = Double(CommandLine.arguments[3]),
      let height = Double(CommandLine.arguments[4]),
      width > 0,
      height > 0 else {
    fputs("usage: capture-macos-region <x> <y> <width> <height> <output.png>\n", stderr)
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
let optionOnScreenOnly = UInt32(1 << 0)
let boundsIgnoreFraming = UInt32(1 << 0)
let bestResolution = UInt32(1 << 3)
let rect = CGRect(x: x, y: y, width: width, height: height)

guard let unmanagedImage = capture(
    rect,
    optionOnScreenOnly,
    0,
    boundsIgnoreFraming | bestResolution
) else {
    fputs("could not capture screen region \(rect)\n", stderr)
    exit(1)
}

let image = unmanagedImage.takeRetainedValue()
let outputURL = URL(fileURLWithPath: CommandLine.arguments[5])
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
