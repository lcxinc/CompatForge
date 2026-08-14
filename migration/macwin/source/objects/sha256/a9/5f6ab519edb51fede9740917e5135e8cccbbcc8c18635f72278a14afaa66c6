import CoreGraphics
import Foundation

guard let session = CGSessionCopyCurrentDictionary() as? [String: Any] else {
    print("unknown")
    exit(1)
}

let lockedValue = session["CGSSessionScreenIsLocked"]
if (lockedValue as? Bool) == true || (lockedValue as? NSNumber)?.boolValue == true {
    print("locked")
} else {
    print("unlocked")
}
