import Foundation

public enum WineArch: String, Codable, CaseIterable, Sendable {
    case win32
    case win64
}

public enum WindowsExecutableArchitecture: String, Codable, CaseIterable, Sendable {
    case i386
    case x86_64
    case arm64
    case unknown

    public var is32Bit: Bool {
        self == .i386
    }
}

public enum CompatibilityRating: String, Codable, CaseIterable, Sendable {
    case excellent
    case good
    case limited
    case experimental
    case unknown

    public var displayName: String {
        switch self {
        case .excellent: "Excellent"
        case .good: "Good"
        case .limited: "Limited"
        case .experimental: "Experimental"
        case .unknown: "Unknown"
        }
    }
}

public enum InstallTaskState: String, Codable, CaseIterable, Sendable {
    case queued
    case running
    case launched
    case succeeded
    case failed
    case cancelled
}

public struct HealthCheck: Codable, Equatable, Sendable {
    public var id: String
    public var name: String
    public var command: [String]

    public init(id: String, name: String, command: [String]) {
        self.id = id
        self.name = name
        self.command = command
    }
}

public struct EngineManifest: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var name: String
    public var wineVersion: String
    public var arch: WineArch
    public var supportsWin32: Bool
    public var winePath: String
    public var wineserverPath: String
    public var runtimePath: String
    public var defaultEnv: [String: String]
    public var healthChecks: [HealthCheck]

    public init(
        id: String,
        name: String,
        wineVersion: String,
        arch: WineArch,
        supportsWin32: Bool = false,
        winePath: String,
        wineserverPath: String,
        runtimePath: String,
        defaultEnv: [String: String],
        healthChecks: [HealthCheck] = []
    ) {
        self.id = id
        self.name = name
        self.wineVersion = wineVersion
        self.arch = arch
        self.supportsWin32 = supportsWin32
        self.winePath = winePath
        self.wineserverPath = wineserverPath
        self.runtimePath = runtimePath
        self.defaultEnv = defaultEnv
        self.healthChecks = healthChecks
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case wineVersion
        case arch
        case supportsWin32
        case winePath
        case wineserverPath
        case runtimePath
        case defaultEnv
        case healthChecks
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(String.self, forKey: .id)
        self.name = try container.decode(String.self, forKey: .name)
        self.wineVersion = try container.decode(String.self, forKey: .wineVersion)
        self.arch = try container.decode(WineArch.self, forKey: .arch)
        self.supportsWin32 = try container.decodeIfPresent(Bool.self, forKey: .supportsWin32) ?? false
        self.winePath = try container.decode(String.self, forKey: .winePath)
        self.wineserverPath = try container.decode(String.self, forKey: .wineserverPath)
        self.runtimePath = try container.decode(String.self, forKey: .runtimePath)
        self.defaultEnv = try container.decode([String: String].self, forKey: .defaultEnv)
        self.healthChecks = try container.decodeIfPresent([HealthCheck].self, forKey: .healthChecks) ?? []
    }
}

public struct LauncherManifest: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var appId: String
    public var bottleId: String
    public var displayName: String
    public var exePath: String
    public var args: [String]
    public var iconPath: String?
    public var envOverrides: [String: String]
    public var showInHome: Bool

    public init(
        id: String,
        appId: String,
        bottleId: String,
        displayName: String,
        exePath: String,
        args: [String] = [],
        iconPath: String? = nil,
        envOverrides: [String: String] = [:],
        showInHome: Bool = true
    ) {
        self.id = id
        self.appId = appId
        self.bottleId = bottleId
        self.displayName = displayName
        self.exePath = exePath
        self.args = args
        self.iconPath = iconPath
        self.envOverrides = envOverrides
        self.showInHome = showInHome
    }
}

public struct BottleManifest: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var name: String
    public var windowsVersion: String
    public var arch: WineArch
    public var engineId: String
    public var envOverrides: [String: String]
    public var installedApps: [LauncherManifest]
    public var createdAt: Date
    public var updatedAt: Date

    public init(
        id: String,
        name: String,
        windowsVersion: String,
        arch: WineArch,
        engineId: String,
        envOverrides: [String: String] = [:],
        installedApps: [LauncherManifest] = [],
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.windowsVersion = windowsVersion
        self.arch = arch
        self.engineId = engineId
        self.envOverrides = envOverrides
        self.installedApps = installedApps
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

public enum InstallerMode: String, Codable, Sendable {
    case localFile
    case download
    case alreadyInstalled
    case none
}

public struct InstallerSpec: Codable, Equatable, Sendable {
    public var mode: InstallerMode
    public var url: String?
    public var fileName: String?
    public var sha256: String?
    public var command: String?
    public var arguments: [String]
    public var hints: [String]

    public init(
        mode: InstallerMode,
        url: String? = nil,
        fileName: String? = nil,
        sha256: String? = nil,
        command: String? = nil,
        arguments: [String] = [],
        hints: [String] = []
    ) {
        self.mode = mode
        self.url = url
        self.fileName = fileName
        self.sha256 = sha256
        self.command = command
        self.arguments = arguments
        self.hints = hints
    }

    private enum CodingKeys: String, CodingKey {
        case mode
        case url
        case fileName
        case sha256
        case command
        case arguments
        case hints
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.mode = try container.decode(InstallerMode.self, forKey: .mode)
        self.url = try container.decodeIfPresent(String.self, forKey: .url)
        self.fileName = try container.decodeIfPresent(String.self, forKey: .fileName)
        self.sha256 = try container.decodeIfPresent(String.self, forKey: .sha256)
        self.command = try container.decodeIfPresent(String.self, forKey: .command)
        self.arguments = try container.decodeIfPresent([String].self, forKey: .arguments) ?? []
        self.hints = try container.decodeIfPresent([String].self, forKey: .hints) ?? []
    }
}

public struct BottleTemplate: Codable, Equatable, Sendable {
    public var windowsVersion: String
    public var arch: WineArch

    public init(windowsVersion: String, arch: WineArch) {
        self.windowsVersion = windowsVersion
        self.arch = arch
    }
}

public struct EngineRequirements: Codable, Equatable, Sendable {
    public var minWineVersion: String?
    public var supportedArch: [WineArch]
    public var requiresWin32: Bool

    public init(minWineVersion: String? = nil, supportedArch: [WineArch] = [.win64], requiresWin32: Bool = false) {
        self.minWineVersion = minWineVersion
        self.supportedArch = supportedArch
        self.requiresWin32 = requiresWin32
    }

    public func isSatisfied(by engine: EngineManifest) -> Bool {
        supportedArch.contains(engine.arch) && (!requiresWin32 || engine.supportsWin32)
    }

    private enum CodingKeys: String, CodingKey {
        case minWineVersion
        case supportedArch
        case requiresWin32
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.minWineVersion = try container.decodeIfPresent(String.self, forKey: .minWineVersion)
        self.supportedArch = try container.decodeIfPresent([WineArch].self, forKey: .supportedArch) ?? [.win64]
        self.requiresWin32 = try container.decodeIfPresent(Bool.self, forKey: .requiresWin32) ?? false
    }
}

public struct LauncherRecipe: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var displayName: String
    public var exePath: String
    public var args: [String]
    public var iconPath: String?
    public var envOverrides: [String: String]
    public var showInHome: Bool

    public init(
        id: String,
        displayName: String,
        exePath: String,
        args: [String] = [],
        iconPath: String? = nil,
        envOverrides: [String: String] = [:],
        showInHome: Bool = true
    ) {
        self.id = id
        self.displayName = displayName
        self.exePath = exePath
        self.args = args
        self.iconPath = iconPath
        self.envOverrides = envOverrides
        self.showInHome = showInHome
    }
}

public struct PostInstallStep: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var kind: String
    public var command: String
    public var args: [String]

    public init(id: String, kind: String, command: String, args: [String] = []) {
        self.id = id
        self.kind = kind
        self.command = command
        self.args = args
    }
}

public struct RecipeManifest: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var name: String
    public var publisher: String
    public var category: String
    public var compatibilityRating: CompatibilityRating
    public var disabledReason: String?
    public var installer: InstallerSpec
    public var bottleTemplate: BottleTemplate
    public var engineRequirements: EngineRequirements
    public var env: [String: String]
    public var launchers: [LauncherRecipe]
    public var postInstall: [PostInstallStep]
    public var warnings: [String]

    public init(
        id: String,
        name: String,
        publisher: String,
        category: String,
        compatibilityRating: CompatibilityRating,
        disabledReason: String? = nil,
        installer: InstallerSpec,
        bottleTemplate: BottleTemplate,
        engineRequirements: EngineRequirements,
        env: [String: String] = [:],
        launchers: [LauncherRecipe],
        postInstall: [PostInstallStep] = [],
        warnings: [String] = []
    ) {
        self.id = id
        self.name = name
        self.publisher = publisher
        self.category = category
        self.compatibilityRating = compatibilityRating
        self.disabledReason = disabledReason
        self.installer = installer
        self.bottleTemplate = bottleTemplate
        self.engineRequirements = engineRequirements
        self.env = env
        self.launchers = launchers
        self.postInstall = postInstall
        self.warnings = warnings
    }
}

public struct InstallTask: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var recipeId: String
    public var bottleId: String
    public var state: InstallTaskState
    public var progressText: String
    public var logPath: String
    public var startedAt: Date
    public var endedAt: Date?
    public var exitCode: Int32?

    public init(
        id: String,
        recipeId: String,
        bottleId: String,
        state: InstallTaskState,
        progressText: String,
        logPath: String,
        startedAt: Date = Date(),
        endedAt: Date? = nil,
        exitCode: Int32? = nil
    ) {
        self.id = id
        self.recipeId = recipeId
        self.bottleId = bottleId
        self.state = state
        self.progressText = progressText
        self.logPath = logPath
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.exitCode = exitCode
    }
}

public struct CatalogRecipeRef: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var name: String
    public var file: String
    public var sha256: String

    public init(id: String, name: String, file: String, sha256: String) {
        self.id = id
        self.name = name
        self.file = file
        self.sha256 = sha256
    }
}

public struct CatalogIndex: Codable, Equatable, Sendable {
    public var generatedAt: Date
    public var expiresAt: Date
    public var recipes: [CatalogRecipeRef]

    public init(generatedAt: Date, expiresAt: Date, recipes: [CatalogRecipeRef]) {
        self.generatedAt = generatedAt
        self.expiresAt = expiresAt
        self.recipes = recipes
    }
}

public struct CatalogSignature: Codable, Equatable, Sendable {
    public var algorithm: String
    public var keyId: String
    public var signatureBase64: String

    public init(algorithm: String, keyId: String, signatureBase64: String) {
        self.algorithm = algorithm
        self.keyId = keyId
        self.signatureBase64 = signatureBase64
    }
}

public struct CatalogSnapshot: Equatable, Sendable {
    public var index: CatalogIndex
    public var recipes: [RecipeManifest]
    public var isExpired: Bool

    public init(index: CatalogIndex, recipes: [RecipeManifest], isExpired: Bool) {
        self.index = index
        self.recipes = recipes
        self.isExpired = isExpired
    }
}
