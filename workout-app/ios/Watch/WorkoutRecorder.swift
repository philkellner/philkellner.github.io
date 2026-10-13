import Foundation
import HealthKit

/// Runs an Apple Health strength-training session on the Watch: live heart rate and calories, keeps the app
/// running between sets, and saves the finished workout to Health. If Health access is denied, the workout still
/// works; there is just no heart-rate data.
final class WorkoutRecorder: NSObject, ObservableObject {
    enum State { case idle, running, unavailable }

    @Published private(set) var state: State = .idle
    @Published private(set) var heartRate: Double = 0
    @Published private(set) var activeCalories: Double = 0
    /// The server session being recorded.
    private(set) var recordingFor: Int?

    private let store = HKHealthStore()
    private var session: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?
    private var startDate = Date()

    static let externalIDPrefix = "workout-app-session-"
    private let bpm = HKUnit.count().unitDivided(by: .minute())

    var isRunning: Bool { state == .running }

    func start(sessionId: Int) async {
        guard HKHealthStore.isHealthDataAvailable() else { return await setState(.unavailable) }
        if isRunning {
            if recordingFor == sessionId { return }
            await discard()          // a different workout was abandoned without finishing
        }
        do {
            try await store.requestAuthorization(
                toShare: [HKObjectType.workoutType()],
                read: [HKQuantityType(.heartRate), HKQuantityType(.activeEnergyBurned)])

            let config = HKWorkoutConfiguration()
            config.activityType = .traditionalStrengthTraining
            config.locationType = .indoor

            let session = try HKWorkoutSession(healthStore: store, configuration: config)
            let builder = session.associatedWorkoutBuilder()
            builder.dataSource = HKLiveWorkoutDataSource(healthStore: store, workoutConfiguration: config)
            session.delegate = self
            builder.delegate = self

            self.session = session
            self.builder = builder
            self.recordingFor = sessionId
            startDate = Date()
            session.startActivity(with: startDate)
            try await builder.beginCollection(at: startDate)
            try await builder.addMetadata([HKMetadataKeyExternalUUID: Self.externalIDPrefix + String(sessionId)])
            await MainActor.run { self.heartRate = 0; self.activeCalories = 0; self.state = .running }
        } catch {
            cleanUp()
            await setState(.unavailable)
        }
    }

    /// Ends the session, saves the workout to Apple Health and returns what was measured.
    func end() async -> WorkoutSummary? {
        guard isRunning, let session, let builder else { return nil }
        let endDate = Date()
        session.end()
        defer { cleanUp() }
        do {
            try await builder.endCollection(at: endDate)
            let workout = try await builder.finishWorkout()
            let hr = builder.statistics(for: HKQuantityType(.heartRate))
            let energy = builder.statistics(for: HKQuantityType(.activeEnergyBurned))
            return WorkoutSummary(
                avgHeartRate: hr?.averageQuantity()?.doubleValue(for: bpm),
                maxHeartRate: hr?.maximumQuantity()?.doubleValue(for: bpm),
                activeCalories: energy?.sumQuantity()?.doubleValue(for: .kilocalorie()),
                durationSeconds: Int(endDate.timeIntervalSince(startDate)),
                healthkitUUID: workout?.uuid.uuidString)
        } catch {
            return nil
        }
    }

    /// Stops recording without saving anything to Health.
    func discard() async {
        guard let session, let builder else { return }
        session.end()
        builder.discardWorkout()
        cleanUp()
        await setState(.idle)
    }

    private func cleanUp() {
        session = nil
        builder = nil
        recordingFor = nil
        DispatchQueue.main.async { if self.state == .running { self.state = .idle } }
    }

    private func setState(_ s: State) async {
        await MainActor.run { self.state = s }
    }
}

extension WorkoutRecorder: HKWorkoutSessionDelegate, HKLiveWorkoutBuilderDelegate {
    func workoutSession(_ workoutSession: HKWorkoutSession, didChangeTo toState: HKWorkoutSessionState,
                        from fromState: HKWorkoutSessionState, date: Date) {}

    func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {
        DispatchQueue.main.async { self.state = .unavailable }
    }

    func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {}

    func workoutBuilder(_ workoutBuilder: HKLiveWorkoutBuilder, didCollectDataOf collectedTypes: Set<HKSampleType>) {
        for type in collectedTypes {
            guard let q = type as? HKQuantityType, let stats = workoutBuilder.statistics(for: q) else { continue }
            DispatchQueue.main.async {
                if q == HKQuantityType(.heartRate) {
                    self.heartRate = stats.mostRecentQuantity()?.doubleValue(for: self.bpm) ?? self.heartRate
                } else if q == HKQuantityType(.activeEnergyBurned) {
                    self.activeCalories = stats.sumQuantity()?.doubleValue(for: .kilocalorie()) ?? self.activeCalories
                }
            }
        }
    }
}
