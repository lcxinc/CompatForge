import Foundation

public struct BottleService {
    public static let highPerformanceBottleId = "high-performance-win11"
    public static let highPerformanceBottleTemplate = BottleTemplate(windowsVersion: "win11", arch: .win64)
    public static let winebootSentinelName = ".macwin-wineboot-ok"
    public static let removedKernelServices: Set<String> = ["dokan2t", "winebth"]
    public static let disabledBackgroundServices: Set<String> = ["androwssvr", "lenovoserviceas", "lisfservice"]
    public static let wineDbgRegistrySection = "Software\\\\Wine\\\\WineDbg"
    public static let wineDbgShowCrashDialogValue = "ShowCrashDialog"
    public static let wineFontsRegistrySection = "Software\\\\Wine\\\\Fonts"
    public static let wineFontsLogPixelsValue = "LogPixels"
    public static let standardWineDPI: UInt32 = 96
    public static let retinaWineDPI: UInt32 = 192
    public static let mmDeviceEnumeratorClassSection = "Software\\\\Classes\\\\CLSID\\\\{BCDE0395-E52F-467C-8E3D-C4579291692E}"
    public static let mmDeviceEnumeratorInprocSection = "Software\\\\Classes\\\\CLSID\\\\{BCDE0395-E52F-467C-8E3D-C4579291692E}\\\\InprocServer32"
    public static let mmDeviceEnumeratorWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{BCDE0395-E52F-467C-8E3D-C4579291692E}"
    public static let mmDeviceEnumeratorWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{BCDE0395-E52F-467C-8E3D-C4579291692E}\\\\InprocServer32"
    public static let networkListManagerClassSection = "Software\\\\Classes\\\\CLSID\\\\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"
    public static let networkListManagerInprocSection = "Software\\\\Classes\\\\CLSID\\\\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}\\\\InprocServer32"
    public static let networkListManagerWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"
    public static let networkListManagerWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{DCB00C01-570F-4A9B-8D69-199FDBA5723B}\\\\InprocServer32"
    public static let fileOpenDialogClassSection = "Software\\\\Classes\\\\CLSID\\\\{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
    public static let fileOpenDialogInprocSection = "Software\\\\Classes\\\\CLSID\\\\{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}\\\\InprocServer32"
    public static let fileOpenDialogWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"
    public static let fileOpenDialogWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}\\\\InprocServer32"
    public static let fileSaveDialogClassSection = "Software\\\\Classes\\\\CLSID\\\\{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}"
    public static let fileSaveDialogInprocSection = "Software\\\\Classes\\\\CLSID\\\\{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}\\\\InprocServer32"
    public static let fileSaveDialogWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}"
    public static let fileSaveDialogWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}\\\\InprocServer32"
    public static let lenovoAppStoreLauncherId = "lenovo-app-store-pcyyb"
    public static let tencentAppStoreLauncherId = "tencent-app-store-androws"
    public static let sevenZipFileManagerLauncherId = "7zip-file-manager"
    public static let sevenZipGUILauncherId = "7zip-gui"
    public static let sevenZipConsoleLauncherId = "7zip-console"
    public static let hoYoPlayLauncherId = "hoyoplay"
    public static let steamLauncherId = "steam"
    public static let sumatraPDFLauncherId = "sumatrapdf"
    public static let vlcLauncherId = "vlc"
    public static let museScoreLauncherId = "musescore-studio"
    public static let mRemoteNG1782LauncherId = "mremoteng-1782-x64"
    public static let onlyOfficeLauncherId = "onlyoffice-desktop-editors"
    public static let portableAppsBackupLauncherId = "portableapps-backup"
    public static let portableAppsBackupRestoreLauncherId = "portableapps-backup-restore"
    public static let portableAppsUpdaterLauncherId = "portableapps-updater"
    public static let renderingRepairSentinelName = ".macwin-rendering-repair-v22"
    public static let commonAppDataRegistrySentinelName = ".macwin-common-appdata-registry-v1"
    public static let fontRegistrySection = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\Fonts"
    public static let currentVersionFontRegistrySection = "Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Fonts"
    public static let fontSubstitutesRegistrySection = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\FontSubstitutes"
    public static let fontLinkRegistrySection = "Software\\\\Microsoft\\\\Windows NT\\\\CurrentVersion\\\\FontLink\\\\SystemLink"
    public static let wineFontReplacementsRegistrySection = "Software\\\\Wine\\\\Fonts\\\\Replacements"
    public static let windowMetricsRegistrySection = "Control Panel\\\\Desktop\\\\WindowMetrics"
    public static let serviceProviderInterfaceSection = "Software\\\\Classes\\\\Interface\\\\{6D5140C1-7436-11CE-8034-00AA006009FA}"
    public static let serviceProviderProxyStubSection = "Software\\\\Classes\\\\Interface\\\\{6D5140C1-7436-11CE-8034-00AA006009FA}\\\\ProxyStubClsid32"
    public static let serviceProviderNumMethodsSection = "Software\\\\Classes\\\\Interface\\\\{6D5140C1-7436-11CE-8034-00AA006009FA}\\\\NumMethods"
    public static let serviceProviderWow64InterfaceSection = "Software\\\\Classes\\\\Wow6432Node\\\\Interface\\\\{6D5140C1-7436-11CE-8034-00AA006009FA}"
    public static let serviceProviderWow64ProxyStubSection = "Software\\\\Classes\\\\Wow6432Node\\\\Interface\\\\{6D5140C1-7436-11CE-8034-00AA006009FA}\\\\ProxyStubClsid32"
    public static let serviceProviderWow64NumMethodsSection = "Software\\\\Classes\\\\Wow6432Node\\\\Interface\\\\{6D5140C1-7436-11CE-8034-00AA006009FA}\\\\NumMethods"
    public static let activeScriptStatsProxyClassSection = "Software\\\\Classes\\\\CLSID\\\\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}"
    public static let activeScriptStatsProxyInprocSection = "Software\\\\Classes\\\\CLSID\\\\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}\\\\InprocServer32"
    public static let activeScriptStatsProxyWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}"
    public static let activeScriptStatsProxyWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}\\\\InprocServer32"
    public static let taskSchedulerClassSection = "Software\\\\Classes\\\\CLSID\\\\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}"
    public static let taskSchedulerInprocSection = "Software\\\\Classes\\\\CLSID\\\\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}\\\\InprocServer32"
    public static let taskSchedulerWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}"
    public static let taskSchedulerWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{0F87369F-A4E5-4CFC-BD3E-73E6154572DD}\\\\InprocServer32"
    public static let legacyTaskSchedulerClassSection = "Software\\\\Classes\\\\CLSID\\\\{148BD52A-A2AB-11CE-B11F-00AA00530503}"
    public static let legacyTaskSchedulerInprocSection = "Software\\\\Classes\\\\CLSID\\\\{148BD52A-A2AB-11CE-B11F-00AA00530503}\\\\InprocServer32"
    public static let legacyTaskSchedulerWow64ClassSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{148BD52A-A2AB-11CE-B11F-00AA00530503}"
    public static let legacyTaskSchedulerWow64InprocSection = "Software\\\\Classes\\\\Wow6432Node\\\\CLSID\\\\{148BD52A-A2AB-11CE-B11F-00AA00530503}\\\\InprocServer32"
    public static let scheduleServiceSection = "System\\\\CurrentControlSet\\\\Services\\\\Schedule"
    public static let scheduleServiceParametersSection = "System\\\\CurrentControlSet\\\\Services\\\\Schedule\\\\Parameters"
    public static let cryptoProviderType001Section = "Software\\\\Microsoft\\\\Cryptography\\\\Defaults\\\\Provider Types\\\\Type 001"
    public static let cryptoProviderType012Section = "Software\\\\Microsoft\\\\Cryptography\\\\Defaults\\\\Provider Types\\\\Type 012"
    public static let cryptoProviderType024Section = "Software\\\\Microsoft\\\\Cryptography\\\\Defaults\\\\Provider Types\\\\Type 024"
    public static let shellFoldersSection = "Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Explorer\\\\Shell Folders"
    public static let userShellFoldersSection = "Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Explorer\\\\User Shell Folders"
    public static let commonShellFolderRegistryValues = [
        ("Common AppData", "C:\\ProgramData"),
        ("Common Desktop", "C:\\users\\Public\\Desktop"),
        ("Common Documents", "C:\\users\\Public\\Documents"),
        ("Common Programs", "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs"),
        ("Common Start Menu", "C:\\ProgramData\\Microsoft\\Windows\\Start Menu"),
        ("Common Startup", "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"),
        ("Common Templates", "C:\\ProgramData\\Microsoft\\Windows\\Templates")
    ]
    public static let commonShellDirectoryRelativePaths = [
        "ProgramData",
        "ProgramData/Microsoft/Windows/Start Menu/Programs/Startup",
        "ProgramData/Microsoft/Windows/Templates",
        "users/Public/Desktop",
        "users/Public/Documents",
        "users/Public/Downloads",
        "users/Public/Music",
        "users/Public/Pictures",
        "users/Public/Videos"
    ]
    public static let chromiumRootDLLNames = [
        "chrome_elf.dll",
        "chrome_wer.dll",
        "msedge_elf.dll",
        "msedge_wer.dll",
        "vivaldi_elf.dll"
    ]
    public static let disabledBundledGPUDLLDirectoryName = ".macwin-disabled-gpu-dlls"
    public static let bundledGPUDLLNames = [
        "libEGL.dll",
        "libGLESv2.dll",
        "vulkan-1.dll",
        "vk_swiftshader.dll",
        "vk_swiftshader_icd.json",
        "d3dcompiler_47.dll",
        "dxcompiler.dll",
        "dxil.dll"
    ]
    public static let fontConfigFileName = "fonts.conf"
    public static let steamLauncherArguments = ApplicationCompatibilityProfile.steamClient.launchArguments
    public static let steamWebHelperArguments = ApplicationCompatibilityProfile.steamWebHelperArguments
    public static let steamLauncherEnvironment = ApplicationCompatibilityProfile.steamClient.environment
    public static let museScoreLauncherArguments = ApplicationCompatibilityProfile.museScoreStudio.launchArguments
    public static let museScoreLauncherEnvironment = ApplicationCompatibilityProfile.museScoreStudio.environment
    public static let mRemoteNG1782Arguments = ApplicationCompatibilityProfile.mRemoteNG1782.launchArguments
    public static let mRemoteNG1782Environment = ApplicationCompatibilityProfile.mRemoteNG1782.environment
    public static let cefSoftwareRendererArguments = ApplicationCompatibilityProfile.cefSoftwareRenderer.launchArguments
    public static let cefSoftwareRendererEnvironment = ApplicationCompatibilityProfile.cefSoftwareRenderer.environment
    public static let onlyOfficeLauncherEnvironment = ApplicationCompatibilityProfile.cefSoftwareRenderer.environment.merging([
        "PATH": "C:\\Program Files\\ONLYOFFICE\\DesktopEditors\\converter;C:\\Program Files\\ONLYOFFICE\\DesktopEditors;C:\\windows\\system32;C:\\windows;C:\\windows\\system32\\wbem;C:\\windows\\system32\\WindowsPowershell\\v1.0",
        "MACWIN_ONLYOFFICE_RENDERER_FONT_REPAIR": "1"
    ], uniquingKeysWith: { _, new in new })
    public static let hoYoPlayArguments = ApplicationCompatibilityProfile.hoYoPlay.launchArguments
    public static let hoYoPlayEnvironment = ApplicationCompatibilityProfile.hoYoPlay.environment
    public static let lenovoAppStoreArguments = ApplicationCompatibilityProfile.lenovoAppStore.launchArguments
    public static let lenovoAppStoreEnvironment = ApplicationCompatibilityProfile.lenovoAppStore.environment
    public static let tencentAppStoreArguments = ApplicationCompatibilityProfile.tencentAppStore.launchArguments
    public static let tencentAppStoreEnvironment = ApplicationCompatibilityProfile.tencentAppStore.environment
    public static let userShellDirectoryRelativePaths = [
        "AppData/Local",
        "AppData/Local/Microsoft/Windows/INetCache",
        "AppData/Local/Microsoft/Windows/INetCookies",
        "AppData/Roaming",
        "AppData/Roaming/Microsoft/Windows/Recent",
        "AppData/Roaming/Microsoft/Windows/SendTo",
        "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup",
        "AppData/Roaming/Microsoft/Windows/Templates",
        "Desktop",
        "Documents",
        "Downloads",
        "Music",
        "Pictures",
        "Videos"
    ]
    public static let shellFolderRegistryValues = [
        ("AppData", "AppData\\Roaming"),
        ("Cache", "AppData\\Local\\Microsoft\\Windows\\INetCache"),
        ("Cookies", "AppData\\Local\\Microsoft\\Windows\\INetCookies"),
        ("Desktop", "Desktop"),
        ("Local AppData", "AppData\\Local"),
        ("My Music", "Music"),
        ("My Pictures", "Pictures"),
        ("My Video", "Videos"),
        ("Personal", "Documents"),
        ("Programs", "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs"),
        ("Recent", "AppData\\Roaming\\Microsoft\\Windows\\Recent"),
        ("SendTo", "AppData\\Roaming\\Microsoft\\Windows\\SendTo"),
        ("Start Menu", "AppData\\Roaming\\Microsoft\\Windows\\Start Menu"),
        ("Startup", "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"),
        ("Templates", "AppData\\Roaming\\Microsoft\\Windows\\Templates"),
        ("Downloads", "Downloads"),
        ("{374DE290-123F-4565-9164-39C4925E467B}", "Downloads")
    ]
    public static let freeCADPythonUnameShimText = """
    # MacWin compatibility shim for FreeCAD's embedded Windows Python under Wine on macOS.
    import os

    if not hasattr(os, "uname"):
        class _MacWinUnameResult(tuple):
            __slots__ = ()
            _fields = ("sysname", "nodename", "release", "version", "machine")

            def __new__(cls):
                return tuple.__new__(cls, ("Windows", "macwin", "11", "Wine", "AMD64"))

            @property
            def sysname(self):
                return self[0]

            @property
            def nodename(self):
                return self[1]

            @property
            def release(self):
                return self[2]

            @property
            def version(self):
                return self[3]

            @property
            def machine(self):
                return self[4]

        def _macwin_uname():
            return _MacWinUnameResult()

        os.uname = _macwin_uname

    """

    public var paths: MacWinPaths
    public var store: JSONStore
    public var fileManager: FileManager
    public var runner: WineRunner

    public init(paths: MacWinPaths = MacWinPaths(), fileManager: FileManager = .default, runner: WineRunner? = nil) {
        self.paths = paths
        self.store = JSONStore(fileManager: fileManager)
        self.fileManager = fileManager
        self.runner = runner ?? WineRunner(paths: paths, fileManager: fileManager)
    }

    public func listBottles() throws -> [BottleManifest] {
        try paths.ensureBaseDirectories(fileManager: fileManager)
        return try store.loadMany(BottleManifest.self, in: paths.bottlesDirectory, fileName: "manifest.json")
            .sorted { $0.updatedAt > $1.updatedAt }
    }

    public func bottle(id: String) throws -> BottleManifest? {
        let url = paths.bottleManifestURL(id: id)
        guard fileManager.fileExists(atPath: url.path) else { return nil }
        return try store.load(BottleManifest.self, from: url)
    }

    @discardableResult
    public func createBottle(name: String, template: BottleTemplate, engine: EngineManifest, runWineboot: Bool = true) throws -> BottleManifest {
        let id = Self.makeBottleId(name: name)
        return try createBottle(
            id: id,
            name: name,
            template: template,
            engine: engine,
            envOverrides: [:],
            runWineboot: runWineboot
        )
    }

    @discardableResult
    public func createBottle(
        id: String,
        name: String,
        template: BottleTemplate,
        engine: EngineManifest,
        envOverrides: [String: String] = [:],
        runWineboot: Bool = true
    ) throws -> BottleManifest {
        let bottleDirectory = paths.bottleDirectory(id: id)
        try fileManager.createDirectory(at: bottleDirectory, withIntermediateDirectories: true)

        var bottle = BottleManifest(
            id: id,
            name: name,
            windowsVersion: template.windowsVersion,
            arch: template.arch,
            engineId: engine.id,
            envOverrides: envOverrides,
            installedApps: []
        )
        try saveBottle(bottle)

        if runWineboot {
            bottle = try bootstrapWinePrefixIfNeeded(bottle: bottle, engine: engine, force: true)
        }

        return bottle
    }

    @discardableResult
    public func ensureHighPerformanceBottle(
        name: String,
        engine: EngineManifest,
        runWineboot: Bool = true
    ) throws -> BottleManifest {
        try ensureBottle(
            id: Self.highPerformanceBottleId,
            name: name,
            template: Self.highPerformanceBottleTemplate,
            engine: engine,
            envOverrides: Self.highPerformanceEnvOverrides(engine: engine),
            enforceEnvOverrides: false,
            runWineboot: runWineboot
        )
    }

    @discardableResult
    public func ensureBottle(
        id: String,
        name: String,
        template: BottleTemplate,
        engine: EngineManifest,
        envOverrides: [String: String],
        enforceEnvOverrides: Bool = true,
        runWineboot: Bool = true
    ) throws -> BottleManifest {
        if var existing = try bottle(id: id) {
            var changed = false
            var engineChanged = false
            if existing.name != name {
                existing.name = name
                changed = true
            }
            if existing.windowsVersion != template.windowsVersion {
                existing.windowsVersion = template.windowsVersion
                changed = true
            }
            if existing.arch != template.arch {
                existing.arch = template.arch
                changed = true
            }
            if existing.engineId != engine.id {
                existing.engineId = engine.id
                changed = true
                engineChanged = true
            }
            for (key, value) in envOverrides {
                if enforceEnvOverrides || existing.envOverrides[key] == nil {
                    if existing.envOverrides[key] != value {
                        existing.envOverrides[key] = value
                        changed = true
                    }
                }
            }
            if changed {
                existing.updatedAt = Date()
                try saveBottle(existing)
            }
            if runWineboot {
                return try bootstrapWinePrefixIfNeeded(bottle: existing, engine: engine, force: engineChanged)
            }
            if !engineChanged, hasCurrentCompatibilityRepairSentinels(existing) {
                return existing
            }
            try repairBottleCompatibility(existing, engine: engine)
            return try bottle(id: id) ?? existing
        }

        return try createBottle(
            id: id,
            name: name,
            template: template,
            engine: engine,
            envOverrides: envOverrides,
            runWineboot: runWineboot
        )
    }

    @discardableResult
    public func bootstrapWinePrefixIfNeeded(
        bottle: BottleManifest,
        engine: EngineManifest,
        force: Bool = false
    ) throws -> BottleManifest {
        let sentinel = winebootSentinelURL(for: bottle)
        if !force, fileManager.fileExists(atPath: sentinel.path) {
            try repairBottleCompatibility(bottle, engine: engine)
            return try self.bottle(id: bottle.id) ?? bottle
        }

        let result = try runner.run(
            WineRunRequest(exe: "wineboot", args: ["-u"], bottle: bottle, engine: engine, logName: "\(bottle.id)-wineboot.log")
        )
        if result.exitCode != 0 {
            throw MacWinError.processFailed(
                command: result.commandLine.joined(separator: " "),
                exitCode: result.exitCode,
                logPath: result.logURL.path
            )
        }

        var updated = bottle
        updated.updatedAt = Date()
        try saveBottle(updated)
        try repairBottleCompatibility(updated, engine: engine)
        try Data("ok\n".utf8).write(to: sentinel, options: [.atomic])
        return try self.bottle(id: updated.id) ?? updated
    }

    public func repairBottleCompatibility(_ bottle: BottleManifest, engine: EngineManifest? = nil) throws {
        if let engine {
            try repairWoW64SystemFilesIfNeeded(bottle: bottle, engine: engine)
            try repairEngineCoverageSystemDLLs(bottle: bottle, engine: engine)
        }
        let didRepairUserDirectories = try repairUserShellDirectories(bottle)
        let didRepairCommonDirectories = try repairCommonShellDirectories(bottle)
        let didRepairFreeCADPythonShim = try repairFreeCADPythonUnameShim(bottle)
        let didRepairFontFiles = try repairWindowsFontFiles(bottle)
        let didRepairFontConfig = try repairFontConfig(bottle)
        let didRepairRegistry = try repairRegistryCompatibility(bottle)
        if let engine {
            try synchronizeCommonAppDataRegistry(bottle, engine: engine)
        }
        let renderingRepairSentinel = paths.bottleDirectory(id: bottle.id)
            .appendingPathComponent(Self.renderingRepairSentinelName)
        let shouldResetRenderingCaches = didRepairFontFiles
            || didRepairFontConfig
            || didRepairRegistry
            || didRepairUserDirectories
            || didRepairCommonDirectories
            || didRepairFreeCADPythonShim
            || !fileManager.fileExists(atPath: renderingRepairSentinel.path)
        if shouldResetRenderingCaches {
            try repairWebViewRenderingCaches(bottle)
            try Data("ok\n".utf8).write(to: renderingRepairSentinel, options: [.atomic])
        }
        let detectedBottle = try registerDetectedInstalledApps(in: bottle)
        _ = try migrateLauncherCompatibility(in: detectedBottle)
    }

    private func hasCurrentCompatibilityRepairSentinels(_ bottle: BottleManifest) -> Bool {
        let renderingRepairSentinel = paths.bottleDirectory(id: bottle.id)
            .appendingPathComponent(Self.renderingRepairSentinelName)
        let commonAppDataRegistrySentinel = paths.bottleDirectory(id: bottle.id)
            .appendingPathComponent(Self.commonAppDataRegistrySentinelName)
        return fileManager.fileExists(atPath: renderingRepairSentinel.path)
            && fileManager.fileExists(atPath: commonAppDataRegistrySentinel.path)
    }

    private func synchronizeCommonAppDataRegistry(
        _ bottle: BottleManifest,
        engine: EngineManifest
    ) throws {
        guard fileManager.isExecutableFile(atPath: engine.winePath) else { return }
        let marker = paths.bottleDirectory(id: bottle.id)
            .appendingPathComponent(Self.commonAppDataRegistrySentinelName)
        guard !fileManager.fileExists(atPath: marker.path) else { return }

        let result = try runner.run(WineRunRequest(
            exe: #"C:\windows\system32\reg.exe"#,
            args: [
                "add",
                #"HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"#,
                "/v",
                "Common AppData",
                "/t",
                "REG_SZ",
                "/d",
                #"C:\ProgramData"#,
                "/f"
            ],
            bottle: bottle,
            engine: engine,
            envOverrides: ["WINEDEBUG": "-all"],
            logName: "\(bottle.id)-common-appdata-registry.log"
        ))
        guard result.exitCode == 0 else {
            throw MacWinError.processFailed(
                command: result.commandLine.joined(separator: " "),
                exitCode: result.exitCode,
                logPath: result.logURL.path
            )
        }
        try Data("ok\n".utf8).write(to: marker, options: [.atomic])
    }

    public func resetWebViewRenderingCaches(for bottle: BottleManifest) throws {
        try repairWebViewRenderingCaches(bottle)
    }

    public func detectedInstalledLaunchers(in bottle: BottleManifest) -> [LauncherManifest] {
        let driveC = paths.bottleDriveCURL(id: bottle.id)
        var launchers: [LauncherManifest] = []

        let lenovoAppStore = driveC
            .appendingPathComponent("Program Files (x86)", isDirectory: true)
            .appendingPathComponent("Lenovo", isDirectory: true)
            .appendingPathComponent("LeAppStore", isDirectory: true)
            .appendingPathComponent("LenovoAppStore.exe")

        if fileManager.fileExists(atPath: lenovoAppStore.path) {
            launchers.append(
                LauncherManifest(
                    id: Self.lenovoAppStoreLauncherId,
                    appId: "lenovo-app-store-pcyyb",
                    bottleId: bottle.id,
                    displayName: "联想应用商店 / 应用宝",
                    exePath: "C:\\Program Files (x86)\\Lenovo\\LeAppStore\\LenovoAppStore.exe",
                    args: Self.lenovoAppStoreArguments,
                    envOverrides: Self.lenovoAppStoreEnvironment,
                    showInHome: true
                )
            )
        }

        if let tencentAppStore = detectedTencentAppStoreLauncher(in: driveC, bottleId: bottle.id) {
            launchers.append(tencentAppStore)
        }

        launchers.append(contentsOf: detectedSevenZipLaunchers(in: driveC, bottleId: bottle.id))

        if let hoYoPlay = detectedHoYoPlayLauncher(in: driveC, bottleId: bottle.id) {
            launchers.append(hoYoPlay)
        }

        let steamPaths = [
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("Steam", isDirectory: true)
                    .appendingPathComponent("Steam.exe"),
                windowsPath: "C:\\Program Files\\Steam\\Steam.exe"
            ),
            (
                url: driveC
                    .appendingPathComponent("Program Files (x86)", isDirectory: true)
                    .appendingPathComponent("Steam", isDirectory: true)
                    .appendingPathComponent("Steam.exe"),
                windowsPath: "C:\\Program Files (x86)\\Steam\\Steam.exe"
            )
        ]
        if let steamPath = steamPaths.first(where: { fileManager.fileExists(atPath: $0.url.path) }) {
            launchers.append(
                LauncherManifest(
                    id: Self.steamLauncherId,
                    appId: "steam",
                    bottleId: bottle.id,
                    displayName: "Steam",
                    exePath: steamPath.windowsPath,
                    args: Self.steamLauncherArguments,
                    envOverrides: Self.steamLauncherEnvironment,
                    showInHome: true
                )
            )
        }

        if let onlyOffice = detectedOnlyOfficeLauncher(in: driveC, bottleId: bottle.id) {
            launchers.append(onlyOffice)
        }

        if let museScore = detectedMuseScoreLauncher(in: driveC, bottleId: bottle.id) {
            launchers.append(museScore)
        }

        if let mRemoteNG = detectedMRemoteNG1782Launcher(in: driveC, bottleId: bottle.id) {
            launchers.append(mRemoteNG)
        }

        if let sumatraPDF = detectedSumatraPDFLauncher(in: driveC, bottleId: bottle.id) {
            launchers.append(sumatraPDF)
        }

        if let vlc = detectedVLCLauncher(in: driveC, bottleId: bottle.id) {
            launchers.append(vlc)
        }

        launchers.append(contentsOf: detectedPortableAppsUtilityLaunchers(in: driveC, bottleId: bottle.id))

        let localAppId = "local-\(bottle.id)"
        let curatedLaunchers = bottle.installedApps.filter { $0.appId != localAppId }
        let knownExecutablePaths = Set(
            (launchers + curatedLaunchers).map { normalizedWindowsExecutablePath($0.exePath) }
        )
        launchers.append(contentsOf: genericInstalledLaunchers(in: driveC, bottleId: bottle.id, excluding: knownExecutablePaths))

        return launchers
    }

    private func detectedSevenZipLaunchers(in driveC: URL, bottleId: String) -> [LauncherManifest] {
        let root = driveC
            .appendingPathComponent("Program Files", isDirectory: true)
            .appendingPathComponent("7-Zip", isDirectory: true)
        let candidates = [
            (
                id: Self.sevenZipFileManagerLauncherId,
                displayName: "7-Zip File Manager",
                fileName: "7zFM.exe"
            ),
            (
                id: Self.sevenZipGUILauncherId,
                displayName: "7-Zip GUI",
                fileName: "7zG.exe"
            ),
            (
                id: Self.sevenZipConsoleLauncherId,
                displayName: "7-Zip Console",
                fileName: "7z.exe"
            )
        ]

        return candidates.compactMap { candidate in
            let url = root.appendingPathComponent(candidate.fileName)
            guard fileManager.fileExists(atPath: url.path) else { return nil }
            let launcher = LauncherManifest(
                id: candidate.id,
                appId: "7zip",
                bottleId: bottleId,
                displayName: candidate.displayName,
                exePath: "C:\\Program Files\\7-Zip\\\(candidate.fileName)",
                args: [],
                envOverrides: [:],
                showInHome: true
            )
            return ApplicationCompatibilityProfile.sevenZipGDI.applied(to: launcher)
        }
    }

    private func detectedSumatraPDFLauncher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let candidates = [
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("SumatraPDF", isDirectory: true)
                    .appendingPathComponent("SumatraPDF.exe"),
                windowsPath: "C:\\Program Files\\SumatraPDF\\SumatraPDF.exe"
            ),
            (
                url: driveC
                    .appendingPathComponent("Program Files (x86)", isDirectory: true)
                    .appendingPathComponent("SumatraPDF", isDirectory: true)
                    .appendingPathComponent("SumatraPDF.exe"),
                windowsPath: "C:\\Program Files (x86)\\SumatraPDF\\SumatraPDF.exe"
            )
        ]

        if let installed = candidates.first(where: { fileManager.fileExists(atPath: $0.url.path) }) {
            return sumatraPDFLauncher(bottleId: bottleId, windowsPath: installed.windowsPath)
        }

        let usersDirectory = driveC.appendingPathComponent("users", isDirectory: true)
        guard let userDirectories = try? fileManager.contentsOfDirectory(
            at: usersDirectory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else {
            return nil
        }

        for userDirectory in userDirectories.sorted(by: { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }) {
            guard (try? userDirectory.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true else { continue }
            let exeURL = userDirectory
                .appendingPathComponent("AppData", isDirectory: true)
                .appendingPathComponent("Local", isDirectory: true)
                .appendingPathComponent("SumatraPDF", isDirectory: true)
                .appendingPathComponent("SumatraPDF.exe")
            guard fileManager.fileExists(atPath: exeURL.path) else { continue }
            let windowsPath = "C:\\users\\\(userDirectory.lastPathComponent)\\AppData\\Local\\SumatraPDF\\SumatraPDF.exe"
            return sumatraPDFLauncher(bottleId: bottleId, windowsPath: windowsPath)
        }

        return nil
    }

    private func sumatraPDFLauncher(bottleId: String, windowsPath: String) -> LauncherManifest {
        LauncherManifest(
            id: Self.sumatraPDFLauncherId,
            appId: "sumatrapdf",
            bottleId: bottleId,
            displayName: "SumatraPDF",
            exePath: windowsPath,
            args: [],
            envOverrides: [
                "LANG": "zh_CN.UTF-8",
                "LC_ALL": "zh_CN.UTF-8",
                "LC_CTYPE": "zh_CN.UTF-8",
                "MACWIN_FONTCONFIG_REPAIR": "1",
                "MACWIN_TEXT_RENDERING_REPAIR": "1",
                "WINEDEBUG": "-all"
            ],
            showInHome: true
        )
    }

    private func detectedVLCLauncher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let candidates = [
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("VideoLAN", isDirectory: true)
                    .appendingPathComponent("VLC", isDirectory: true)
                    .appendingPathComponent("vlc.exe"),
                windowsPath: "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"
            ),
            (
                url: driveC
                    .appendingPathComponent("Program Files (x86)", isDirectory: true)
                    .appendingPathComponent("VideoLAN", isDirectory: true)
                    .appendingPathComponent("VLC", isDirectory: true)
                    .appendingPathComponent("vlc.exe"),
                windowsPath: "C:\\Program Files (x86)\\VideoLAN\\VLC\\vlc.exe"
            )
        ]
        guard let candidate = candidates.first(where: { fileManager.fileExists(atPath: $0.url.path) }) else {
            return nil
        }
        return LauncherManifest(
            id: Self.vlcLauncherId,
            appId: "vlc",
            bottleId: bottleId,
            displayName: "VLC media player",
            exePath: candidate.windowsPath,
            args: [],
            envOverrides: [
                "LANG": "zh_CN.UTF-8",
                "LC_ALL": "zh_CN.UTF-8",
                "LC_CTYPE": "zh_CN.UTF-8",
                "MACWIN_FONTCONFIG_REPAIR": "1",
                "MACWIN_TEXT_RENDERING_REPAIR": "1",
                "WINE_D3D_CONFIG": "renderer=vulkan,csmt=0x0",
                "WINEDEBUG": "-all"
            ],
            showInHome: true
        )
    }

    @discardableResult
    public func registerDetectedInstalledApps(in bottle: BottleManifest) throws -> BottleManifest {
        var latest = try self.bottle(id: bottle.id) ?? bottle
        let launchers = detectedInstalledLaunchers(in: latest)
        let detectedIds = Set(launchers.map(\.id))
        let localAppId = "local-\(bottle.id)"
        let originalCount = latest.installedApps.count
        latest.installedApps.removeAll { launcher in
            launcher.appId == localAppId && !detectedIds.contains(launcher.id)
        }
        if latest.installedApps.count != originalCount {
            latest.updatedAt = Date()
            try saveBottle(latest)
        }
        guard !launchers.isEmpty else { return latest }
        return try addLaunchers(launchers, to: latest)
    }

    @discardableResult
    public func migrateLauncherCompatibility(in bottle: BottleManifest) throws -> BottleManifest {
        var latest = try self.bottle(id: bottle.id) ?? bottle
        guard !latest.installedApps.isEmpty else { return latest }

        var changed = false
        latest.installedApps = latest.installedApps.map { launcher in
            let migrated: LauncherManifest
            if let profile = ApplicationCompatibilityProfile.current(in: launcher) {
                migrated = profile.applied(to: launcher)
            } else {
                var sanitized = launcher
                sanitized.args = ApplicationCompatibilityProfile.sanitizedLaunchArguments(launcher.args)
                sanitized.envOverrides = WineRunner.sanitizedRuntimeEnvironment(launcher.envOverrides)
                migrated = sanitized
            }
            if migrated != launcher {
                changed = true
            }
            return migrated
        }

        if changed {
            latest.updatedAt = Date()
            try saveBottle(latest)
        }
        return latest
    }

    private func detectedHoYoPlayLauncher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let root = driveC
            .appendingPathComponent("Program Files", isDirectory: true)
            .appendingPathComponent("miHoYo Launcher", isDirectory: true)

        let directCandidates = [
            ("launcher.exe", "C:\\Program Files\\miHoYo Launcher\\launcher.exe"),
            ("HYP.exe", "C:\\Program Files\\miHoYo Launcher\\HYP.exe")
        ]
        for (fileName, windowsPath) in directCandidates {
            if fileManager.fileExists(atPath: root.appendingPathComponent(fileName).path) {
                return hoYoPlayLauncher(bottleId: bottleId, exePath: windowsPath)
            }
        }

        let versionDirectories = (try? fileManager.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        for directory in versionDirectories.sorted(by: { lhs, rhs in
            lhs.lastPathComponent.localizedStandardCompare(rhs.lastPathComponent) == .orderedDescending
        }) {
            let values = try? directory.resourceValues(forKeys: [.isDirectoryKey])
            guard values?.isDirectory == true else { continue }
            for fileName in ["launcher.exe", "HYP.exe"] {
                if fileManager.fileExists(atPath: directory.appendingPathComponent(fileName).path) {
                    return hoYoPlayLauncher(
                        bottleId: bottleId,
                        exePath: "C:\\Program Files\\miHoYo Launcher\\\(directory.lastPathComponent)\\\(fileName)"
                    )
                }
            }
        }

        return nil
    }

    private func hoYoPlayLauncher(bottleId: String, exePath: String) -> LauncherManifest {
        LauncherManifest(
            id: Self.hoYoPlayLauncherId,
            appId: "hoyoplay-cn",
            bottleId: bottleId,
            displayName: "HoYoPlay / 米哈游启动器",
            exePath: exePath,
            args: Self.hoYoPlayArguments,
            envOverrides: Self.hoYoPlayEnvironment,
            showInHome: true
        )
    }

    private func detectedTencentAppStoreLauncher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let applicationRoot = driveC
            .appendingPathComponent("Program Files", isDirectory: true)
            .appendingPathComponent("Tencent", isDirectory: true)
            .appendingPathComponent("Androws", isDirectory: true)
            .appendingPathComponent("Application", isDirectory: true)

        let versionDirectories = (try? fileManager.contentsOfDirectory(
            at: applicationRoot,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        for directory in versionDirectories.sorted(by: { lhs, rhs in
            lhs.lastPathComponent.localizedStandardCompare(rhs.lastPathComponent) == .orderedDescending
        }) {
            let values = try? directory.resourceValues(forKeys: [.isDirectoryKey])
            guard values?.isDirectory == true else { continue }
            for fileName in ["AndrowsStore.exe", "AndrowsLauncher.exe"] {
                if fileManager.fileExists(atPath: directory.appendingPathComponent(fileName).path) {
                    return tencentAppStoreLauncher(
                        bottleId: bottleId,
                        exePath: "C:\\Program Files\\Tencent\\Androws\\Application\\\(directory.lastPathComponent)\\\(fileName)"
                    )
                }
            }
        }

        let directLauncher = applicationRoot.appendingPathComponent("AndrowsLauncher.exe")
        if fileManager.fileExists(atPath: directLauncher.path) {
            return tencentAppStoreLauncher(
                bottleId: bottleId,
                exePath: "C:\\Program Files\\Tencent\\Androws\\Application\\AndrowsLauncher.exe"
            )
        }

        return nil
    }

    private func tencentAppStoreLauncher(bottleId: String, exePath: String) -> LauncherManifest {
        LauncherManifest(
            id: Self.tencentAppStoreLauncherId,
            appId: "tencent-app-store",
            bottleId: bottleId,
            displayName: "应用宝 / 腾讯应用市场",
            exePath: exePath,
            args: Self.tencentAppStoreArguments,
            envOverrides: Self.tencentAppStoreEnvironment,
            showInHome: true
        )
    }

    private func detectedOnlyOfficeLauncher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let candidates = [
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("ONLYOFFICE", isDirectory: true)
                    .appendingPathComponent("DesktopEditors", isDirectory: true)
                    .appendingPathComponent("DesktopEditors.exe"),
                windowsPath: "C:\\Program Files\\ONLYOFFICE\\DesktopEditors\\DesktopEditors.exe"
            ),
            (
                url: driveC
                    .appendingPathComponent("Program Files (x86)", isDirectory: true)
                    .appendingPathComponent("ONLYOFFICE", isDirectory: true)
                    .appendingPathComponent("DesktopEditors", isDirectory: true)
                    .appendingPathComponent("DesktopEditors.exe"),
                windowsPath: "C:\\Program Files (x86)\\ONLYOFFICE\\DesktopEditors\\DesktopEditors.exe"
            )
        ]
        guard let candidate = candidates.first(where: { fileManager.fileExists(atPath: $0.url.path) }) else {
            return nil
        }
        return LauncherManifest(
            id: Self.onlyOfficeLauncherId,
            appId: "onlyoffice-desktop-editors",
            bottleId: bottleId,
            displayName: "ONLYOFFICE Desktop Editors",
            exePath: candidate.windowsPath,
            args: Self.cefSoftwareRendererArguments,
            envOverrides: Self.onlyOfficeLauncherEnvironment,
            showInHome: true
        )
    }

    private func detectedMuseScoreLauncher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let candidates = [
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("MuseScore 4", isDirectory: true)
                    .appendingPathComponent("bin", isDirectory: true)
                    .appendingPathComponent("MuseScore4.exe"),
                windowsPath: "C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe"
            ),
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("MuseScore Studio 4", isDirectory: true)
                    .appendingPathComponent("bin", isDirectory: true)
                    .appendingPathComponent("MuseScore4.exe"),
                windowsPath: "C:\\Program Files\\MuseScore Studio 4\\bin\\MuseScore4.exe"
            ),
            (
                url: driveC
                    .appendingPathComponent("Program Files", isDirectory: true)
                    .appendingPathComponent("MuseScore Studio", isDirectory: true)
                    .appendingPathComponent("bin", isDirectory: true)
                    .appendingPathComponent("MuseScore4.exe"),
                windowsPath: "C:\\Program Files\\MuseScore Studio\\bin\\MuseScore4.exe"
            )
        ]
        guard let candidate = candidates.first(where: { fileManager.fileExists(atPath: $0.url.path) }) else {
            return nil
        }
        return LauncherManifest(
            id: Self.museScoreLauncherId,
            appId: "musescore-studio",
            bottleId: bottleId,
            displayName: "MuseScore Studio",
            exePath: candidate.windowsPath,
            args: Self.museScoreLauncherArguments,
            envOverrides: Self.museScoreLauncherEnvironment,
            showInHome: true
        )
    }

    private func detectedMRemoteNG1782Launcher(in driveC: URL, bottleId: String) -> LauncherManifest? {
        let executable = driveC
            .appendingPathComponent("macwin-portable", isDirectory: true)
            .appendingPathComponent("mremoteng-1782-x64", isDirectory: true)
            .appendingPathComponent("mRemoteNG.exe")
        guard fileManager.fileExists(atPath: executable.path) else {
            return nil
        }
        return LauncherManifest(
            id: Self.mRemoteNG1782LauncherId,
            appId: "mremoteng-1782-x64",
            bottleId: bottleId,
            displayName: "mRemoteNG 1.78.2",
            exePath: "C:\\macwin-portable\\mremoteng-1782-x64\\mRemoteNG.exe",
            args: Self.mRemoteNG1782Arguments,
            envOverrides: Self.mRemoteNG1782Environment,
            showInHome: true
        )
    }

    private func detectedPortableAppsUtilityLaunchers(in driveC: URL, bottleId: String) -> [LauncherManifest] {
        let baseDirectory = driveC
            .appendingPathComponent("PortableApps", isDirectory: true)
            .appendingPathComponent("PortableApps.com", isDirectory: true)
        let utilities: [(id: String, appId: String, displayName: String, fileName: String)] = [
            (Self.portableAppsBackupLauncherId, "portableapps-utilities", "PortableApps Backup", "PortableAppsBackup.exe"),
            (Self.portableAppsBackupRestoreLauncherId, "portableapps-utilities", "PortableApps Backup Restore", "PortableAppsBackupRestore.exe"),
            (Self.portableAppsUpdaterLauncherId, "portableapps-utilities", "PortableApps Updater", "PortableAppsUpdater.exe")
        ]

        return utilities.compactMap { utility in
            let executable = baseDirectory.appendingPathComponent(utility.fileName)
            guard fileManager.fileExists(atPath: executable.path) else { return nil }
            let windowsPath = "C:\\PortableApps\\PortableApps.com\\\(utility.fileName)"
            var launcher = LauncherManifest(
                id: utility.id,
                appId: utility.appId,
                bottleId: bottleId,
                displayName: utility.displayName,
                exePath: windowsPath,
                args: [],
                envOverrides: [:],
                showInHome: true
            )
            if let profile = ApplicationCompatibilityProfile.matched(exePath: windowsPath) {
                launcher = profile.applied(to: launcher)
            }
            return launcher
        }
    }

    private func genericInstalledLaunchers(
        in driveC: URL,
        bottleId: String,
        excluding knownExecutablePaths: Set<String>
    ) -> [LauncherManifest] {
        let roots = [
            (url: driveC.appendingPathComponent("Program Files", isDirectory: true), windowsPrefix: "C:\\Program Files"),
            (url: driveC.appendingPathComponent("Program Files (x86)", isDirectory: true), windowsPrefix: "C:\\Program Files (x86)"),
            (url: driveC.appendingPathComponent("macwin-portable", isDirectory: true), windowsPrefix: "C:\\macwin-portable")
        ]

        var candidatesByAppDirectory: [String: GenericLauncherCandidate] = [:]
        for root in roots where fileManager.fileExists(atPath: root.url.path) {
            for candidate in executableCandidates(in: root.url, windowsPrefix: root.windowsPrefix, bottleId: bottleId) {
                guard !knownExecutablePaths.contains(normalizedWindowsExecutablePath(candidate.launcher.exePath)) else { continue }
                let key = candidate.deduplicationKey.lowercased()
                if let existing = candidatesByAppDirectory[key], existing.score >= candidate.score {
                    continue
                }
                candidatesByAppDirectory[key] = candidate
            }
        }

        return candidatesByAppDirectory.values
            .sorted {
                if $0.score != $1.score {
                    return $0.score > $1.score
                }
                return $0.launcher.displayName.localizedStandardCompare($1.launcher.displayName) == .orderedAscending
            }
            .prefix(12)
            .map(\.launcher)
    }

    private func executableCandidates(
        in root: URL,
        windowsPrefix: String,
        bottleId: String
    ) -> [GenericLauncherCandidate] {
        guard let enumerator = fileManager.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return []
        }

        var candidates: [GenericLauncherCandidate] = []
        for case let url as URL in enumerator {
            let relativeComponents = relativeComponents(for: url, under: root)
            if relativeComponents.count > 4 {
                enumerator.skipDescendants()
                continue
            }
            guard url.pathExtension.lowercased() == "exe",
                  let values = try? url.resourceValues(forKeys: [.isRegularFileKey]),
                  values.isRegularFile == true,
                  !isIgnoredExecutable(fileName: url.lastPathComponent, relativeComponents: relativeComponents),
                  let appDirectoryName = relativeComponents.first else {
                continue
            }

            let windowsPath = ([windowsPrefix] + relativeComponents).joined(separator: "\\")
            let displayName = genericDisplayName(
                fileName: url.deletingPathExtension().lastPathComponent,
                appDirectoryName: appDirectoryName
            )
            let launcher = LauncherManifest(
                id: "local-\(stableLauncherId(for: windowsPath))",
                appId: "local-\(bottleId)",
                bottleId: bottleId,
                displayName: displayName,
                exePath: windowsPath,
                args: [],
                envOverrides: [:],
                showInHome: true
            )
            let profiledLauncher = ApplicationCompatibilityProfile.matched(exePath: windowsPath)?.applied(to: launcher) ?? launcher
            candidates.append(GenericLauncherCandidate(
                appDirectoryKey: appDirectoryName,
                deduplicationKey: genericLauncherDeduplicationKey(
                    appDirectoryName: appDirectoryName,
                    fileName: url.lastPathComponent,
                    windowsPath: windowsPath
                ),
                launcher: profiledLauncher,
                score: genericExecutableScore(fileName: url.lastPathComponent, appDirectoryName: appDirectoryName, depth: relativeComponents.count)
            ))
        }
        return candidates
    }

    private func relativeComponents(for url: URL, under root: URL) -> [String] {
        let rootPath = root.standardizedFileURL.path
        let path = url.standardizedFileURL.path
        guard path.hasPrefix(rootPath) else { return [] }
        var relative = String(path.dropFirst(rootPath.count))
        if relative.hasPrefix("/") {
            relative.removeFirst()
        }
        return relative.split(separator: "/").map(String.init)
    }

    private func isIgnoredExecutable(fileName: String, relativeComponents: [String]) -> Bool {
        let lowercased = fileName.lowercased()
        let normalizedExecutable = normalizedLauncherToken(
            URL(fileURLWithPath: fileName).deletingPathExtension().lastPathComponent
        )
        if ["remove", "unwise", "maintenancetool"].contains(normalizedExecutable) {
            return true
        }
        let normalizedComponents = relativeComponents.map { normalizedLauncherToken($0) }
        if normalizedComponents.contains("softmakerfreeoffice2024")
            || normalizedComponents.contains("softmakeroffice2024") {
            let executable = normalizedLauncherToken(URL(fileURLWithPath: fileName).deletingPathExtension().lastPathComponent)
            if normalizedComponents.contains("tb")
                && ["7z", "downloader", "tbinst"].contains(executable) {
                return true
            }
        }
        if normalizedComponents.contains("mremoteng1782x64") {
            let executable = normalizedLauncherToken(URL(fileURLWithPath: fileName).deletingPathExtension().lastPathComponent)
            if ["puttyng"].contains(executable) {
                return true
            }
        }
        let ignoredTokens = [
            "unins",
            "uninstall",
            "setup",
            "install",
            "update",
            "updater",
            "helper",
            "crash",
            "report",
            "service",
            "broker",
            "renderer",
            "debug",
            "syspin",
            "downloader",
            "usbstick"
        ]
        return ignoredTokens.contains { lowercased.contains($0) }
    }

    private func genericDisplayName(fileName: String, appDirectoryName: String) -> String {
        let normalizedFileName = fileName.trimmingCharacters(in: .whitespacesAndNewlines)
        let genericNames: Set<String> = ["app", "client", "launcher", "main", "start"]
        if genericNames.contains(normalizedFileName.lowercased()) {
            return appDirectoryName
        }
        return normalizedFileName
    }

    private func genericExecutableScore(fileName: String, appDirectoryName: String, depth: Int) -> Int {
        let normalizedFile = normalizedLauncherToken(URL(fileURLWithPath: fileName).deletingPathExtension().lastPathComponent)
        let normalizedDirectory = normalizedLauncherToken(appDirectoryName)
        var score = max(0, 40 - depth * 4)
        if normalizedFile == normalizedDirectory {
            score += 60
        } else if normalizedFile.contains(normalizedDirectory) || normalizedDirectory.contains(normalizedFile) {
            score += 30
        }
        if ["launcher", "client", "app"].contains(normalizedFile) {
            score += 8
        }
        return score
    }

    private func normalizedLauncherToken(_ value: String) -> String {
        value.lowercased().filter { $0.isLetter || $0.isNumber }
    }

    private func normalizedWindowsExecutablePath(_ value: String) -> String {
        var normalized = value
            .replacingOccurrences(of: "/", with: "\\")
            .lowercased()
        while normalized.contains("\\\\") {
            normalized = normalized.replacingOccurrences(of: "\\\\", with: "\\")
        }
        return normalized
    }

    private func genericLauncherDeduplicationKey(
        appDirectoryName: String,
        fileName: String,
        windowsPath: String
    ) -> String {
        if isMultiLauncherOfficeSuiteExecutable(appDirectoryName: appDirectoryName, fileName: fileName) {
            return windowsPath
        }
        return appDirectoryName
    }

    private func isMultiLauncherOfficeSuiteExecutable(appDirectoryName: String, fileName: String) -> Bool {
        let directory = normalizedLauncherToken(appDirectoryName)
        let executable = normalizedLauncherToken(URL(fileURLWithPath: fileName).deletingPathExtension().lastPathComponent)

        if directory.contains("softmaker") {
            return ["textmaker", "planmaker", "presentations"].contains(executable)
        }
        if directory.contains("libreoffice") {
            return ["soffice", "swriter", "scalc", "simpress", "sdraw", "smath", "sbase"].contains(executable)
        }
        if directory.contains("openoffice") {
            return ["soffice", "swriter", "scalc", "simpress", "sdraw", "smath", "sbase"].contains(executable)
        }
        return false
    }

    private func stableLauncherId(for windowsPath: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
        let slug = windowsPath
            .lowercased()
            .unicodeScalars
            .map { allowed.contains($0) ? Character($0) : "-" }
            .reduce(into: "") { $0.append($1) }
            .split(separator: "-")
            .joined(separator: "-")
        return slug.isEmpty ? UUID().uuidString.lowercased() : slug
    }

    private struct GenericLauncherCandidate {
        var appDirectoryKey: String
        var deduplicationKey: String
        var launcher: LauncherManifest
        var score: Int
    }

    @discardableResult
    private func repairWindowsFontFiles(_ bottle: BottleManifest) throws -> Bool {
        let fontsDirectory = paths.bottleDriveCURL(id: bottle.id)
            .appendingPathComponent("windows", isDirectory: true)
            .appendingPathComponent("Fonts", isDirectory: true)
        try fileManager.createDirectory(at: fontsDirectory, withIntermediateDirectories: true)

        let discoveredFonts = Self.discoverMacFonts(fileManager: fileManager)
        var changed = false
        for link in Self.windowsFontLinks {
            let target = fontsDirectory.appendingPathComponent(link.fileName)
            guard let source = resolvedFontSource(for: link, discoveredFonts: discoveredFonts) else {
                continue
            }
            if (try? fileManager.destinationOfSymbolicLink(atPath: target.path)) != nil {
                let destination = (try? fileManager.destinationOfSymbolicLink(atPath: target.path)) ?? ""
                if destination == source {
                    continue
                }
                try fileManager.removeItem(at: target)
            } else if fileManager.fileExists(atPath: target.path) {
                guard link.replaceExisting else { continue }
                try fileManager.removeItem(at: target)
            }
            try fileManager.createSymbolicLink(atPath: target.path, withDestinationPath: source)
            changed = true
        }
        return changed
    }

    private func resolvedFontSource(for link: WindowsFontLink, discoveredFonts: [String: String]) -> String? {
        for fileName in link.discoveryFileNames {
            if let source = discoveredFonts[fileName.lowercased()],
               fileManager.fileExists(atPath: source) {
                return source
            }
        }
        if let source = link.sourceCandidates.first(where: { fileManager.fileExists(atPath: $0) }) {
            return source
        }
        return nil
    }

    @discardableResult
    private func repairFontConfig(_ bottle: BottleManifest) throws -> Bool {
        let fontConfigURL = Self.fontConfigURL(for: bottle.id, paths: paths)
        let fontDirectories = Self.fontConfigDirectories(for: bottle.id, paths: paths, fileManager: fileManager)
        let repaired = Self.fontConfigText(fontDirectories: fontDirectories)
        if fileManager.fileExists(atPath: fontConfigURL.path),
           (try? String(contentsOf: fontConfigURL, encoding: .utf8)) == repaired {
            return false
        }
        try fileManager.createDirectory(at: fontConfigURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        try repaired.write(to: fontConfigURL, atomically: true, encoding: .utf8)
        return true
    }

    private func repairWebViewRenderingCaches(_ bottle: BottleManifest) throws {
        try repairChromiumBrowserRootDLLs(in: bottle)
        try repairLenovoAppStoreBundledGPUDLLs(in: bottle)
        try repairTencentAndrowsBundledGPUDLLs(in: bottle)

        let usersDirectory = paths.bottleDriveCURL(id: bottle.id).appendingPathComponent("users", isDirectory: true)
        guard fileManager.fileExists(atPath: usersDirectory.path) else { return }
        guard let enumerator = fileManager.enumerator(
            at: usersDirectory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return }

        while let item = enumerator.nextObject() as? URL {
            let values = try? item.resourceValues(forKeys: [.isDirectoryKey])
            guard values?.isDirectory == true else { continue }
            guard !item.path.contains(".macwin-backup-") else {
                enumerator.skipDescendants()
                continue
            }
            if isLenovoWebViewStoreCache(item) {
                try? fileManager.removeItem(at: item)
                enumerator.skipDescendants()
                continue
            }
            if isTencentAndrowsWebViewRenderingCache(item) {
                try? fileManager.removeItem(at: item)
                enumerator.skipDescendants()
                continue
            }
            if isHoYoPlayRootWebViewCache(item) {
                try? fileManager.removeItem(at: item)
                enumerator.skipDescendants()
                continue
            }
            if isHoYoPlayWebViewRenderingCache(item) {
                try? fileManager.removeItem(at: item)
                enumerator.skipDescendants()
                continue
            }
            guard Self.webViewRenderingCacheDirectoryNames.contains(item.lastPathComponent) else { continue }
            try? fileManager.removeItem(at: item)
            enumerator.skipDescendants()
        }
    }

    private func repairLenovoAppStoreBundledGPUDLLs(in bottle: BottleManifest) throws {
        let appDirectory = paths.bottleDriveCURL(id: bottle.id)
            .appendingPathComponent("Program Files (x86)", isDirectory: true)
            .appendingPathComponent("Lenovo", isDirectory: true)
            .appendingPathComponent("LeAppStore", isDirectory: true)
        guard fileManager.fileExists(atPath: appDirectory.appendingPathComponent("LenovoAppStore.exe").path) else {
            return
        }

        let disabledRoot = appDirectory.appendingPathComponent(Self.disabledBundledGPUDLLDirectoryName, isDirectory: true)
        try disableBundledGPUDLLs(in: appDirectory, movingTo: disabledRoot)

        let swiftShaderDirectory = appDirectory.appendingPathComponent("swiftshader", isDirectory: true)
        if fileManager.fileExists(atPath: swiftShaderDirectory.path) {
            try disableBundledGPUDLLs(
                in: swiftShaderDirectory,
                movingTo: disabledRoot.appendingPathComponent("swiftshader", isDirectory: true)
            )
        }
    }

    private func repairTencentAndrowsBundledGPUDLLs(in bottle: BottleManifest) throws {
        let androwsDirectory = paths.bottleDriveCURL(id: bottle.id)
            .appendingPathComponent("Program Files", isDirectory: true)
            .appendingPathComponent("Tencent", isDirectory: true)
            .appendingPathComponent("Androws", isDirectory: true)
        guard fileManager.fileExists(atPath: androwsDirectory.path) else {
            return
        }

        guard let enumerator = fileManager.enumerator(
            at: androwsDirectory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { return }

        while let directory = enumerator.nextObject() as? URL {
            let values = try? directory.resourceValues(forKeys: [.isDirectoryKey])
            guard values?.isDirectory == true else { continue }
            if directory.lastPathComponent == Self.disabledBundledGPUDLLDirectoryName {
                enumerator.skipDescendants()
                continue
            }
            let disabledRoot = directory.appendingPathComponent(Self.disabledBundledGPUDLLDirectoryName, isDirectory: true)
            try disableBundledGPUDLLs(in: directory, movingTo: disabledRoot)
        }
    }

    private func disableBundledGPUDLLs(in directory: URL, movingTo disabledDirectory: URL) throws {
        var didCreateDisabledDirectory = false
        for fileName in Self.bundledGPUDLLNames {
            let source = directory.appendingPathComponent(fileName)
            guard fileManager.fileExists(atPath: source.path) else { continue }
            if !didCreateDisabledDirectory {
                try fileManager.createDirectory(at: disabledDirectory, withIntermediateDirectories: true)
                didCreateDisabledDirectory = true
            }
            let destination = disabledDirectory.appendingPathComponent(fileName)
            if fileManager.fileExists(atPath: destination.path) {
                try? fileManager.removeItem(at: destination)
            }
            try fileManager.moveItem(at: source, to: destination)
        }
    }

    private func repairChromiumBrowserRootDLLs(in bottle: BottleManifest) throws {
        let driveC = paths.bottleDriveCURL(id: bottle.id)
        guard fileManager.fileExists(atPath: driveC.path),
              let enumerator = fileManager.enumerator(
                at: driveC,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
              ) else { return }

        while let item = enumerator.nextObject() as? URL {
            let values = try? item.resourceValues(forKeys: [.isDirectoryKey])
            guard values?.isDirectory == true else { continue }
            let lowercasedPath = item.path.replacingOccurrences(of: "\\", with: "/").lowercased()
            if lowercasedPath.contains("/windows/") {
                enumerator.skipDescendants()
                continue
            }
            guard item.lastPathComponent == "Application",
                  isChromiumApplicationDirectory(item),
                  let versionDirectory = chromiumVersionDirectory(in: item) else {
                continue
            }

            for fileName in Self.chromiumRootDLLNames {
                let source = versionDirectory.appendingPathComponent(fileName)
                guard fileManager.fileExists(atPath: source.path) else { continue }
                let destination = item.appendingPathComponent(fileName)
                if fileManager.fileExists(atPath: destination.path) {
                    continue
                }
                try? fileManager.copyItem(at: source, to: destination)
            }
            enumerator.skipDescendants()
        }
    }

    @discardableResult
    private func repairFreeCADPythonUnameShim(_ bottle: BottleManifest) throws -> Bool {
        let driveC = paths.bottleDriveCURL(id: bottle.id)
        guard fileManager.fileExists(atPath: driveC.path),
              let enumerator = fileManager.enumerator(
                at: driveC,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
              ) else { return false }

        var changed = false
        while let item = enumerator.nextObject() as? URL {
            let values = try? item.resourceValues(forKeys: [.isDirectoryKey])
            guard values?.isDirectory == true else { continue }
            let lowercasedPath = item.path.replacingOccurrences(of: "\\", with: "/").lowercased()
            if lowercasedPath.contains("/windows/") || lowercasedPath.contains("/appdata/") {
                enumerator.skipDescendants()
                continue
            }
            guard item.lastPathComponent == "Lib",
                  lowercasedPath.contains("/freecad"),
                  fileManager.fileExists(atPath: item.appendingPathComponent("platform.py").path) else {
                continue
            }
            let shimURL = item.appendingPathComponent("sitecustomize.py")
            let shimText = Self.freeCADPythonUnameShimText
            if fileManager.fileExists(atPath: shimURL.path),
               (try? String(contentsOf: shimURL, encoding: .utf8)) == shimText {
                enumerator.skipDescendants()
                continue
            }
            try shimText.write(to: shimURL, atomically: true, encoding: .utf8)
            changed = true
            enumerator.skipDescendants()
        }
        return changed
    }

    private func isChromiumApplicationDirectory(_ directory: URL) -> Bool {
        ["brave.exe", "chrome.exe", "msedge.exe", "vivaldi.exe"].contains { fileName in
            fileManager.fileExists(atPath: directory.appendingPathComponent(fileName).path)
        }
    }

    private func chromiumVersionDirectory(in applicationDirectory: URL) -> URL? {
        let directories = (try? fileManager.contentsOfDirectory(
            at: applicationDirectory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        return directories
            .filter { directory in
                let values = try? directory.resourceValues(forKeys: [.isDirectoryKey])
                guard values?.isDirectory == true else { return false }
                return Self.chromiumRootDLLNames.contains { fileName in
                    fileManager.fileExists(atPath: directory.appendingPathComponent(fileName).path)
                }
            }
            .sorted { lhs, rhs in
                lhs.lastPathComponent.localizedStandardCompare(rhs.lastPathComponent) == .orderedDescending
            }
            .first
    }

    private func isLenovoWebViewStoreCache(_ url: URL) -> Bool {
        let normalizedPath = url.path.replacingOccurrences(of: "\\", with: "/").lowercased()
        return normalizedPath.contains("/appdata/local/lenovo/leappstore/storecache")
    }

    private func isTencentAndrowsWebViewRenderingCache(_ url: URL) -> Bool {
        let normalizedPath = url.path.replacingOccurrences(of: "\\", with: "/").lowercased()
        guard normalizedPath.contains("/appdata/roaming/tencent/androws/cef/") else { return false }
        return normalizedPath.contains("/cef_androws")
            || Self.webViewRenderingCacheDirectoryNames.contains(url.lastPathComponent)
    }

    private func isHoYoPlayRootWebViewCache(_ url: URL) -> Bool {
        let normalizedPath = url.path.replacingOccurrences(of: "\\", with: "/").lowercased()
        return normalizedPath.contains("/appdata/roaming/mihoyo/hyp/")
            && normalizedPath.hasSuffix("/cache")
    }

    private func isHoYoPlayWebViewRenderingCache(_ url: URL) -> Bool {
        let normalizedPath = url.path.replacingOccurrences(of: "\\", with: "/").lowercased()
        guard normalizedPath.contains("/appdata/roaming/mihoyo/hyp/") else { return false }
        let cacheNames: Set<String> = [
            "cache",
            "cache_data",
            "code cache",
            "dawncache",
            "dawnwebgpucache",
            "graphitedawncache",
            "grshadercache",
            "gpucache",
            "shadercache"
        ]
        if cacheNames.contains(url.lastPathComponent.lowercased()) {
            return true
        }
        return normalizedPath.hasSuffix("/service worker/cachestorage")
    }

    @discardableResult
    private func repairRegistryCompatibility(_ bottle: BottleManifest) throws -> Bool {
        let windowsUserName = inferredWindowsUserName(for: bottle)
        var changed = false
        let systemRegistry = paths.bottleDirectory(id: bottle.id).appendingPathComponent("system.reg")
        if fileManager.fileExists(atPath: systemRegistry.path) {
            let original = try String(contentsOf: systemRegistry, encoding: .utf8)
            var repaired = Self.registryText(
                original,
                removingServices: Self.removedKernelServices
            )
            repaired = Self.registryText(
                repaired,
                disablingServices: Self.disabledBackgroundServices
            )
            repaired = Self.registryTextWithMMDeviceRepairs(repaired)
            repaired = Self.registryTextWithNetworkListManagerRepairs(repaired)
            repaired = Self.registryTextWithFileDialogRepairs(repaired)
            repaired = Self.registryTextWithCryptoProviderRepairs(repaired)
            repaired = Self.registryTextWithFontRepairs(repaired)
            repaired = Self.registryTextWithFontLinkRepairs(repaired)
            repaired = Self.registryTextWithCOMProxyRepairs(repaired)
            repaired = Self.registryTextWithTaskSchedulerRepairs(repaired)
            repaired = Self.registryTextWithWinRTActivationRepairs(repaired)
            repaired = Self.registryTextWithCommonShellFolderRepairs(repaired)
            if repaired != original {
                try repaired.write(to: systemRegistry, atomically: true, encoding: .utf8)
                changed = true
            }
        }

        let userRegistry = paths.bottleDirectory(id: bottle.id).appendingPathComponent("user.reg")
        guard fileManager.fileExists(atPath: userRegistry.path) else { return changed }
        let original = try String(contentsOf: userRegistry, encoding: .utf8)
        var repaired = Self.registryText(
            original,
            settingDWORD: Self.wineDbgShowCrashDialogValue,
            value: 0,
            inSection: Self.wineDbgRegistrySection
        )
        repaired = Self.registryTextWithShellFolderRepairs(repaired, windowsUserName: windowsUserName)
        repaired = Self.registryTextWithFontRepairs(repaired)
        repaired = Self.registryTextWithWindowMetricsFontRepairs(repaired)
        repaired = Self.registryTextWithMacDriverInputRepairs(repaired)
        repaired = Self.registryTextWithCOMProxyRepairs(repaired)
        repaired = Self.registryTextWithTaskSchedulerRepairs(repaired)
        guard repaired != original else { return changed }
        try repaired.write(to: userRegistry, atomically: true, encoding: .utf8)
        return true
    }

    @discardableResult
    private func repairUserShellDirectories(_ bottle: BottleManifest) throws -> Bool {
        let userName = inferredWindowsUserName(for: bottle)
        let userDirectory = paths.bottleDriveCURL(id: bottle.id)
            .appendingPathComponent("users", isDirectory: true)
            .appendingPathComponent(userName, isDirectory: true)
        var changed = false
        for relativePath in Self.userShellDirectoryRelativePaths {
            let directory = userDirectory.appendingPathComponent(relativePath, isDirectory: true)
            if !fileManager.fileExists(atPath: directory.path) {
                try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
                changed = true
            }
        }
        return changed
    }

    @discardableResult
    private func repairCommonShellDirectories(_ bottle: BottleManifest) throws -> Bool {
        let driveC = paths.bottleDriveCURL(id: bottle.id)
        var changed = false
        for relativePath in Self.commonShellDirectoryRelativePaths {
            let directory = driveC.appendingPathComponent(relativePath, isDirectory: true)
            if !fileManager.fileExists(atPath: directory.path) {
                try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
                changed = true
            }
        }
        return changed
    }

    private func inferredWindowsUserName(for bottle: BottleManifest) -> String {
        let usersDirectory = paths.bottleDriveCURL(id: bottle.id).appendingPathComponent("users", isDirectory: true)
        let candidates = (try? fileManager.contentsOfDirectory(
            at: usersDirectory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        let ignored: Set<String> = ["all users", "default", "default user", "public"]
        if let directory = candidates
            .filter({
                let values = try? $0.resourceValues(forKeys: [.isDirectoryKey])
                return values?.isDirectory == true && !ignored.contains($0.lastPathComponent.lowercased())
            })
            .sorted(by: { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending })
            .first {
            return directory.lastPathComponent
        }
        return ProcessInfo.processInfo.environment["USER"].flatMap { $0.isEmpty ? nil : $0 } ?? "user"
    }

    public static func registryText(_ text: String, removingServices services: Set<String>) -> String {
        var output: [String] = []
        var shouldDropSection = false
        var changed = false

        for line in text.components(separatedBy: .newlines) {
            if line.hasPrefix("[") {
                shouldDropSection = shouldRemoveRegistrySection(line, removingServices: services)
                if shouldDropSection {
                    changed = true
                    continue
                }
            }

            if shouldDropSection {
                changed = true
                continue
            }
            output.append(line)
        }

        return changed ? output.joined(separator: "\n") : text
    }

    public static func registryText(_ text: String, disablingServices services: Set<String>) -> String {
        let normalizedServices = Set(services.map { $0.lowercased() })
        var output: [String] = []
        var isInDisabledServiceSection = false
        var wroteStartValue = false
        var changed = false
        let disabledStartLine = "\"Start\"=dword:00000004"

        func finishServiceSectionIfNeeded() {
            if isInDisabledServiceSection, !wroteStartValue {
                output.append(disabledStartLine)
                wroteStartValue = true
                changed = true
            }
        }

        for line in text.components(separatedBy: .newlines) {
            if let sectionName = registrySectionName(line) {
                finishServiceSectionIfNeeded()
                isInDisabledServiceSection = serviceName(fromRegistrySection: sectionName)
                    .map { normalizedServices.contains($0.lowercased()) } == true
                wroteStartValue = false
                output.append(line)
                continue
            }

            if isInDisabledServiceSection, line.hasPrefix("\"Start\"=") {
                output.append(disabledStartLine)
                wroteStartValue = true
                if line != disabledStartLine {
                    changed = true
                }
                continue
            }

            output.append(line)
        }

        finishServiceSectionIfNeeded()
        return changed ? output.joined(separator: "\n") : text
    }

    public static func registryText(
        _ text: String,
        settingDWORD valueName: String,
        value: UInt32,
        inSection sectionName: String
    ) -> String {
        let valueLine = "\"\(valueName)\"=dword:\(String(format: "%08x", value))"
        var output: [String] = []
        var isInTargetSection = false
        var foundTargetSection = false
        var wroteValueInTargetSection = false
        var skipsReplacedValueContinuation = false
        var changed = false

        func finishTargetSectionIfNeeded() {
            if isInTargetSection, !wroteValueInTargetSection {
                output.append(valueLine)
                wroteValueInTargetSection = true
                changed = true
            }
        }

        for line in text.components(separatedBy: .newlines) {
            if skipsReplacedValueContinuation {
                if Self.isRegistryContinuationLine(line) {
                    skipsReplacedValueContinuation = line.hasSuffix("\\")
                    changed = true
                    continue
                }
                skipsReplacedValueContinuation = false
            }

            if let currentSection = registrySectionName(line) {
                finishTargetSectionIfNeeded()
                isInTargetSection = currentSection == sectionName
                if isInTargetSection {
                    foundTargetSection = true
                    wroteValueInTargetSection = false
                }
                output.append(line)
                continue
            }

            if isInTargetSection, line.hasPrefix("\"\(valueName)\"=") {
                output.append(valueLine)
                wroteValueInTargetSection = true
                if line != valueLine {
                    changed = true
                }
                skipsReplacedValueContinuation = line.hasSuffix("\\")
                continue
            }

            output.append(line)
        }

        finishTargetSectionIfNeeded()

        if !foundTargetSection {
            if output.last?.isEmpty == false {
                output.append("")
            }
            output.append("[\(sectionName)]")
            output.append(valueLine)
            changed = true
        }

        return changed ? output.joined(separator: "\n") : text
    }

    public static func registryText(
        _ text: String,
        settingString valueName: String?,
        value: String,
        inSection sectionName: String
    ) -> String {
        let valueLine = "\(registryValueName(valueName))=\"\(registryEscapedString(value))\""
        var output: [String] = []
        var isInTargetSection = false
        var foundTargetSection = false
        var wroteValueInTargetSection = false
        var skipsReplacedValueContinuation = false
        var changed = false

        func finishTargetSectionIfNeeded() {
            if isInTargetSection, !wroteValueInTargetSection {
                output.append(valueLine)
                wroteValueInTargetSection = true
                changed = true
            }
        }

        for line in text.components(separatedBy: .newlines) {
            if skipsReplacedValueContinuation {
                if Self.isRegistryContinuationLine(line) {
                    skipsReplacedValueContinuation = line.hasSuffix("\\")
                    changed = true
                    continue
                }
                skipsReplacedValueContinuation = false
            }

            if let currentSection = registrySectionName(line) {
                finishTargetSectionIfNeeded()
                isInTargetSection = currentSection == sectionName
                if isInTargetSection {
                    foundTargetSection = true
                    wroteValueInTargetSection = false
                }
                output.append(line)
                continue
            }

            if isInTargetSection, line.hasPrefix("\(registryValueName(valueName))=") {
                output.append(valueLine)
                wroteValueInTargetSection = true
                if line != valueLine {
                    changed = true
                }
                skipsReplacedValueContinuation = line.hasSuffix("\\")
                continue
            }

            output.append(line)
        }

        finishTargetSectionIfNeeded()

        if !foundTargetSection {
            if output.last?.isEmpty == false {
                output.append("")
            }
            output.append("[\(sectionName)]")
            output.append(valueLine)
            changed = true
        }

        return changed ? output.joined(separator: "\n") : text
    }

    private static func registryText(
        _ text: String,
        settingMultiString valueName: String,
        values: [String],
        inSection sectionName: String
    ) -> String {
        let encodedValues = values.map { registryEscapedString($0) }.joined(separator: "\\0")
        let valueLine = "\"\(valueName)\"=str(7):\"\(encodedValues)\\0\""
        var output: [String] = []
        var isInTargetSection = false
        var foundTargetSection = false
        var wroteValueInTargetSection = false
        var skipsReplacedValueContinuation = false
        var changed = false

        func finishTargetSectionIfNeeded() {
            if isInTargetSection, !wroteValueInTargetSection {
                output.append(valueLine)
                wroteValueInTargetSection = true
                changed = true
            }
        }

        for line in text.components(separatedBy: .newlines) {
            if skipsReplacedValueContinuation {
                if Self.isRegistryContinuationLine(line) {
                    skipsReplacedValueContinuation = line.hasSuffix("\\")
                    changed = true
                    continue
                }
                skipsReplacedValueContinuation = false
            }

            if let currentSection = registrySectionName(line) {
                finishTargetSectionIfNeeded()
                isInTargetSection = currentSection == sectionName
                if isInTargetSection {
                    foundTargetSection = true
                    wroteValueInTargetSection = false
                }
                output.append(line)
                continue
            }

            if isInTargetSection, line.hasPrefix("\"\(valueName)\"=") {
                output.append(valueLine)
                wroteValueInTargetSection = true
                if line != valueLine {
                    changed = true
                }
                skipsReplacedValueContinuation = line.hasSuffix("\\")
                continue
            }

            output.append(line)
        }

        finishTargetSectionIfNeeded()

        if !foundTargetSection {
            if output.last?.isEmpty == false {
                output.append("")
            }
            output.append("[\(sectionName)]")
            output.append(valueLine)
            changed = true
        }

        return changed ? output.joined(separator: "\n") : text
    }

    public static func registryTextWithFontRepairs(_ text: String) -> String {
        var repaired = text
        for (valueName, value) in Self.fontRegistryValues {
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: value,
                inSection: Self.fontRegistrySection
            )
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: value,
                inSection: Self.currentVersionFontRegistrySection
            )
        }
        for section in [
            Self.fontSubstitutesRegistrySection,
            Self.wineFontReplacementsRegistrySection
        ] {
            repaired = Self.registryText(
                repaired,
                removingValueNames: Self.obsoleteFontSubstituteValueNames,
                inSection: section
            )
        }
        for (valueName, value) in Self.fontSubstituteValues {
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: value,
                inSection: Self.fontSubstitutesRegistrySection
            )
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: value,
                inSection: Self.wineFontReplacementsRegistrySection
            )
        }
        return repaired
    }

    public static func registryTextWithFontLinkRepairs(_ text: String) -> String {
        Self.fontLinkValues.reduce(text) { repaired, entry in
            Self.registryText(
                repaired,
                settingMultiString: entry.valueName,
                values: entry.values,
                inSection: Self.fontLinkRegistrySection
            )
        }
    }

    public static func registryTextWithWindowMetricsFontRepairs(_ text: String) -> String {
        let encodedLogFont = Self.registryEncodedLogFont(faceName: "Tahoma")
        return Self.windowMetricsFontValueNames.reduce(text) { repaired, valueName in
            Self.registryText(
                repaired,
                settingEncodedValue: valueName,
                encodedValue: encodedLogFont,
                inSection: Self.windowMetricsRegistrySection
            )
        }
    }

    private static func registryText(
        _ text: String,
        settingEncodedValue valueName: String,
        encodedValue: String,
        inSection sectionName: String
    ) -> String {
        let valueLine = "\"\(valueName)\"=\(encodedValue)"
        var output: [String] = []
        var isInTargetSection = false
        var foundTargetSection = false
        var wroteValueInTargetSection = false
        var skipsReplacedValueContinuation = false
        var changed = false

        func finishTargetSectionIfNeeded() {
            if isInTargetSection, !wroteValueInTargetSection {
                output.append(valueLine)
                wroteValueInTargetSection = true
                changed = true
            }
        }

        for line in text.components(separatedBy: .newlines) {
            if skipsReplacedValueContinuation {
                if Self.isRegistryContinuationLine(line) {
                    skipsReplacedValueContinuation = line.hasSuffix("\\")
                    changed = true
                    continue
                }
                skipsReplacedValueContinuation = false
            }

            if let currentSection = registrySectionName(line) {
                finishTargetSectionIfNeeded()
                isInTargetSection = currentSection == sectionName
                if isInTargetSection {
                    foundTargetSection = true
                    wroteValueInTargetSection = false
                }
                output.append(line)
                continue
            }

            if isInTargetSection, line.hasPrefix("\"\(valueName)\"=") {
                output.append(valueLine)
                wroteValueInTargetSection = true
                if line != valueLine {
                    changed = true
                }
                skipsReplacedValueContinuation = line.hasSuffix("\\")
                continue
            }

            output.append(line)
        }

        finishTargetSectionIfNeeded()

        if !foundTargetSection {
            if output.last?.isEmpty == false {
                output.append("")
            }
            output.append("[\(sectionName)]")
            output.append(valueLine)
            changed = true
        }

        return changed ? output.joined(separator: "\n") : text
    }

    private static func registryEncodedLogFont(
        faceName: String,
        height: Int32 = -12,
        weight: Int32 = 400
    ) -> String {
        var data = Data()

        func appendInt32(_ value: Int32) {
            var littleEndian = value.littleEndian
            withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
        }

        func appendUInt16(_ value: UInt16) {
            var littleEndian = value.littleEndian
            withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
        }

        appendInt32(height)
        appendInt32(0)
        appendInt32(0)
        appendInt32(0)
        appendInt32(weight)
        data.append(contentsOf: [0, 0, 0, 1, 0, 0, 5, 32])

        let faceUnits = Array(faceName.utf16.prefix(31))
        for unit in faceUnits {
            appendUInt16(unit)
        }
        appendUInt16(0)
        while data.count < 92 {
            data.append(0)
        }

        return "hex:" + data.map { String(format: "%02x", $0) }.joined(separator: ",")
    }

    public static func registryTextWithMacDriverInputRepairs(
        _ text: String,
        borderlessAppMode: Bool = false,
        retinaMode: Bool = false
    ) -> String {
        let macDriverSection = "Software\\\\Wine\\\\Mac Driver"
        let directInputSection = "Software\\\\Wine\\\\DirectInput"
        let x11DriverSection = "Software\\\\Wine\\\\X11 Driver"
        var repaired = text
        repaired = Self.registryText(repaired, removingValueNames: ["MouseWarpOverride"], inSection: macDriverSection)
        repaired = Self.registryText(repaired, settingString: "Managed", value: "Y", inSection: macDriverSection)
        repaired = Self.registryText(repaired, settingString: "Decorated", value: borderlessAppMode ? "N" : "Y", inSection: macDriverSection)
        repaired = Self.registryText(repaired, settingString: "UseTakeFocus", value: "Y", inSection: macDriverSection)
        repaired = Self.registryText(repaired, settingString: "GrabFullscreen", value: "N", inSection: macDriverSection)
        repaired = Self.registryText(repaired, settingString: "WindowsFloatWhenInactive", value: "all", inSection: macDriverSection)
        repaired = Self.registryText(repaired, settingString: "RetinaMode", value: retinaMode ? "Y" : "N", inSection: macDriverSection)
        repaired = Self.registryText(
            repaired,
            settingDWORD: Self.wineFontsLogPixelsValue,
            value: retinaMode ? Self.retinaWineDPI : Self.standardWineDPI,
            inSection: Self.wineFontsRegistrySection
        )
        repaired = Self.registryText(repaired, settingString: "MouseWarpOverride", value: "disable", inSection: directInputSection)
        repaired = Self.registryText(repaired, settingString: "Managed", value: "Y", inSection: x11DriverSection)
        repaired = Self.registryText(repaired, settingString: "Decorated", value: borderlessAppMode ? "N" : "Y", inSection: x11DriverSection)
        repaired = Self.registryText(repaired, settingString: "UseTakeFocus", value: "Y", inSection: x11DriverSection)
        repaired = Self.registryText(repaired, settingString: "GrabFullscreen", value: "N", inSection: x11DriverSection)
        return repaired
    }

    public static func registryTextWithMuseScoreFirstLaunchRepairs(_ text: String) -> String {
        var repaired = text
        for root in Self.museScoreSettingsRegistryRoots {
            repaired = Self.registryText(
                repaired,
                removingValueNames: Self.museScoreFlattenedSettingsValueNames,
                inSection: root
            )
        }
        for root in Self.museScoreSettingsRegistryRoots {
            repaired = Self.registryText(repaired, settingDWORD: "hasCompletedFirstLaunchSetup", value: 1, inSection: "\(root)\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "welcomeDialogShowOnStartup", value: 0, inSection: "\(root)\\\\application")
            repaired = Self.registryText(repaired, settingString: "welcomeDialogLastShownVersion", value: "999.999.999", inSection: "\(root)\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "welcomeDialogLastShownIndex", value: 999, inSection: "\(root)\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "modeStart", value: 0, inSection: "\(root)\\\\application\\\\startup")
            repaired = Self.registryText(repaired, settingString: "startScore", value: "", inSection: "\(root)\\\\application\\\\startup")
            repaired = Self.registryText(repaired, settingString: "currentThemeCode", value: "light", inSection: "\(root)\\\\ui\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "followSystemTheme", value: 0, inSection: "\(root)\\\\ui\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "highContrastEnabled", value: 0, inSection: "\(root)\\\\ui\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "currentAccentColorIndex", value: 4, inSection: "\(root)\\\\ui\\\\application")
            repaired = Self.registryText(repaired, settingDWORD: "showSplashScreen", value: 0, inSection: "\(root)\\\\ui\\\\application\\\\startup")
            repaired = Self.registryText(repaired, settingString: "fontFamily", value: "Arial", inSection: "\(root)\\\\ui\\\\theme")
            repaired = Self.registryText(repaired, settingDWORD: "fontSize", value: 12, inSection: "\(root)\\\\ui\\\\theme")
            repaired = Self.registryText(repaired, settingDWORD: "finished", value: 1, inSection: "\(root)\\\\gettingstarted")
            repaired = Self.registryText(repaired, settingDWORD: "currentPageIndex", value: 999, inSection: "\(root)\\\\gettingstarted")
            repaired = Self.registryText(repaired, settingDWORD: "finished", value: 1, inSection: "\(root)\\\\gettingStarted")
            repaired = Self.registryText(repaired, settingDWORD: "currentPageIndex", value: 999, inSection: "\(root)\\\\gettingStarted")
            repaired = Self.registryText(repaired, settingDWORD: "finished", value: 1, inSection: "\(root)\\\\onboarding")
            repaired = Self.registryText(repaired, settingDWORD: "currentPageIndex", value: 999, inSection: "\(root)\\\\onboarding")
        }
        return repaired
    }

    public static let museScoreSettingsRegistryRoots = [
        "Software\\\\MuseScore\\\\MuseScore Studio",
        "Software\\\\MuseScore\\\\MuseScore 4",
        "Software\\\\MuseScore\\\\MuseScore4",
        "Software\\\\MuseScore\\\\MuseScoreStudio4",
        "Software\\\\MuseScore\\\\MuseScore Studio 4",
        "Software\\\\MuseScore\\\\MuseScore Studio 4 stable",
        "Software\\\\MuseScore\\\\MuseScore Studio\\\\appshell",
        "Software\\\\MuseScore\\\\MuseScore 4\\\\appshell",
        "Software\\\\MuseScore\\\\MuseScore4\\\\appshell",
        "Software\\\\MuseScore\\\\MuseScoreStudio4\\\\appshell",
        "Software\\\\MuseScore\\\\MuseScore Studio 4\\\\appshell",
        "Software\\\\MuseScore\\\\MuseScore Studio 4 stable\\\\appshell"
    ]

    private static let museScoreFlattenedSettingsValueNames: Set<String> = [
        "applicationhasCompletedFirstLaunchSetup",
        "applicationstartupmodeStart",
        "applicationstartupstartScore",
        "applicationwelcomeDialogLastShownIndex",
        "applicationwelcomeDialogLastShownVersion",
        "applicationwelcomeDialogShowOnStartup",
        "tourslastShownTours",
        "uiapplicationcurrentThemeCode",
        "uiapplicationcurrentAccentColorIndex",
        "uiapplicationfollowSystemTheme",
        "uiapplicationhighContrastEnabled",
        "uiapplicationstartupshowSplashScreen",
        "ui\\application\\followSystemTheme",
        "ui\\applicationcurrentAccentColorIndex",
        "ui\\applicationcurrentThemeCode",
        "ui\\applicationhighContrastEnabled",
        "ui\\applicationstartupshowSplashScreen",
        "ui\\theme\\fontFamily",
        "ui\\theme\\fontSize",
        "uithemefontFamily",
        "uithemefontSize"
    ]

    public static func registryTextWithCOMProxyRepairs(_ text: String) -> String {
        var repaired = text
        for repair in [
            (
                interfaceSection: Self.serviceProviderInterfaceSection,
                proxyStubSection: Self.serviceProviderProxyStubSection,
                numMethodsSection: Self.serviceProviderNumMethodsSection
            ),
            (
                interfaceSection: Self.serviceProviderWow64InterfaceSection,
                proxyStubSection: Self.serviceProviderWow64ProxyStubSection,
                numMethodsSection: Self.serviceProviderWow64NumMethodsSection
            )
        ] {
            repaired = Self.registryText(
                repaired,
                settingString: nil,
                value: "IServiceProvider",
                inSection: repair.interfaceSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: "ProxyStubClsid32",
                value: "{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}",
                inSection: repair.interfaceSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: "NumMethods",
                value: "4",
                inSection: repair.interfaceSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: nil,
                value: "{B8DA6310-E19B-11D0-933C-00A0C90DCAA9}",
                inSection: repair.proxyStubSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: nil,
                value: "4",
                inSection: repair.numMethodsSection
            )
        }
        repaired = Self.registryTextWithProxyClass(
            repaired,
            classSection: Self.activeScriptStatsProxyClassSection,
            inprocSection: Self.activeScriptStatsProxyInprocSection,
            modulePath: "C:\\windows\\system32\\actxprxy.dll"
        )
        repaired = Self.registryTextWithProxyClass(
            repaired,
            classSection: Self.activeScriptStatsProxyWow64ClassSection,
            inprocSection: Self.activeScriptStatsProxyWow64InprocSection,
            modulePath: "C:\\windows\\syswow64\\actxprxy.dll"
        )
        return repaired
    }

    public static func registryTextWithWinRTActivationRepairs(_ text: String) -> String {
        var repaired = text
        for (className, dllName) in Self.winRTActivationClasses {
            let nativeSection = "Software\\\\Microsoft\\\\WindowsRuntime\\\\ActivatableClassId\\\\\(className)"
            let wow64Section = "Software\\\\Wow6432Node\\\\Microsoft\\\\WindowsRuntime\\\\ActivatableClassId\\\\\(className)"
            repaired = Self.registryText(
                repaired,
                settingString: nil,
                value: className,
                inSection: nativeSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: "DllPath",
                value: "C:\\windows\\system32\\\(dllName)",
                inSection: nativeSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: nil,
                value: className,
                inSection: wow64Section
            )
            repaired = Self.registryText(
                repaired,
                settingString: "DllPath",
                value: "C:\\windows\\syswow64\\\(dllName)",
                inSection: wow64Section
            )
        }
        return repaired
    }

    public static func registryTextWithTaskSchedulerRepairs(_ text: String) -> String {
        var repaired = Self.registryTextWithProxyClass(
            text,
            classSection: Self.taskSchedulerClassSection,
            inprocSection: Self.taskSchedulerInprocSection,
            modulePath: "C:\\windows\\system32\\taskschd.dll"
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "TaskScheduler class",
            inSection: Self.taskSchedulerClassSection
        )
        repaired = Self.registryTextWithProxyClass(
            repaired,
            classSection: Self.taskSchedulerWow64ClassSection,
            inprocSection: Self.taskSchedulerWow64InprocSection,
            modulePath: "C:\\windows\\syswow64\\taskschd.dll"
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "TaskScheduler class",
            inSection: Self.taskSchedulerWow64ClassSection
        )
        repaired = Self.registryTextWithProxyClass(
            repaired,
            classSection: Self.legacyTaskSchedulerClassSection,
            inprocSection: Self.legacyTaskSchedulerInprocSection,
            modulePath: "C:\\windows\\system32\\mstask.dll"
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "CTaskScheduler class",
            inSection: Self.legacyTaskSchedulerClassSection
        )
        repaired = Self.registryTextWithProxyClass(
            repaired,
            classSection: Self.legacyTaskSchedulerWow64ClassSection,
            inprocSection: Self.legacyTaskSchedulerWow64InprocSection,
            modulePath: "C:\\windows\\syswow64\\mstask.dll"
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "CTaskScheduler class",
            inSection: Self.legacyTaskSchedulerWow64ClassSection
        )
        repaired = Self.registryText(
            repaired,
            settingDWORD: "Type",
            value: 32,
            inSection: Self.scheduleServiceSection
        )
        repaired = Self.registryText(
            repaired,
            settingDWORD: "Start",
            value: 2,
            inSection: Self.scheduleServiceSection
        )
        repaired = Self.registryText(
            repaired,
            settingDWORD: "ErrorControl",
            value: 1,
            inSection: Self.scheduleServiceSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ImagePath",
            value: "C:\\windows\\system32\\svchost.exe -k netsvcs",
            inSection: Self.scheduleServiceSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "DisplayName",
            value: "Task Scheduler",
            inSection: Self.scheduleServiceSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ObjectName",
            value: "LocalSystem",
            inSection: Self.scheduleServiceSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ServiceDll",
            value: "C:\\windows\\system32\\schedsvc.dll",
            inSection: Self.scheduleServiceParametersSection
        )
        return repaired
    }

    public static func registryTextWithMMDeviceRepairs(_ text: String) -> String {
        var repaired = Self.registryText(
            text,
            settingString: nil,
            value: "MMDeviceEnumerator class",
            inSection: Self.mmDeviceEnumeratorClassSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "C:\\windows\\system32\\mmdevapi.dll",
            inSection: Self.mmDeviceEnumeratorInprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ThreadingModel",
            value: "Both",
            inSection: Self.mmDeviceEnumeratorInprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "MMDeviceEnumerator class",
            inSection: Self.mmDeviceEnumeratorWow64ClassSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "C:\\windows\\syswow64\\mmdevapi.dll",
            inSection: Self.mmDeviceEnumeratorWow64InprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ThreadingModel",
            value: "Both",
            inSection: Self.mmDeviceEnumeratorWow64InprocSection
        )
        return repaired
    }

    public static func registryTextWithNetworkListManagerRepairs(_ text: String) -> String {
        var repaired = Self.registryText(
            text,
            settingString: nil,
            value: "NetworkListManager",
            inSection: Self.networkListManagerClassSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "C:\\windows\\system32\\netprofm.dll",
            inSection: Self.networkListManagerInprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ThreadingModel",
            value: "Both",
            inSection: Self.networkListManagerInprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "NetworkListManager",
            inSection: Self.networkListManagerWow64ClassSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: "C:\\windows\\syswow64\\netprofm.dll",
            inSection: Self.networkListManagerWow64InprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ThreadingModel",
            value: "Both",
            inSection: Self.networkListManagerWow64InprocSection
        )
        return repaired
    }

    public static func registryTextWithFileDialogRepairs(_ text: String) -> String {
        let registrations: [(classSection: String, inprocSection: String, className: String, modulePath: String)] = [
            (
                Self.fileOpenDialogClassSection,
                Self.fileOpenDialogInprocSection,
                "File Open Dialog",
                "C:\\windows\\system32\\comdlg32.dll"
            ),
            (
                Self.fileOpenDialogWow64ClassSection,
                Self.fileOpenDialogWow64InprocSection,
                "File Open Dialog",
                "C:\\windows\\syswow64\\comdlg32.dll"
            ),
            (
                Self.fileSaveDialogClassSection,
                Self.fileSaveDialogInprocSection,
                "File Save Dialog",
                "C:\\windows\\system32\\comdlg32.dll"
            ),
            (
                Self.fileSaveDialogWow64ClassSection,
                Self.fileSaveDialogWow64InprocSection,
                "File Save Dialog",
                "C:\\windows\\syswow64\\comdlg32.dll"
            )
        ]

        return registrations.reduce(text) { repaired, registration in
            var result = Self.registryText(
                repaired,
                settingString: nil,
                value: registration.className,
                inSection: registration.classSection
            )
            result = Self.registryText(
                result,
                settingString: nil,
                value: registration.modulePath,
                inSection: registration.inprocSection
            )
            return Self.registryText(
                result,
                settingString: "ThreadingModel",
                value: "Apartment",
                inSection: registration.inprocSection
            )
        }
    }

    public static func registryTextWithCryptoProviderRepairs(_ text: String) -> String {
        var repaired = text
        let providers: [(name: String, type: UInt32, typeSection: String, typeName: String)] = [
            (
                "Microsoft Enhanced Cryptographic Provider v1.0",
                1,
                Self.cryptoProviderType001Section,
                "RSA Full (Signature and Key Exchange)"
            ),
            (
                "Microsoft Base Cryptographic Provider v1.0",
                1,
                Self.cryptoProviderType001Section,
                "RSA Full (Signature and Key Exchange)"
            ),
            (
                "Microsoft Strong Cryptographic Provider",
                1,
                Self.cryptoProviderType001Section,
                "RSA Full (Signature and Key Exchange)"
            ),
            (
                "Microsoft RSA SChannel Cryptographic Provider",
                12,
                Self.cryptoProviderType012Section,
                "RSA SChannel"
            ),
            (
                "Microsoft Enhanced RSA and AES Cryptographic Provider",
                24,
                Self.cryptoProviderType024Section,
                "RSA Full and AES"
            )
        ]

        var repairedTypeSections = Set<String>()
        for provider in providers {
            let providerSection = "Software\\\\Microsoft\\\\Cryptography\\\\Defaults\\\\Provider\\\\\(provider.name)"
            repaired = Self.registryText(
                repaired,
                settingString: "Image Path",
                value: "rsaenh.dll",
                inSection: providerSection
            )
            repaired = Self.registryText(
                repaired,
                settingDWORD: "Type",
                value: provider.type,
                inSection: providerSection
            )
            guard repairedTypeSections.insert(provider.typeSection).inserted else { continue }
            repaired = Self.registryText(
                repaired,
                settingString: "Name",
                value: provider.name,
                inSection: provider.typeSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: "TypeName",
                value: provider.typeName,
                inSection: provider.typeSection
            )
        }
        return repaired
    }

    public static func registryTextWithShellFolderRepairs(_ text: String, windowsUserName: String) -> String {
        var repaired = text
        for (valueName, relativePath) in Self.shellFolderRegistryValues {
            let path = "C:\\users\\\(windowsUserName)\\\(relativePath)"
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: path,
                inSection: Self.shellFoldersSection
            )
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: path,
                inSection: Self.userShellFoldersSection
            )
        }
        return repaired
    }

    public static func registryTextWithCommonShellFolderRepairs(_ text: String) -> String {
        var repaired = text
        for (valueName, path) in Self.commonShellFolderRegistryValues {
            repaired = Self.registryText(
                repaired,
                settingString: valueName,
                value: path,
                inSection: Self.shellFoldersSection
            )
        }
        return repaired
    }

    private static func registryTextWithProxyClass(
        _ text: String,
        classSection: String,
        inprocSection: String,
        modulePath: String
    ) -> String {
        var repaired = Self.registryText(
            text,
            settingString: nil,
            value: "PSFactoryBuffer",
            inSection: classSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: nil,
            value: modulePath,
            inSection: inprocSection
        )
        repaired = Self.registryText(
            repaired,
            settingString: "ThreadingModel",
            value: "Both",
            inSection: inprocSection
        )
        return repaired
    }

    public static func fontConfigURL(for bottleId: String, paths: MacWinPaths) -> URL {
        paths.bottleDirectory(id: bottleId).appendingPathComponent(Self.fontConfigFileName)
    }

    public static func fontConfigDirectories(
        for bottleId: String,
        paths: MacWinPaths,
        fileManager: FileManager = .default
    ) -> [String] {
        let candidates = [
            paths.bottleDriveCURL(id: bottleId)
                .appendingPathComponent("windows", isDirectory: true)
                .appendingPathComponent("Fonts", isDirectory: true)
                .path,
            "/System/Library/Fonts",
            "/System/Library/Fonts/Supplemental",
            "/Library/Fonts",
            NSString(string: "~/Library/Fonts").expandingTildeInPath,
            "/System/Library/AssetsV2/com_apple_MobileAsset_Font8"
        ]
        var seen: Set<String> = []
        return candidates.filter { path in
            guard !seen.contains(path), fileManager.fileExists(atPath: path) else { return false }
            seen.insert(path)
            return true
        }
    }

    public static func fontConfigText(fontDirectories: [String]) -> String {
        let latinFallbackFamilies = [
            "Tahoma",
            "Arial",
            "PingFang SC",
            "Hiragino Sans GB",
            "Heiti SC",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Noto Sans SC",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "SimHei",
            "SimSun",
            "Arial Unicode MS",
            "sans-serif"
        ]
        let arialFallbackFamilies = [
            "Arial",
            "Tahoma",
            "PingFang SC",
            "Hiragino Sans GB",
            "Heiti SC",
            "Noto Sans SC",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "SimHei",
            "SimSun",
            "Arial Unicode MS",
            "sans-serif"
        ]
        let arialBlackFallbackFamilies = [
            "Arial Black",
            "Arial",
            "Tahoma",
            "PingFang SC",
            "Hiragino Sans GB",
            "Heiti SC",
            "Noto Sans SC",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "SimHei",
            "SimSun",
            "Arial Unicode MS",
            "sans-serif"
        ]
        let cjkFallbackFamilies = [
            "PingFang SC",
            "Hiragino Sans GB",
            "Heiti SC",
            "Noto Sans SC",
            "Noto Sans CJK SC",
            "Source Han Sans SC",
            "SimHei",
            "SimSun",
            "Arial Unicode MS",
            "Tahoma",
            "Arial",
            "sans-serif"
        ]
        let aliasFamilies = [
            "sans-serif",
            "system-ui",
            "-apple-system",
            "BlinkMacSystemFont",
            "Segoe UI",
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "Arial Black",
            "Arial",
            "Tahoma",
            "Inter",
            "MiSans",
            "HarmonyOS Sans",
            "HarmonyOS Sans SC",
            "OPPOSans",
            "Roboto",
            "Source Han Sans",
            "Source Han Sans CN",
            "Source Han Sans SC",
            "HYWenHei",
            "HYWenHei-85W",
            "HYWenHei 85W",
            "HYWenHei 85W Regular",
            "HYWenHei-Genshin",
            "Genshin Impact DRIP FONT",
            "Genshin Impact",
            "miHoYo"
        ]
        let cjkAliasFamilies: Set<String> = [
            "Microsoft YaHei UI",
            "Microsoft YaHei",
            "MiSans",
            "HarmonyOS Sans",
            "HarmonyOS Sans SC",
            "OPPOSans",
            "Source Han Sans",
            "Source Han Sans CN",
            "Source Han Sans SC",
            "HYWenHei",
            "HYWenHei-85W",
            "HYWenHei 85W",
            "HYWenHei 85W Regular",
            "HYWenHei-Genshin",
            "Genshin Impact DRIP FONT",
            "Genshin Impact",
            "miHoYo"
        ]

        var lines = [
            #"<?xml version="1.0"?>"#,
            #"<!DOCTYPE fontconfig SYSTEM "fonts.dtd">"#,
            "<fontconfig>"
        ]
        lines.append(contentsOf: fontDirectories.map { "  <dir>\(Self.xmlEscaped($0))</dir>" })
        for family in aliasFamilies {
            let fallbackFamilies: [String]
            if cjkAliasFamilies.contains(family) {
                fallbackFamilies = cjkFallbackFamilies
            } else if family == "Arial Black" {
                fallbackFamilies = arialBlackFallbackFamilies
            } else if family == "Arial" {
                fallbackFamilies = arialFallbackFamilies
            } else {
                fallbackFamilies = latinFallbackFamilies
            }
            lines.append("  <alias>")
            lines.append("    <family>\(Self.xmlEscaped(family))</family>")
            lines.append("    <prefer>")
            lines.append(contentsOf: fallbackFamilies.map { "      <family>\(Self.xmlEscaped($0))</family>" })
            lines.append("    </prefer>")
            lines.append("  </alias>")
        }
        lines.append("  <match target=\"pattern\">")
        lines.append("    <edit name=\"lang\" mode=\"append\">")
        lines.append("      <string>zh-cn</string>")
        lines.append("    </edit>")
        lines.append("  </match>")
        lines.append("  <rescan>")
        lines.append("    <int>0</int>")
        lines.append("  </rescan>")
        lines.append("</fontconfig>")
        return lines.joined(separator: "\n")
    }

    private static func xmlEscaped(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&apos;")
    }

    public static func registryText(
        _ text: String,
        removingValueNames valueNames: Set<String>,
        inSection sectionName: String
    ) -> String {
        guard !valueNames.isEmpty else { return text }
        var output: [String] = []
        var isInTargetSection = false
        var skipsRemovedValueContinuation = false
        var changed = false

        for line in text.components(separatedBy: .newlines) {
            if skipsRemovedValueContinuation {
                if Self.isRegistryContinuationLine(line) {
                    skipsRemovedValueContinuation = line.hasSuffix("\\")
                    changed = true
                    continue
                }
                skipsRemovedValueContinuation = false
            }

            if let currentSection = registrySectionName(line) {
                isInTargetSection = currentSection == sectionName
                output.append(line)
                continue
            }

            if isInTargetSection,
               let valueName = registryLineValueName(line),
               valueNames.contains(valueName) {
                changed = true
                skipsRemovedValueContinuation = line.hasSuffix("\\")
                continue
            }

            output.append(line)
        }

        return changed ? output.joined(separator: "\n") : text
    }

    @discardableResult
    public func applyGraphicsPreset(
        _ preset: GraphicsPreset,
        to bottle: BottleManifest,
        engine: EngineManifest
    ) throws -> BottleManifest {
        var updated = bottle
        for key in GraphicsPreset.managedEnvironmentKeys {
            updated.envOverrides.removeValue(forKey: key)
        }
        for (key, value) in preset.environment(engine: engine) {
            updated.envOverrides[key] = value
        }
        updated.updatedAt = Date()
        try saveBottle(updated)
        return updated
    }

    @discardableResult
    public func applyNativeUIIntegrationPreset(
        _ preset: NativeUIIntegrationPreset,
        to bottle: BottleManifest
    ) throws -> BottleManifest {
        var updated = bottle
        updated.envOverrides[NativeUIIntegrationPreset.environmentKey] = preset.environmentValue
        updated.updatedAt = Date()
        try saveBottle(updated)
        return updated
    }

    public func saveBottle(_ bottle: BottleManifest) throws {
        try paths.ensureBaseDirectories(fileManager: fileManager)
        try store.save(bottle, to: paths.bottleManifestURL(id: bottle.id))
    }

    public func addLaunchers(_ launchers: [LauncherManifest], to bottle: BottleManifest) throws -> BottleManifest {
        var updated = bottle
        var changed = false
        for incomingLauncher in launchers {
            let launcher = launcherWithCachedIcon(incomingLauncher, in: bottle)
            if let index = updated.installedApps.firstIndex(where: { $0.id == launcher.id }) {
                if updated.installedApps[index] != launcher {
                    updated.installedApps[index] = launcher
                    changed = true
                }
            } else {
                updated.installedApps.append(launcher)
                changed = true
            }
        }
        if changed {
            updated.updatedAt = Date()
            try saveBottle(updated)
        }
        return updated
    }

    private func launcherWithCachedIcon(_ launcher: LauncherManifest, in bottle: BottleManifest) -> LauncherManifest {
        if let iconPath = launcher.iconPath,
           fileManager.fileExists(atPath: iconPath) {
            return launcher
        }
        guard let executableURL = executableURL(for: launcher.exePath, in: bottle),
              fileManager.fileExists(atPath: executableURL.path),
              let iconData = try? WindowsExecutableIconExtractor.extractBestIcon(from: executableURL, fileManager: fileManager) else {
            return launcher
        }

        do {
            try fileManager.createDirectory(at: paths.iconCacheDirectory, withIntermediateDirectories: true)
            let hash = (try? Hashing.sha256Hex(file: executableURL)) ?? UUID().uuidString.lowercased()
            let destination = paths.iconCacheDirectory.appendingPathComponent("\(hash).ico")
            if !fileManager.fileExists(atPath: destination.path) {
                try iconData.write(to: destination, options: .atomic)
            }
            var updated = launcher
            updated.iconPath = destination.path
            return updated
        } catch {
            return launcher
        }
    }

    private func executableURL(for path: String, in bottle: BottleManifest) -> URL? {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.hasPrefix("/") {
            return URL(fileURLWithPath: trimmed)
        }

        let normalized = trimmed.replacingOccurrences(of: "\\", with: "/")
        let lowercased = normalized.lowercased()
        if lowercased.hasPrefix("c:/") {
            let relative = String(normalized.dropFirst(3))
            return paths.bottleDriveCURL(id: bottle.id).appendingPathComponent(relative)
        }
        return nil
    }

    @discardableResult
    public func updateLauncher(_ launcher: LauncherManifest, in bottle: BottleManifest) throws -> BottleManifest {
        var updated = bottle
        guard let index = updated.installedApps.firstIndex(where: { $0.id == launcher.id }) else {
            throw MacWinError.invalidManifest("Launcher \(launcher.id) does not exist in bottle \(bottle.id)")
        }
        if updated.installedApps[index] != launcher {
            updated.installedApps[index] = launcher
            updated.updatedAt = Date()
            try saveBottle(updated)
        }
        return updated
    }

    @discardableResult
    public func applyCompatibilityProfile(
        _ profile: ApplicationCompatibilityProfile,
        to launcher: LauncherManifest,
        in bottle: BottleManifest
    ) throws -> BottleManifest {
        try updateLauncher(profile.applied(to: launcher), in: bottle)
    }

    @discardableResult
    public func clearCompatibilityProfile(
        from launcher: LauncherManifest,
        in bottle: BottleManifest
    ) throws -> BottleManifest {
        try updateLauncher(ApplicationCompatibilityProfile.cleared(from: launcher), in: bottle)
    }

    public func deleteBottle(_ bottle: BottleManifest) throws {
        let url = paths.bottleDirectory(id: bottle.id)
        if fileManager.fileExists(atPath: url.path) {
            try fileManager.removeItem(at: url)
        }
    }

    public static func makeBottleId(name: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
        let slug = name
            .lowercased()
            .unicodeScalars
            .map { allowed.contains($0) ? Character($0) : "-" }
            .reduce(into: "") { $0.append($1) }
            .split(separator: "-")
            .joined(separator: "-")
        let prefix = slug.isEmpty ? "bottle" : slug
        return "\(prefix)-\(UUID().uuidString.prefix(8).lowercased())"
    }

    public static func highPerformanceEnvOverrides(engine: EngineManifest) -> [String: String] {
        var env = GraphicsPreset.wineD3DVulkan.environment(engine: engine)
        env[NativeUIIntegrationPreset.environmentKey] = NativeUIIntegrationPreset.automatic.environmentValue
        env["WINEDEBUG"] = "-all"
        return env
    }

    private func winebootSentinelURL(for bottle: BottleManifest) -> URL {
        paths.bottleDirectory(id: bottle.id).appendingPathComponent(Self.winebootSentinelName)
    }

    private func repairWoW64SystemFilesIfNeeded(bottle: BottleManifest, engine: EngineManifest) throws {
        guard engine.supportsWin32 else { return }
        guard bottle.arch == .win64 else { return }
        guard !hasUsableWoW64SystemFiles(bottle: bottle) else { return }

        let temporaryBottle = BottleManifest(
            id: ".macwin-wow64-repair-\(UUID().uuidString.lowercased())",
            name: "MacWin WoW64 Repair",
            windowsVersion: bottle.windowsVersion,
            arch: bottle.arch,
            engineId: engine.id,
            envOverrides: bottle.envOverrides,
            installedApps: []
        )
        let temporaryDirectory = paths.bottleDirectory(id: temporaryBottle.id)
        defer { try? fileManager.removeItem(at: temporaryDirectory) }

        let result = try runner.run(
            WineRunRequest(
                exe: "wineboot",
                args: ["-u"],
                bottle: temporaryBottle,
                engine: engine,
                logName: "\(bottle.id)-wow64-repair.log"
            )
        )
        if result.exitCode != 0 {
            throw MacWinError.processFailed(
                command: result.commandLine.joined(separator: " "),
                exitCode: result.exitCode,
                logPath: result.logURL.path
            )
        }

        let sourceWindows = paths.bottleDriveCURL(id: temporaryBottle.id)
            .appendingPathComponent("windows", isDirectory: true)
        let targetWindows = paths.bottleDriveCURL(id: bottle.id)
            .appendingPathComponent("windows", isDirectory: true)
        let sourceSysWOW64 = sourceWindows.appendingPathComponent("syswow64", isDirectory: true)
        let targetSysWOW64 = targetWindows.appendingPathComponent("syswow64", isDirectory: true)
        guard fileManager.fileExists(atPath: sourceSysWOW64.appendingPathComponent("ntdll.dll").path) else {
            throw MacWinError.missingFile(sourceSysWOW64.appendingPathComponent("ntdll.dll").path)
        }

        if fileManager.fileExists(atPath: targetSysWOW64.path) {
            try fileManager.removeItem(at: targetSysWOW64)
        }
        try fileManager.createDirectory(at: targetWindows, withIntermediateDirectories: true)
        try copyItemReplacingExisting(at: sourceSysWOW64, to: targetSysWOW64)

        let sourceSystem32 = sourceWindows.appendingPathComponent("system32", isDirectory: true)
        let targetSystem32 = targetWindows.appendingPathComponent("system32", isDirectory: true)
        try fileManager.createDirectory(at: targetSystem32, withIntermediateDirectories: true)
        for fileName in Self.requiredWoW64System32Files {
            let source = sourceSystem32.appendingPathComponent(fileName)
            let target = targetSystem32.appendingPathComponent(fileName)
            guard fileManager.fileExists(atPath: source.path) else {
                throw MacWinError.missingFile(source.path)
            }
            try copyItemReplacingExisting(at: source, to: target)
        }

        let sourceDrivers = sourceSystem32.appendingPathComponent("drivers", isDirectory: true)
        let targetDrivers = targetSystem32.appendingPathComponent("drivers", isDirectory: true)
        try fileManager.createDirectory(at: targetDrivers, withIntermediateDirectories: true)
        for fileName in Self.requiredWoW64DriverFiles {
            let source = sourceDrivers.appendingPathComponent(fileName)
            let target = targetDrivers.appendingPathComponent(fileName)
            guard fileManager.fileExists(atPath: source.path) else {
                throw MacWinError.missingFile(source.path)
            }
            try copyItemReplacingExisting(at: source, to: target)
        }
    }

    private func repairEngineCoverageSystemDLLs(bottle: BottleManifest, engine: EngineManifest) throws {
        let buildURL = paths.engineDirectory(id: engine.id).appendingPathComponent("build", isDirectory: true)
        let windows = paths.bottleDriveCURL(id: bottle.id).appendingPathComponent("windows", isDirectory: true)
        let system32 = windows.appendingPathComponent("system32", isDirectory: true)
        let sysWOW64 = windows.appendingPathComponent("syswow64", isDirectory: true)
        try fileManager.createDirectory(at: system32, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: sysWOW64, withIntermediateDirectories: true)

        for item in Self.engineCoverageSystemDLLs {
            let x64Source = buildURL
                .appendingPathComponent("dlls", isDirectory: true)
                .appendingPathComponent(item.module, isDirectory: true)
                .appendingPathComponent("x86_64-windows", isDirectory: true)
                .appendingPathComponent(item.dll)
            let x64Target = system32.appendingPathComponent(item.dll)
            if fileManager.fileExists(atPath: x64Source.path) {
                try copyItemReplacingExisting(at: x64Source, to: x64Target)
            }

            let x86Source = buildURL
                .appendingPathComponent("dlls", isDirectory: true)
                .appendingPathComponent(item.module, isDirectory: true)
                .appendingPathComponent("i386-windows", isDirectory: true)
                .appendingPathComponent(item.dll)
            let x86Target = sysWOW64.appendingPathComponent(item.dll)
            if fileManager.fileExists(atPath: x86Source.path) {
                try copyItemReplacingExisting(at: x86Source, to: x86Target)
            }
        }
    }

    private func copyItemReplacingExisting(at source: URL, to target: URL) throws {
        if fileManager.fileExists(atPath: target.path) {
            try fileManager.removeItem(at: target)
        }
        do {
            try fileManager.copyItem(at: source, to: target)
        } catch CocoaError.fileWriteFileExists {
            try fileManager.removeItem(at: target)
            try fileManager.copyItem(at: source, to: target)
        }
    }

    private func hasUsableWoW64SystemFiles(bottle: BottleManifest) -> Bool {
        let windows = paths.bottleDriveCURL(id: bottle.id).appendingPathComponent("windows", isDirectory: true)
        let sysWOW64 = windows.appendingPathComponent("syswow64", isDirectory: true)
        let system32 = windows.appendingPathComponent("system32", isDirectory: true)
        let drivers = system32.appendingPathComponent("drivers", isDirectory: true)
        return Self.requiredWoW64SysWOW64Files.allSatisfy {
            fileManager.fileExists(atPath: sysWOW64.appendingPathComponent($0).path)
        } && Self.requiredWoW64System32Files.allSatisfy {
            fileManager.fileExists(atPath: system32.appendingPathComponent($0).path)
        } && Self.requiredWoW64DriverFiles.allSatisfy {
            fileManager.fileExists(atPath: drivers.appendingPathComponent($0).path)
        }
    }

    private static let requiredWoW64SysWOW64Files = [
        "ntdll.dll",
        "kernel32.dll",
        "vulkan-1.dll",
        "winevulkan.dll",
        "opengl32.dll",
        "wined3d.dll",
        "d3d9.dll",
        "d3d11.dll",
        "d3d12.dll",
        "dxgi.dll",
        "d3dcompiler_47.dll",
        "mfplat.dll",
        "mfreadwrite.dll",
        "mmdevapi.dll",
        "rsaenh.dll",
        "rtworkq.dll",
        "xaudio2_7.dll",
        "xaudio2_8.dll",
        "xaudio2_9.dll",
        "winedevice.exe",
        "winemac.drv"
    ]

    private static let requiredWoW64System32Files = [
        "wow64.dll",
        "wow64cpu.dll",
        "wow64win.dll",
        "dwrite.dll",
        "vulkan-1.dll",
        "winevulkan.dll",
        "opengl32.dll",
        "wined3d.dll",
        "d3d9.dll",
        "d3d11.dll",
        "d3d12.dll",
        "dxgi.dll",
        "d3dcompiler_47.dll",
        "mfplat.dll",
        "mfreadwrite.dll",
        "mmdevapi.dll",
        "rsaenh.dll",
        "rtworkq.dll",
        "xaudio2_7.dll",
        "xaudio2_8.dll",
        "xaudio2_9.dll",
        "winedevice.exe",
        "winemac.drv"
    ]

    private static let requiredWoW64DriverFiles = [
        "hidparse.sys",
        "mountmgr.sys",
        "ndis.sys",
        "nsiproxy.sys",
        "winebus.sys"
    ]

    public static let engineCoverageSystemDLLs: [(module: String, dll: String)] = [
        ("actxprxy", "actxprxy.dll"),
        ("bcryptprimitives", "bcryptprimitives.dll"),
        ("comctl32_v6", "comctl32_v6.dll"),
        ("concrt140", "concrt140.dll"),
        ("vcomp", "vcomp.dll"),
        ("vcomp90", "vcomp90.dll"),
        ("vcomp100", "vcomp100.dll"),
        ("vcomp110", "vcomp110.dll"),
        ("vcomp120", "vcomp120.dll"),
        ("vcomp140", "vcomp140.dll"),
        ("credui", "credui.dll"),
        ("cryptui", "cryptui.dll"),
        ("dcomp", "dcomp.dll"),
        ("dwrite", "dwrite.dll"),
        ("esent", "esent.dll"),
        ("iphlpapi", "iphlpapi.dll"),
        ("kerberos", "kerberos.dll"),
        ("mmdevapi", "mmdevapi.dll"),
        ("msctf", "msctf.dll"),
        ("msv1_0", "msv1_0.dll"),
        ("netapi32", "netapi32.dll"),
        ("netprofm", "netprofm.dll"),
        ("oleacc", "oleacc.dll"),
        ("powrprof", "powrprof.dll"),
        ("qmgr", "qmgr.dll"),
        ("rasapi32", "rasapi32.dll"),
        ("rstrtmgr", "rstrtmgr.dll"),
        ("rsaenh", "rsaenh.dll"),
        ("taskschd", "taskschd.dll"),
        ("mstask", "mstask.dll"),
        ("schedsvc", "schedsvc.dll"),
        ("uiautomationcore", "uiautomationcore.dll"),
        ("wevtapi", "wevtapi.dll"),
        ("wevtsvc", "wevtsvc.dll"),
        ("webservices", "webservices.dll"),
        ("threadpoolwinrt", "threadpoolwinrt.dll"),
        ("windows.ui", "windows.ui.dll"),
        ("wintab32", "wintab32.dll"),
        ("wlanapi", "wlanapi.dll")
    ]

    private static let winRTActivationClasses: [(className: String, dllName: String)] = [
        ("Windows.Foundation.Metadata.ApiInformation", "wintypes.dll"),
        ("Windows.Foundation.PropertyValue", "wintypes.dll"),
        ("Windows.Foundation.Collections.PropertySet", "wintypes.dll"),
        ("Windows.Storage.Streams.Buffer", "wintypes.dll"),
        ("Windows.Storage.Streams.DataWriter", "wintypes.dll"),
        ("Windows.System.Threading.ThreadPool", "threadpoolwinrt.dll"),
        ("Windows.System.Threading.ThreadPoolTimer", "threadpoolwinrt.dll"),
        ("Windows.UI.ViewManagement.AccessibilitySettings", "windows.ui.dll"),
        ("Windows.UI.ViewManagement.UISettings", "windows.ui.dll"),
        ("Windows.UI.ViewManagement.UIViewSettings", "windows.ui.dll"),
        ("Windows.UI.ViewManagement.InputPane", "windows.ui.dll"),
        ("Windows.UI.Core.CoreWindow", "windows.ui.dll"),
        ("Windows.UI.Internal.Input.InputSite", "windows.ui.dll"),
        ("Windows.UI.Internal.Input.ActivationConfigurationInputObject", "windows.ui.dll"),
        ("Windows.UI.Composition.Compositor", "windows.ui.dll"),
        ("Windows.UI.Composition.CompositionCapabilities", "windows.ui.dll"),
        ("Windows.UI.Composition.CompositionEffectSourceParameter", "windows.ui.dll")
    ]

    private static let webViewRenderingCacheDirectoryNames: Set<String> = [
        "GPUCache",
        "ShaderCache",
        "GrShaderCache",
        "DawnCache",
        "DawnWebGPUCache",
        "DawnGraphiteCache",
        "GraphiteDawnCache",
        "Code Cache"
    ]

    private static let fontRegistryValues: [(String, String)] = [
        ("Arial (TrueType)", "arial.ttf"),
        ("Arial Bold (TrueType)", "arialbd.ttf"),
        ("Arial Italic (TrueType)", "ariali.ttf"),
        ("Arial Bold Italic (TrueType)", "arialbi.ttf"),
        ("Arial Black (TrueType)", "ariblk.ttf"),
        ("Arial Unicode MS (TrueType)", "arialuni.ttf"),
        ("Courier New (TrueType)", "cour.ttf"),
        ("Courier New Bold (TrueType)", "courbd.ttf"),
        ("Courier New Italic (TrueType)", "couri.ttf"),
        ("Courier New Bold Italic (TrueType)", "courbi.ttf"),
        ("Microsoft Sans Serif (TrueType)", "micross.ttf"),
        ("Segoe UI (TrueType)", "segoeui.ttf"),
        ("Segoe UI Bold (TrueType)", "segoeuib.ttf"),
        ("Segoe UI Italic (TrueType)", "segoeuii.ttf"),
        ("Segoe UI Bold Italic (TrueType)", "segoeuiz.ttf"),
        ("Segoe UI Light (TrueType)", "segoeuil.ttf"),
        ("Segoe UI Semibold (TrueType)", "seguisb.ttf"),
        ("Segoe UI Symbol (TrueType)", "seguisym.ttf"),
        ("Segoe Fluent Icons (TrueType)", "segfluent.ttf"),
        ("Tahoma (TrueType)", "tahoma.ttf"),
        ("Tahoma Bold (TrueType)", "tahomabd.ttf"),
        ("Times New Roman (TrueType)", "times.ttf"),
        ("Times New Roman Bold (TrueType)", "timesbd.ttf"),
        ("Times New Roman Italic (TrueType)", "timesi.ttf"),
        ("Times New Roman Bold Italic (TrueType)", "timesbi.ttf"),
        ("PingFang SC (TrueType)", "pingfang.ttc"),
        ("Hiragino Sans GB (TrueType)", "simhei.ttf"),
        ("Heiti SC (TrueType)", "simhei.ttf"),
        ("Noto Sans SC (TrueType)", "Noto Sans SC (TrueType).otf"),
        ("Noto Sans SC Bold (TrueType)", "Noto Sans SC Bold (TrueType).otf"),
        ("Noto Sans SC Medium (TrueType)", "Noto Sans SC Medium (TrueType).otf"),
        ("SimSun & NSimSun (TrueType)", "simsun.ttc"),
        ("SimHei (TrueType)", "simhei.ttf"),
        ("Microsoft YaHei & Microsoft YaHei UI (TrueType)", "msyh.ttc"),
        ("Microsoft YaHei Bold & Microsoft YaHei UI Bold (TrueType)", "msyhbd.ttc"),
        ("Microsoft YaHei Light & Microsoft YaHei UI Light (TrueType)", "msyhl.ttc"),
        ("Microsoft JhengHei & Microsoft JhengHei UI (TrueType)", "msjh.ttc"),
        ("Microsoft JhengHei Bold & Microsoft JhengHei UI Bold (TrueType)", "msjhbd.ttc"),
        ("Malgun Gothic (TrueType)", "malgun.ttf"),
        ("Malgun Gothic Bold (TrueType)", "malgunbd.ttf"),
        ("Meiryo & Meiryo UI (TrueType)", "meiryo.ttc"),
        ("Meiryo Bold & Meiryo UI Bold (TrueType)", "meiryob.ttc"),
        ("Yu Gothic & Yu Gothic UI (TrueType)", "yugothic.ttf"),
        ("Yu Gothic Bold & Yu Gothic UI Bold (TrueType)", "yugothib.ttf"),
        ("HarmonyOS Sans SC (TrueType)", "msyh.ttc"),
        ("MiSans (TrueType)", "msyh.ttc"),
        ("OPPOSans (TrueType)", "msyh.ttc"),
        ("Roboto (TrueType)", "arial.ttf"),
        ("Source Han Sans SC (TrueType)", "Noto Sans SC (TrueType).otf"),
        ("HYWenHei (TrueType)", "msyh.ttc"),
        ("HYWenHei-85W (TrueType)", "msyhbd.ttc"),
        ("HYWenHei 85W (TrueType)", "msyhbd.ttc"),
        ("HYWenHei 85W Regular (TrueType)", "msyhbd.ttc"),
        ("HYWenHei-Genshin (TrueType)", "msyhbd.ttc"),
        ("Genshin Impact DRIP FONT (TrueType)", "msyhbd.ttc"),
        ("Genshin Impact (TrueType)", "msyhbd.ttc"),
        ("miHoYo (TrueType)", "msyh.ttc")
    ]

    private static let fontSubstituteValues: [(String, String)] = [
        ("MS Shell Dlg", "Tahoma"),
        ("MS Shell Dlg 2", "Tahoma"),
        ("Microsoft Sans Serif", "Tahoma"),
        ("MS Sans Serif", "Tahoma"),
        ("Arial Unicode MS", "PingFang SC"),
        ("DIN", "PingFang SC"),
        ("DIN Alternate", "PingFang SC"),
        ("HarmonyOS Sans", "PingFang SC"),
        ("HarmonyOS Sans SC", "PingFang SC"),
        ("Helv", "PingFang SC"),
        ("Helvetica", "PingFang SC"),
        ("Hiragino Sans GB", "PingFang SC"),
        ("Inter", "PingFang SC"),
        ("MiSans", "PingFang SC"),
        ("Noto Sans", "PingFang SC"),
        ("Roboto", "PingFang SC"),
        ("Segoe UI", "Tahoma"),
        ("Segoe UI Bold", "Tahoma"),
        ("Segoe UI Semibold", "Tahoma"),
        ("Segoe UI Variable", "Tahoma"),
        ("BlinkMacSystemFont", "PingFang SC"),
        ("-apple-system", "PingFang SC"),
        ("system-ui", "PingFang SC"),
        ("sans", "PingFang SC"),
        ("sans-serif", "PingFang SC"),
        ("Noto Sans CJK SC", "PingFang SC"),
        ("Noto Sans SC", "PingFang SC"),
        ("Source Han Sans SC", "PingFang SC"),
        ("Source Han Sans CN", "PingFang SC"),
        ("Microsoft YaHei", "PingFang SC"),
        ("Microsoft YaHei Bold", "PingFang SC"),
        ("Microsoft YaHei UI", "PingFang SC"),
        ("Microsoft YaHei UI Bold", "PingFang SC"),
        ("Microsoft YaHei Light", "PingFang SC"),
        ("Microsoft YaHei UI Light", "PingFang SC"),
        ("Microsoft JhengHei", "PingFang SC"),
        ("Microsoft JhengHei UI", "PingFang SC"),
        ("Meiryo", "PingFang SC"),
        ("Yu Gothic", "PingFang SC"),
        ("SimSun", "PingFang SC"),
        ("NSimSun", "PingFang SC"),
        ("SimHei", "PingFang SC"),
        ("Songti SC", "PingFang SC"),
        ("Heiti SC", "PingFang SC"),
        ("HYWenHei", "PingFang SC"),
        ("HYWenHei-85W", "PingFang SC"),
        ("HYWenHei 85W", "PingFang SC"),
        ("HYWenHei 85W Regular", "PingFang SC"),
        ("HYWenHei-Genshin", "PingFang SC"),
        ("Hanyi WenHei", "PingFang SC"),
        ("Genshin Impact DRIP FONT", "PingFang SC"),
        ("Genshin Impact", "PingFang SC"),
        ("miHoYo", "PingFang SC"),
        ("MiSans", "PingFang SC"),
        ("OPPOSans", "PingFang SC"),
        ("HarmonyOS Sans SC", "PingFang SC"),
        ("Source Han Sans", "PingFang SC"),
        ("Source Han Sans CN", "PingFang SC"),
        ("Source Han Sans SC", "PingFang SC")
    ]

    private static let obsoleteFontSubstituteValueNames: Set<String> = [
        "PingFang SC",
        "Arial",
        "Arial Black",
        "Arial Bold",
        "Tahoma"
    ]

    private static let fontLinkValues: [(valueName: String, values: [String])] = [
        ("Arial", ["Noto Sans SC (TrueType).otf"]),
        ("Arial Black", ["Noto Sans SC (TrueType).otf"]),
        ("Arial Bold", ["Noto Sans SC Bold (TrueType).otf", "Noto Sans SC (TrueType).otf"]),
        ("Segoe UI", ["Noto Sans SC (TrueType).otf"]),
        ("Segoe UI Bold", ["Noto Sans SC Bold (TrueType).otf", "Noto Sans SC (TrueType).otf"]),
        ("Tahoma", ["Noto Sans SC (TrueType).otf"]),
        ("Tahoma Bold", ["Noto Sans SC Bold (TrueType).otf", "Noto Sans SC (TrueType).otf"]),
        ("System", ["Noto Sans SC (TrueType).otf"])
    ]

    private static let windowMetricsFontValueNames = [
        "CaptionFont",
        "IconFont",
        "MenuFont",
        "MessageFont",
        "SmCaptionFont",
        "StatusFont"
    ]

    private struct WindowsFontLink {
        var fileName: String
        var sourceCandidates: [String]
        var discoveryFileNames: [String] = []
        var replaceExisting: Bool = false
    }

    private static let windowsFontLinks: [WindowsFontLink] = [
        WindowsFontLink(fileName: "pingfang.ttc", sourceCandidates: [], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(
            fileName: "arial.ttf",
            sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"],
            discoveryFileNames: ["Arial.ttf"]
        ),
        WindowsFontLink(
            fileName: "arialbd.ttf",
            sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"],
            discoveryFileNames: ["Arial Bold.ttf"]
        ),
        WindowsFontLink(fileName: "ariali.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Italic.ttf", "/Library/Fonts/Arial Italic.ttf"]),
        WindowsFontLink(fileName: "arialbi.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf", "/Library/Fonts/Arial Bold Italic.ttf"]),
        WindowsFontLink(fileName: "ariblk.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Black.ttf", "/Library/Fonts/Arial Black.ttf"]),
        WindowsFontLink(fileName: "arialuni.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"]),
        WindowsFontLink(fileName: "cour.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Courier New.ttf", "/Library/Fonts/Courier New.ttf"]),
        WindowsFontLink(fileName: "courbd.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Courier New Bold.ttf", "/Library/Fonts/Courier New Bold.ttf"]),
        WindowsFontLink(fileName: "couri.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Courier New Italic.ttf", "/Library/Fonts/Courier New Italic.ttf"]),
        WindowsFontLink(fileName: "courbi.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Courier New Bold Italic.ttf", "/Library/Fonts/Courier New Bold Italic.ttf"]),
        WindowsFontLink(fileName: "micross.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Microsoft Sans Serif.ttf", "/Library/Fonts/Microsoft Sans Serif.ttf"]),
        WindowsFontLink(fileName: "segoeui.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Tahoma.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc"]),
        WindowsFontLink(fileName: "segoeuib.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Tahoma Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]),
        WindowsFontLink(fileName: "segoeuii.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Italic.ttf"]),
        WindowsFontLink(fileName: "segoeuiz.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"]),
        WindowsFontLink(fileName: "segoeuil.ttf", sourceCandidates: ["/System/Library/Fonts/HelveticaNeue.ttc", "/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"]),
        WindowsFontLink(fileName: "seguisb.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Tahoma Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]),
        WindowsFontLink(fileName: "seguisym.ttf", sourceCandidates: ["/System/Library/Fonts/Apple Symbols.ttf", "/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "segfluent.ttf", sourceCandidates: ["/System/Library/Fonts/Apple Symbols.ttf", "/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "tahoma.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Tahoma.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]),
        WindowsFontLink(fileName: "tahomabd.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Tahoma Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]),
        WindowsFontLink(fileName: "times.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Times New Roman.ttf", "/Library/Fonts/Times New Roman.ttf"]),
        WindowsFontLink(fileName: "timesbd.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", "/Library/Fonts/Times New Roman Bold.ttf"]),
        WindowsFontLink(fileName: "timesi.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf", "/Library/Fonts/Times New Roman Italic.ttf"]),
        WindowsFontLink(fileName: "timesbi.ttf", sourceCandidates: ["/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf", "/Library/Fonts/Times New Roman Bold Italic.ttf"]),
        WindowsFontLink(fileName: "Noto Sans SC (TrueType).otf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["NotoSansCJK-Regular.ttc", "NotoSansSC-Regular.otf", "PingFang.ttc"]),
        WindowsFontLink(fileName: "Noto Sans SC Bold (TrueType).otf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["NotoSansCJK-Bold.ttc", "NotoSansSC-Bold.otf", "PingFang.ttc"]),
        WindowsFontLink(fileName: "Noto Sans SC Medium (TrueType).otf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["NotoSansCJK-Medium.ttc", "NotoSansSC-Medium.otf", "PingFang.ttc"]),
        WindowsFontLink(fileName: "simsun.ttc", sourceCandidates: ["/System/Library/Fonts/Supplemental/Songti.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "simhei.ttf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "msyh.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "msyhbd.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "msyhl.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Light.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "msjh.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "msjhbd.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "malgun.ttf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "malgunbd.ttf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "meiryo.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "meiryob.ttc", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "yugothic.ttf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"]),
        WindowsFontLink(fileName: "yugothib.ttf", sourceCandidates: ["/System/Library/Fonts/STHeiti Medium.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc"], discoveryFileNames: ["PingFang.ttc"])
    ]

    private static func discoverMacFonts(fileManager: FileManager) -> [String: String] {
        let roots = [
            "/System/Library/Fonts",
            "/System/Library/Fonts/Supplemental",
            "/Library/Fonts",
            NSString(string: "~/Library/Fonts").expandingTildeInPath,
            "/System/Library/AssetsV2/com_apple_MobileAsset_Font8"
        ]
        let validExtensions: Set<String> = ["ttf", "ttc", "otf"]
        var result: [String: String] = [:]

        for rootPath in roots where fileManager.fileExists(atPath: rootPath) {
            let root = URL(fileURLWithPath: rootPath, isDirectory: true)
            guard let enumerator = fileManager.enumerator(
                at: root,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles, .skipsPackageDescendants]
            ) else { continue }

            while let item = enumerator.nextObject() as? URL {
                let values = try? item.resourceValues(forKeys: [.isDirectoryKey])
                if values?.isDirectory == true {
                    continue
                }
                guard validExtensions.contains(item.pathExtension.lowercased()) else { continue }
                let key = item.lastPathComponent.lowercased()
                if result[key] == nil {
                    result[key] = item.path
                }
            }
        }

        return result
    }

    private static func shouldRemoveRegistrySection(_ line: String, removingServices services: Set<String>) -> Bool {
        let parts = registrySectionParts(line)
        if parts.count >= 4,
           parts[0] == "System",
           parts[2] == "Services",
           services.contains(parts[3].lowercased()) {
            return true
        }

        if parts.count >= 6,
           parts[0] == "System",
           parts[2] == "Enum",
           parts[3] == "ROOT",
           parts[4] == "WINE",
           services.contains(parts[5].lowercased()) {
            return true
        }

        return false
    }

    private static func serviceName(fromRegistrySection section: String) -> String? {
        let parts = section.components(separatedBy: "\\\\")
        guard parts.count == 4,
              parts[0] == "System",
              parts[2] == "Services"
        else {
            return nil
        }
        return parts[3]
    }

    private static func registrySectionParts(_ line: String) -> [String] {
        guard let section = registrySectionName(line) else { return [] }
        return section.components(separatedBy: "\\\\")
    }

    private static func registryValueName(_ valueName: String?) -> String {
        guard let valueName else { return "@" }
        return "\"\(valueName)\""
    }

    private static func registryEscapedString(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
    }

    private static func registrySectionName(_ line: String) -> String? {
        guard line.hasPrefix("[") else { return nil }
        guard let closingBracket = line.firstIndex(of: "]") else { return nil }
        let sectionStart = line.index(after: line.startIndex)
        return String(line[sectionStart..<closingBracket])
    }

    private static func registryLineValueName(_ line: String) -> String? {
        guard line.hasPrefix("\"") else { return nil }
        guard let closingQuote = line.dropFirst().firstIndex(of: "\"") else { return nil }
        return String(line[line.index(after: line.startIndex)..<closingQuote])
    }

    private static func isRegistryContinuationLine(_ line: String) -> Bool {
        line.first?.isWhitespace == true
    }
}
