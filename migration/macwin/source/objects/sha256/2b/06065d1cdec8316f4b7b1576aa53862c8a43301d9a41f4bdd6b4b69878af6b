import Foundation

let arguments = CommandLine.arguments
guard arguments.count >= 5,
      let port = Int(arguments[1]),
      let delay = Double(arguments[4]) else {
    fputs("usage: inspect-chromium-page <port> <report.json> <screenshot.png> <delay-seconds> [timeout-seconds]\n", stderr)
    exit(2)
}

let reportURL = URL(fileURLWithPath: arguments[2])
let screenshotURL = URL(fileURLWithPath: arguments[3])
let timeout = arguments.count >= 6 ? (Double(arguments[5]) ?? 30) : 30
let deadline = Date().addingTimeInterval(timeout)
let session = URLSession(configuration: .ephemeral)
var firstTargetSeenAt: Date?

func loadJSON(_ url: URL) -> Any? {
    let semaphore = DispatchSemaphore(value: 0)
    var result: Any?
    session.dataTask(with: url) { data, _, _ in
        defer { semaphore.signal() }
        guard let data else { return }
        result = try? JSONSerialization.jsonObject(with: data)
    }.resume()
    _ = semaphore.wait(timeout: .now() + 2)
    return result
}

func pageTarget() -> [String: Any]? {
    let endpoint = URL(string: "http://127.0.0.1:\(port)/json/list")!
    guard let targets = loadJSON(endpoint) as? [[String: Any]] else { return nil }
    let pages = targets.filter { $0["type"] as? String == "page" }
    if let preferred = pages.first(where: { target in
        let url = (target["url"] as? String ?? "").lowercased()
        return url.contains("127.0.0.1") || url.contains("/browser/")
    }) {
        return preferred
    }
    if pages.contains(where: { target in
        let title = (target["title"] as? String ?? "").lowercased()
        let url = (target["url"] as? String ?? "").lowercased()
        return title.contains("pgadmin") && url.contains("splash.html")
    }) {
        return nil
    }
    return pages.first
}

func sendCommand(
    _ method: String,
    params: [String: Any] = [:],
    using task: URLSessionWebSocketTask,
    id: Int
) -> [String: Any]? {
    let payload: [String: Any] = ["id": id, "method": method, "params": params]
    guard let data = try? JSONSerialization.data(withJSONObject: payload),
          let text = String(data: data, encoding: .utf8) else { return nil }

    let sendSemaphore = DispatchSemaphore(value: 0)
    var sendSucceeded = false
    task.send(.string(text)) { error in
        sendSucceeded = error == nil
        sendSemaphore.signal()
    }
    guard sendSemaphore.wait(timeout: .now() + 2) == .success, sendSucceeded else { return nil }

    while Date() < deadline {
        let receiveSemaphore = DispatchSemaphore(value: 0)
        var received: URLSessionWebSocketTask.Message?
        task.receive { result in
            if case let .success(message) = result { received = message }
            receiveSemaphore.signal()
        }
        guard receiveSemaphore.wait(timeout: .now() + 2) == .success else { return nil }
        let responseText: String?
        switch received {
        case let .string(value): responseText = value
        case let .data(value): responseText = String(data: value, encoding: .utf8)
        case nil: responseText = nil
        @unknown default: responseText = nil
        }
        guard let responseText,
              let responseData = responseText.data(using: .utf8),
              let response = try? JSONSerialization.jsonObject(with: responseData) as? [String: Any],
              response["id"] as? Int == id else { continue }
        return response
    }
    return nil
}

let diagnosticExpression = #"""
(() => {
  const store = window._reduxStore;
  const state = store && store.getState ? store.getState() : null;
  const native = state && state.native;
  const recommend = state && state.recommend;
  const aiPcRecommend = state && state.aiPcRecommend;
  const exploreEntry = state && state.exploreEntry;
  const banners = recommend && recommend.recoBanner && recommend.recoBanner.data;
  const cards = recommend && recommend.recoRecommend && recommend.recoRecommend.pageCardList;
  const resources = performance.getEntriesByType("resource");
  const visible = [...document.querySelectorAll("body *")].filter(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" &&
      Number(style.opacity || 1) > 0 && rect.width > 1 && rect.height > 1;
  });
  const loadingElements = visible.filter(element =>
    /load|spin|skeleton/i.test(`${element.className || ""} ${element.id || ""}`)
  );
  return {
    capturedAt: new Date().toISOString(),
    href: location.href,
    title: document.title,
    readyState: document.readyState,
    bodyTextLength: document.body ? document.body.innerText.length : 0,
    bodyHTMLLength: document.body ? document.body.innerHTML.length : 0,
    bodyBackground: document.body ? getComputedStyle(document.body).backgroundColor : null,
    rootChildren: document.body ? document.body.children.length : 0,
    visibleElementCount: visible.length,
    visibleTextSample: visible.map(element => element.innerText || "")
      .filter(Boolean).join(" ").replace(/\s+/g, " ").slice(0, 800),
    viewport: { width: innerWidth, height: innerHeight, devicePixelRatio },
    reduxStateKeys: state ? Object.keys(state) : [],
    nativeCommandLineReady: native ? native.commandLineReady === true : null,
    nativeCommandLine: native && native.commandLine ? String(native.commandLine) : null,
    recommendPresent: !!recommend,
    bannerCount: Array.isArray(banners) ? banners.length : -1,
    cardCount: Array.isArray(cards) ? cards.length : -1,
    bannerResponse: !!(recommend && recommend.recoBannerDataIsResponse),
    recommendLoading: recommend ? !!recommend.recoRecommendLoadding : null,
    recommendPageType: recommend && recommend.recoBanner ? recommend.recoBanner.pageType || null : null,
    recommendBannerKey: recommend && recommend.recoBanner ? recommend.recoBanner.getBannerKey || null : null,
    aiPcRecommend: aiPcRecommend ? {
      isAbLoaded: !!aiPcRecommend.isAbLoaded,
      isAbEnabled: !!aiPcRecommend.isAbEnabled,
      engineAvailable: !!aiPcRecommend.engineAvailable,
      cardCount: Array.isArray(aiPcRecommend.cards) ? aiPcRecommend.cards.length : -1
    } : null,
    exploreEntry: exploreEntry ? {
      initialized: exploreEntry.initialized === true,
      commandLineMode: exploreEntry.commandLineMode || null,
      userTabLock: exploreEntry.userTabLock || null,
      entrySource: exploreEntry.entrySource || null
    } : null,
    visibleLoadingElementCount: loadingElements.length,
    visibleLoadingElements: loadingElements.slice(0, 12).map(element => ({
      tag: element.tagName,
      id: element.id || "",
      className: String(element.className || "").slice(0, 240),
      text: (element.innerText || "").replace(/\s+/g, " ").slice(0, 160)
    })),
    resourceCount: resources.length,
    lenovoResourceCount: resources.filter(entry => /lenovo|lenovomm/i.test(entry.name)).length,
    recentResources: resources.slice(-30).map(entry => ({
      name: entry.name,
      duration: Math.round(entry.duration),
      transferSize: entry.transferSize || 0,
      encodedBodySize: entry.encodedBodySize || 0,
      responseStatus: entry.responseStatus || 0
    })),
    canvasCount: document.querySelectorAll("canvas").length,
    canvases: [...document.querySelectorAll("canvas")].map(canvas => ({
      width: canvas.width,
      height: canvas.height,
      clientWidth: canvas.clientWidth,
      clientHeight: canvas.clientHeight
    })),
    imageCount: document.images.length,
    completeImageCount: [...document.images].filter(image => image.complete && image.naturalWidth > 0).length,
    failedImageCount: [...document.images].filter(image => image.complete && image.naturalWidth === 0).length
  };
})()
"""#

while Date() < deadline {
    guard let target = pageTarget(),
          let socketText = target["webSocketDebuggerUrl"] as? String,
          let socketURL = URL(string: socketText) else {
        Thread.sleep(forTimeInterval: 0.25)
        continue
    }

    if firstTargetSeenAt == nil { firstTargetSeenAt = Date() }
    if let firstTargetSeenAt, Date().timeIntervalSince(firstTargetSeenAt) < delay {
        Thread.sleep(forTimeInterval: 0.25)
        continue
    }

    let socket = session.webSocketTask(with: socketURL)
    socket.resume()

    guard let evaluation = sendCommand(
        "Runtime.evaluate",
        params: [
            "expression": diagnosticExpression,
            "returnByValue": true,
            "awaitPromise": true,
        ],
        using: socket,
        id: 1
    ),
    let evaluationResult = evaluation["result"] as? [String: Any],
    let remoteResult = evaluationResult["result"] as? [String: Any],
    let diagnostics = remoteResult["value"] as? [String: Any] else {
        socket.cancel(with: .goingAway, reason: nil)
        Thread.sleep(forTimeInterval: 0.25)
        continue
    }
    let href = diagnostics["href"] as? String ?? ""
    let readyState = diagnostics["readyState"] as? String ?? ""
    let bodyHTMLLength = diagnostics["bodyHTMLLength"] as? Int ?? 0
    let visibleElementCount = diagnostics["visibleElementCount"] as? Int ?? 0
    let resourceCount = diagnostics["resourceCount"] as? Int ?? 0
    let visibleText = diagnostics["visibleTextSample"] as? String ?? ""
    let visibleLoadingElementCount = diagnostics["visibleLoadingElementCount"] as? Int ?? 0
    // Small but complete diagnostic pages (for example example.com) are valid
    // Chromium render targets; the visible DOM check still rejects blank tabs.
    guard href != "about:blank", bodyHTMLLength > 100, visibleElementCount > 0 else {
        socket.cancel(with: .goingAway, reason: nil)
        Thread.sleep(forTimeInterval: 0.35)
        continue
    }
    if href.hasPrefix("http://127.0.0.1:"), href.hasSuffix("/browser/") {
        let requiredText = ["Object Explorer", "Servers", "Dashboard", "pgAdmin"]
        let pgAdminReady = readyState == "complete"
            && bodyHTMLLength >= 50_000
            && visibleElementCount >= 100
            && resourceCount >= 20
            && visibleLoadingElementCount == 0
            && requiredText.allSatisfy(visibleText.contains)
        guard pgAdminReady else {
            socket.cancel(with: .goingAway, reason: nil)
            Thread.sleep(forTimeInterval: 0.5)
            continue
        }
    }

    let report: [String: Any] = [
        "target": [
            "id": target["id"] ?? "",
            "title": target["title"] ?? "",
            "url": target["url"] ?? "",
        ],
        "diagnostics": diagnostics,
    ]
    let reportData = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
    try FileManager.default.createDirectory(
        at: reportURL.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    try reportData.write(to: reportURL)

    guard let screenshot = sendCommand(
        "Page.captureScreenshot",
        params: ["format": "png", "fromSurface": true, "captureBeyondViewport": false],
        using: socket,
        id: 2
    ),
    let screenshotResult = screenshot["result"] as? [String: Any],
    let base64 = screenshotResult["data"] as? String,
    let imageData = Data(base64Encoded: base64) else {
        socket.cancel(with: .goingAway, reason: nil)
        fputs("CDP diagnostics written but screenshot capture failed\n", stderr)
        exit(1)
    }
    try imageData.write(to: screenshotURL)
    socket.cancel(with: .normalClosure, reason: nil)
    print("report=\(reportURL.path)")
    print("screenshot=\(screenshotURL.path)")
    exit(0)
}

fputs("Chromium page inspection timed out\n", stderr)
exit(1)
