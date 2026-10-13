import SwiftUI
import WatchConnectivity
import WatchKit

/// Receives server URL + token from the iPhone app.
final class PhoneLink: NSObject, WCSessionDelegate, ObservableObject {
    @Published var config = APIConfig.load()

    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }

    private func apply(_ ctx: [String: Any]) {
        if let lb = ctx["useLb"] as? Bool { Units.useLb = lb }
        guard let url = ctx["baseURL"] as? String, let token = ctx["token"] as? String else { return }
        let c = APIConfig(baseURL: url, token: token)
        c.save()
        DispatchQueue.main.async { self.config = c }
    }

    func session(_ s: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        apply(s.receivedApplicationContext)
    }
    func session(_ s: WCSession, didReceiveApplicationContext ctx: [String: Any]) { apply(ctx) }
}

@main
struct WorkoutWatchApp: App {
    @StateObject private var link = PhoneLink()
    @StateObject private var recorder = WorkoutRecorder()
    var body: some Scene {
        WindowGroup {
            Group {
                if let config = link.config { WatchHome(api: APIClient(config: config)).environmentObject(recorder) }
                else { Text("Open the Workout app on your iPhone and save the server settings.").padding() }
            }
            .onAppear { link.activate() }
        }
    }
}
