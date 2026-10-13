import SwiftUI
import WatchConnectivity

/// Pushes the server URL + token to the Watch so it can talk to the API directly.
final class WatchLink: NSObject, WCSessionDelegate {
    static let shared = WatchLink()

    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    func send(_ config: APIConfig) {
        guard WCSession.default.activationState == .activated else { return }
        try? WCSession.default.updateApplicationContext(["baseURL": config.baseURL, "token": config.token, "useLb": Units.useLb])
    }

    func session(_ s: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        if state == .activated, let c = APIConfig.load() { send(c) }
    }
    func sessionDidBecomeInactive(_ s: WCSession) {}
    func sessionDidDeactivate(_ s: WCSession) { s.activate() }
}

@main
struct WorkoutApp: App {
    init() { WatchLink.shared.activate() }
    var body: some Scene { WindowGroup { RootView() } }
}
