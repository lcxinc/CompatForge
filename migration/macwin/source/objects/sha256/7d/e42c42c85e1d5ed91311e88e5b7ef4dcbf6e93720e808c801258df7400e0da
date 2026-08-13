import Foundation

let arguments = CommandLine.arguments
guard arguments.count >= 2, let port = Int(arguments[1]) else {
    fputs("usage: repair-lenovo-app-store-page <port> [timeout-seconds]\n", stderr)
    exit(2)
}

let timeout = arguments.count >= 3 ? (Double(arguments[2]) ?? 60) : 60
let deadline = Date().addingTimeInterval(timeout)
let session = URLSession(configuration: .ephemeral)

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

func pageSocketURL() -> URL? {
    let endpoint = URL(string: "http://127.0.0.1:\(port)/json/list")!
    guard let pages = loadJSON(endpoint) as? [[String: Any]] else { return nil }
    for page in pages where page["type"] as? String == "page" {
        if let rawURL = page["webSocketDebuggerUrl"] as? String,
           let url = URL(string: rawURL) {
            return url
        }
    }
    return nil
}

func evaluate(_ expression: String, using task: URLSessionWebSocketTask, id: Int) -> String? {
    let payload: [String: Any] = [
        "id": id,
        "method": "Runtime.evaluate",
        "params": [
            "expression": expression,
            "returnByValue": true,
            "awaitPromise": true,
        ],
    ]
    guard let data = try? JSONSerialization.data(withJSONObject: payload),
          let text = String(data: data, encoding: .utf8) else { return nil }

    let sendSemaphore = DispatchSemaphore(value: 0)
    var sendError: Error?
    task.send(.string(text)) { error in
        sendError = error
        sendSemaphore.signal()
    }
    _ = sendSemaphore.wait(timeout: .now() + 2)
    if sendError != nil { return nil }

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
        let result = response["result"] as? [String: Any]
        let remoteResult = result?["result"] as? [String: Any]
        return remoteResult?["value"] as? String
    }
    return nil
}

let repairExpression = #"""
(() => {
  const store = window._reduxStore;
  if (!store) return "not-ready:store";
  const state = store.getState();
  const native = state && state.native;
  const recommend = state && state.recommend;
  if (!native) return "not-ready:native";
  if (!recommend) return "not-ready:recommend";
  if (native.commandLineReady !== true) {
    store.dispatch({ type: "SET_COMMAND_LINE_READY", ready: true });
    return "patched-command-line-ready";
  }
  const exploreEntry = state && state.exploreEntry;
  if (!exploreEntry) return "not-ready:explore-entry";
  if (exploreEntry.initialized !== true) {
    const commandLine = String(native.commandLine || "");
    if (/(^|\s)-c\s+/.test(commandLine)) return "not-ready:special-command-line";
    store.dispatch({
      type: "EXPLORE_ENTRY_INIT",
      payload: { commandLineMode: "none", entrySource: "cold_start" }
    });
    return "patched-explore-entry";
  }
  if (recommend.recoBanner && Array.isArray(recommend.recoBanner.data) && recommend.recoBanner.data.length) {
    return "already-renderable";
  }
  const cards = recommend.recoRecommend && recommend.recoRecommend.pageCardList;
  if (!Array.isArray(cards) || !cards.length) return "not-ready:cards";
  if (!recommend.recoBannerDataIsResponse) return "not-ready:banner-response";
  const entries = performance.getEntriesByType("resource")
    .filter(entry => entry.name.includes("/appstorecontents/page/top_contents"));
  if (!entries.length) return "not-ready:request";
  const requestURL = new URL(entries[entries.length - 1].name);
  const getBannerKey = Number(requestURL.searchParams.get("time"));
  if (!Number.isFinite(getBannerKey)) return "not-ready:key";
  store.dispatch({
    type: "RECO_TOP_CONTENTS_SUCCESS",
    payload: {
      status: 0,
      message: "MacWin empty-banner compatibility fallback",
      data: [cards[0]],
      getBannerKey,
      pageType: "soft"
    }
  });
  return "patched-empty-banner";
})()
"""#

var requestID = 1
while Date() < deadline {
    guard let socketURL = pageSocketURL() else {
        Thread.sleep(forTimeInterval: 0.25)
        continue
    }
    let socket = session.webSocketTask(with: socketURL)
    socket.resume()
    while Date() < deadline {
        if let status = evaluate(repairExpression, using: socket, id: requestID) {
            print(status)
            if status == "patched-empty-banner" || status == "already-renderable" {
                socket.cancel(with: .normalClosure, reason: nil)
                exit(0)
            }
        }
        requestID += 1
        Thread.sleep(forTimeInterval: 0.35)
    }
    socket.cancel(with: .goingAway, reason: nil)
}

fputs("Lenovo page repair timed out\n", stderr)
exit(1)
