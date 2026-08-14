import Foundation

public struct JSONStore {
    public var encoder: JSONEncoder
    public var decoder: JSONDecoder
    public var fileManager: FileManager

    public init(fileManager: FileManager = .default) {
        self.fileManager = fileManager
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        self.encoder = encoder

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    public func load<T: Decodable>(_ type: T.Type, from url: URL) throws -> T {
        let data = try Data(contentsOf: url)
        return try decoder.decode(T.self, from: data)
    }

    public func save<T: Encodable>(_ value: T, to url: URL) throws {
        try fileManager.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let data = try encoder.encode(value)
        let tempURL = url.deletingLastPathComponent().appendingPathComponent(".\(url.lastPathComponent).tmp-\(UUID().uuidString)")
        try data.write(to: tempURL, options: [.atomic])
        if fileManager.fileExists(atPath: url.path) {
            try fileManager.removeItem(at: url)
        }
        try fileManager.moveItem(at: tempURL, to: url)
    }

    public func loadMany<T: Decodable>(_ type: T.Type, in directory: URL, fileName: String) throws -> [T] {
        guard fileManager.fileExists(atPath: directory.path) else { return [] }
        let contents = try fileManager.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.isDirectoryKey])
        var values: [T] = []
        for item in contents {
            let manifestURL = item.appendingPathComponent(fileName)
            if fileManager.fileExists(atPath: manifestURL.path) {
                values.append(try load(T.self, from: manifestURL))
            }
        }
        return values
    }
}
