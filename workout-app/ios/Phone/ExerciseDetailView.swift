import SwiftUI
import AVKit

/// Muted, endlessly looping clip.
struct LoopingVideo: View {
    let url: URL
    @State private var player: AVQueuePlayer?
    @State private var looper: AVPlayerLooper?

    var body: some View {
        Group {
            if let player { VideoPlayer(player: player) } else { Color.black.opacity(0.05) }
        }
        .aspectRatio(16 / 9, contentMode: .fit)
        .onAppear {
            guard player == nil else { player?.play(); return }
            let queue = AVQueuePlayer()
            queue.isMuted = true
            looper = AVPlayerLooper(player: queue, templateItem: AVPlayerItem(url: url))
            player = queue
            queue.play()
        }
        .onDisappear { player?.pause() }
    }
}

/// A quick reminder of how to do an exercise: the written steps are the source of truth, the video is a visual aid.
struct ExerciseDetailView: View {
    let exercise: String
    @State private var info: ExerciseInfo?
    @State private var videoURL: URL?
    @State private var error: String?

    var body: some View {
        List {
            if let error { Text(error).foregroundStyle(.red) }
            if let videoURL {
                Section {
                    LoopingVideo(url: videoURL).listRowInsets(EdgeInsets())
                } footer: {
                    Text("AI-generated reminder clip. Follow the written steps below if it differs.")
                }
            }
            if let info {
                if !info.cues.isEmpty {
                    Section("Form") {
                        ForEach(Array(info.cues.enumerated()), id: \.offset) { i, cue in
                            HStack(alignment: .top) {
                                Text("\(i + 1).").foregroundStyle(.secondary)
                                Text(cue.prefix(1).uppercased() + cue.dropFirst())
                            }
                        }
                    }
                }
                Section("Works") {
                    LabeledContent("Main muscles", value: info.primary.joined(separator: ", ").capitalized)
                    if !info.secondary.isEmpty {
                        LabeledContent("Also", value: info.secondary.joined(separator: ", ").capitalized)
                    }
                    LabeledContent("Equipment", value: info.equipment.capitalized)
                }
                if !info.youtube.isEmpty {
                    Section("Popular tutorials on YouTube") {
                        ForEach(info.youtube) { v in
                            if let url = URL(string: v.url) {
                                Link(destination: url) {
                                    VStack(alignment: .leading) {
                                        Text(v.title)
                                        Text("\(v.channel) · \(v.views.formatted(.number.notation(.compactName))) views")
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(exercise)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            guard let c = APIConfig.load() else { return }
            let api = APIClient(config: c)
            do {
                let i = try await api.info(exercise: exercise)
                info = i
                videoURL = i.videoUrl.flatMap { api.absoluteURL($0) }
            } catch { self.error = error.localizedDescription }
        }
    }
}
