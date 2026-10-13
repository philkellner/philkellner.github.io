import Foundation
import HealthKit

/// Saves a finished workout to Apple Health from the iPhone, for workouts done without the Watch recording them.
/// There is no heart-rate data in that case. Skipped when Health already has this workout (tagged by session id).
enum PhoneHealth {
    static func saveIfNeeded(_ session: WorkoutSession) async {
        guard HKHealthStore.isHealthDataAvailable(), session.source != "watch", session.health == nil,
              let start = parseISO(session.startedAt), let finish = session.finishedAt.flatMap(parseISO), finish > start
        else { return }
        let store = HKHealthStore()
        let tag = WorkoutRecorder.externalIDPrefix + String(session.id)
        do {
            try await store.requestAuthorization(toShare: [HKObjectType.workoutType()], read: [HKObjectType.workoutType()])
            let existing = HKSampleQueryDescriptor(
                predicates: [.workout(HKQuery.predicateForObjects(withMetadataKey: HKMetadataKeyExternalUUID,
                                                                  operatorType: .equalTo, value: tag))],
                sortDescriptors: [], limit: 1)
            if try await !existing.result(for: store).isEmpty { return }

            let config = HKWorkoutConfiguration()
            config.activityType = .traditionalStrengthTraining
            config.locationType = .indoor
            let builder = HKWorkoutBuilder(healthStore: store, configuration: config, device: .local())
            try await builder.beginCollection(at: start)
            try await builder.addMetadata([HKMetadataKeyExternalUUID: tag, HKMetadataKeyWorkoutBrandName: "Workout"])
            try await builder.endCollection(at: finish)
            _ = try await builder.finishWorkout()
        } catch {
            // Health is optional: a denied permission or a Health error must never block finishing a workout.
        }
    }
}
