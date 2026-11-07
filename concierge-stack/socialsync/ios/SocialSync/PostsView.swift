import SwiftUI

struct PostsView: View {
    enum Filter: String, CaseIterable, Identifiable {
        case all = "All"
        case drafts = "Drafts"
        case scheduled = "Scheduled"
        case posted = "Posted"
        var id: String { rawValue }
    }

    @Environment(AppStore.self) private var store
    @State private var filter: Filter = .all
    @State private var pendingDelete: Post?

    private var shown: [Post] {
        store.posts.filter { post in
            switch filter {
            case .all: return true
            case .drafts: return post.status == .draft
            case .scheduled: return post.status == .scheduled
            case .posted: return post.status == .posted
            }
        }
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Picker("Show", selection: $filter) {
                        ForEach(Filter.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                }
                .listRowBackground(Color.clear)

                if shown.isEmpty {
                    Text("Nothing here yet.").foregroundStyle(.secondary)
                }

                ForEach(shown) { post in
                    NavigationLink(value: post.id) { PostRow(post: post) }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) {
                                pendingDelete = post
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                        .swipeActions(edge: .leading) {
                            Button {
                                Task {
                                    do {
                                        let copy = try await store.duplicate(post)
                                        store.edit(copy)
                                    } catch {
                                        store.handle(error)
                                    }
                                }
                            } label: {
                                Label("Duplicate", systemImage: "plus.square.on.square")
                            }
                            .tint(.indigo)
                        }
                }
            }
            .navigationTitle("Posts")
            .navigationDestination(for: Int.self) { id in PostDetailView(postID: id) }
            .refreshable { await store.refresh() }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { store.startNewPost() } label: { Image(systemName: "plus") }
                        .accessibilityLabel("New post")
                }
            }
            .confirmationDialog(
                "Delete this post for good?",
                isPresented: Binding(get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }),
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    if let post = pendingDelete {
                        Task {
                            do { try await store.delete(post) } catch { store.handle(error) }
                        }
                    }
                    pendingDelete = nil
                }
                Button("Cancel", role: .cancel) { pendingDelete = nil }
            }
        }
    }
}

struct PostDetailView: View {
    let postID: Int
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @State private var notice: String?
    @State private var confirmPosted = false
    @State private var confirmDelete = false
    @State private var copied = false

    private var post: Post? { store.posts.first { $0.id == postID } }

    var body: some View {
        if let post {
            List {
                Section {
                    HStack {
                        StatusBadge(post: post)
                        PlatformRow(ids: post.platforms)
                    }
                    if let date = post.scheduledAt, post.status != .posted {
                        LabeledContent("Scheduled for", value: date.formatted(date: .abbreviated, time: .shortened))
                    }
                    if let date = post.postedAt, post.status == .posted {
                        LabeledContent("Posted", value: date.formatted(date: .abbreviated, time: .shortened))
                    }
                }

                Section("Text") {
                    Text(post.shareText.isEmpty ? "(no text)" : post.shareText)
                        .textSelection(.enabled)
                    MediaStrip(ids: post.mediaIds)
                }

                if post.status != .posted, !post.platforms.isEmpty {
                    Section {
                        ForEach(store.publishTargets(for: post)) { target in
                            Button {
                                UIPasteboard.general.string = post.shareText
                                notice = target.hint
                                if let url = target.url { openURL(url) }
                            } label: {
                                Label(target.label, systemImage: "arrow.up.right.square")
                            }
                            .disabled(target.url == nil)
                        }
                    } header: {
                        Text("Post now")
                    } footer: {
                        Text(notice ?? "Tap a platform: the text is copied, then that platform opens.")
                    }
                }

                Section {
                    ShareLink(item: post.shareText) {
                        Label("Share or copy to a platform", systemImage: "square.and.arrow.up")
                    }
                    Button {
                        UIPasteboard.general.string = post.shareText
                        copied = true
                    } label: {
                        Label(copied ? "Copied" : "Copy text", systemImage: copied ? "checkmark" : "doc.on.doc")
                    }
                }

                Section {
                    if post.status != .posted {
                        Button { store.edit(post) } label: { Label("Edit", systemImage: "pencil") }
                        Button { confirmPosted = true } label: {
                            Label("Mark as posted", systemImage: "checkmark.circle")
                        }
                    }
                    if post.status == .scheduled {
                        Button {
                            run { try await store.unschedule(post) }
                        } label: {
                            Label("Unschedule", systemImage: "calendar.badge.minus")
                        }
                    }
                    Button {
                        run {
                            let copy = try await store.duplicate(post)
                            store.edit(copy)
                        }
                    } label: {
                        Label("Duplicate", systemImage: "plus.square.on.square")
                    }
                    Button(role: .destructive) { confirmDelete = true } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }
            .navigationTitle("Post")
            .navigationBarTitleDisplayMode(.inline)
            .confirmationDialog(
                "Only mark this as posted once it is live on the platforms.",
                isPresented: $confirmPosted,
                titleVisibility: .visible
            ) {
                Button("Mark as posted") {
                    run { try await store.markPosted(post) }
                }
                Button("Cancel", role: .cancel) {}
            }
            .confirmationDialog(
                "Delete this post for good?",
                isPresented: $confirmDelete,
                titleVisibility: .visible
            ) {
                Button("Delete", role: .destructive) {
                    run {
                        try await store.delete(post)
                        dismiss()
                    }
                }
                Button("Cancel", role: .cancel) {}
            }
        } else {
            ContentUnavailableView("Post not found", systemImage: "questionmark.folder")
        }
    }

    private func run(_ work: @escaping () async throws -> Void) {
        Task {
            do { try await work() } catch { store.handle(error) }
        }
    }
}
