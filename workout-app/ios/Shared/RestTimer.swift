import SwiftUI
import UserNotifications

/// A local notification so the wrist (or phone) buzzes when rest ends even if the app isn't in the foreground.
enum RestAlert {
    static func schedule(after seconds: Int, next: String) {
        guard seconds > 0 else { return }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = "Rest over"
            content.body = "Next: \(next)"
            content.sound = .default
            let trigger = UNTimeIntervalNotificationTrigger(timeInterval: TimeInterval(seconds), repeats: false)
            center.add(UNNotificationRequest(identifier: "rest-timer", content: content, trigger: trigger))
        }
    }

    static func cancel() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["rest-timer"])
    }
}

/// Counts down to `endDate`. Computed from the clock, so it stays correct if the view is re-created or the app sleeps.
struct RestCountdown: View {
    let endDate: Date
    var onFinish: () -> Void

    var body: some View {
        TimelineView(.periodic(from: .now, by: 0.5)) { context in
            let remaining = max(0, Int(ceil(endDate.timeIntervalSince(context.date))))
            Text(String(format: "%d:%02d", remaining / 60, remaining % 60))
                .font(.system(size: 40, weight: .bold, design: .rounded))
                .monospacedDigit()
                .onChange(of: remaining) { _, r in if r == 0 { onFinish() } }
                .onAppear { if remaining == 0 { onFinish() } }
        }
    }
}
