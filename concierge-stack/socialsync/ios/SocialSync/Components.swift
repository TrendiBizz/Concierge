import SwiftUI

struct PlatformBadge: View {
    let platform: Platform

    var body: some View {
        Text(platform.tag)
            .font(.caption.bold())
            .foregroundStyle(.white)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(platform.color, in: Capsule())
            .accessibilityLabel(platform.label)
    }
}

struct PlatformRow: View {
    let ids: [String]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(ids, id: \.self) { id in
                if let platform = Platform(rawValue: id) {
                    PlatformBadge(platform: platform)
                }
            }
        }
    }
}

struct StatusBadge: View {
    let post: Post

    private var tint: Color {
        if post.isDue { return .orange }
        switch post.status {
        case .draft: return .blue
        case .scheduled: return .green
        case .posted: return .gray
        }
    }

    var body: some View {
        Text(post.statusLabel)
            .font(.caption.bold())
            .foregroundStyle(tint)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(tint.opacity(0.15), in: Capsule())
    }
}

/// A square thumbnail of a library item. Pass a size for a fixed square, or nil to fill the width.
struct MediaThumb: View {
    @Environment(AppStore.self) private var store
    let item: MediaItem
    var size: CGFloat?

    var body: some View {
        let base = Color(.secondarySystemBackground)
        Group {
            if let size {
                base.frame(width: size, height: size)
            } else {
                base.aspectRatio(1, contentMode: .fit)
            }
        }
        .overlay {
            if item.isVideo {
                Image(systemName: "play.rectangle.fill")
                    .font(.title)
                    .foregroundStyle(.secondary)
            } else {
                AsyncImage(url: store.mediaURL(item)) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill()
                    case .failure:
                        Image(systemName: "photo").foregroundStyle(.secondary)
                    default:
                        ProgressView()
                    }
                }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .accessibilityLabel(item.caption.isEmpty ? item.filename : item.caption)
    }
}

struct MediaStrip: View {
    @Environment(AppStore.self) private var store
    let ids: [Int]

    var body: some View {
        let items = ids.compactMap { id in store.media.first { $0.id == id } }
        if !items.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack {
                    ForEach(items) { item in
                        MediaThumb(item: item, size: 72)
                    }
                }
            }
        }
    }
}

struct PostRow: View {
    let post: Post

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                StatusBadge(post: post)
                PlatformRow(ids: post.platforms)
                Spacer()
                if let date = post.calendarDate {
                    Text(date.formatted(date: .abbreviated, time: .shortened))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Text(post.content.isEmpty ? "(no text)" : post.content)
                .lineLimit(3)
        }
        .padding(.vertical, 2)
    }
}
