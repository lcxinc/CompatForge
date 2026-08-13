import Foundation

public struct MacWinPaths: Sendable {
    public var root: URL

    public init(root: URL = MacWinPaths.defaultRoot()) {
        self.root = root
    }

    public static func defaultRoot() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return appSupport.appendingPathComponent("MacWin", isDirectory: true)
    }

    public var enginesDirectory: URL { root.appendingPathComponent("Engines", isDirectory: true) }
    public var bottlesDirectory: URL { root.appendingPathComponent("Bottles", isDirectory: true) }
    public var catalogDirectory: URL { root.appendingPathComponent("Catalog", isDirectory: true) }
    public var logsDirectory: URL { root.appendingPathComponent("Logs", isDirectory: true) }
    public var downloadsDirectory: URL { root.appendingPathComponent("Downloads", isDirectory: true) }
    public var iconCacheDirectory: URL { root.appendingPathComponent("IconCache", isDirectory: true) }
    public var externalOpenQueueDirectory: URL { root.appendingPathComponent("ExternalOpenQueue", isDirectory: true) }
    public var nativeUIProbeDirectory: URL { root.appendingPathComponent("NativeUIProbe", isDirectory: true) }

    public func engineDirectory(id: String) -> URL {
        enginesDirectory.appendingPathComponent(id, isDirectory: true)
    }

    public func engineManifestURL(id: String) -> URL {
        engineDirectory(id: id).appendingPathComponent("manifest.json")
    }

    public func bottleDirectory(id: String) -> URL {
        bottlesDirectory.appendingPathComponent(id, isDirectory: true)
    }

    public func bottleManifestURL(id: String) -> URL {
        bottleDirectory(id: id).appendingPathComponent("manifest.json")
    }

    public func bottleDriveCURL(id: String) -> URL {
        bottleDirectory(id: id).appendingPathComponent("drive_c", isDirectory: true)
    }

    public func ensureBaseDirectories(fileManager: FileManager = .default) throws {
        for url in [root, enginesDirectory, bottlesDirectory, catalogDirectory, logsDirectory, downloadsDirectory, iconCacheDirectory, externalOpenQueueDirectory, nativeUIProbeDirectory] {
            try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
        }
    }
}
