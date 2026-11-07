import SwiftUI

func channelLabel(_ platform: String) -> String {
    switch platform {
    case "facebook": return "Facebook"
    case "instagram": return "Instagram"
    case "linkedin": return "LinkedIn"
    case "twitter": return "X"
    case "youtube": return "YouTube"
    case "tiktok": return "TikTok"
    case "google": return "Google Business Profile"
    case "website": return "Website"
    default: return "Other"
    }
}

/// Every page and account Pukeko uses, in one list. Tap one to open it.
struct SocialPagesView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.openURL) private var openURL
    @State private var editing: Channel?
    @State private var adding = false
    @State private var pendingDelete: Channel?

    private var hasLinkedIn: Bool {
        store.channels.contains { $0.platform == "linkedin" }
    }

    var body: some View {
        List {
            if !hasLinkedIn {
                Section {
                    Label(
                        "No LinkedIn page yet. The Pukeko website does not link to one. Add its address with the + button.",
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .foregroundStyle(.orange)
                }
            }

            Section {
                if store.channels.isEmpty {
                    Text("No pages yet.").foregroundStyle(.secondary)
                }
                ForEach(store.channels) { channel in
                    Button {
                        if let url = URL(string: channel.url) { openURL(url) }
                    } label: {
                        HStack(spacing: 12) {
                            if let platform = Platform(rawValue: channel.platform) {
                                PlatformBadge(platform: platform)
                            } else {
                                Image(systemName: "globe").foregroundStyle(.secondary)
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(channel.name).bold().foregroundStyle(.primary)
                                Text(channelLabel(channel.platform)).font(.caption).foregroundStyle(.secondary)
                                Text(channel.url).font(.caption).foregroundStyle(.tint).lineLimit(1)
                                if !channel.notes.isEmpty {
                                    Text(channel.notes).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            Image(systemName: "arrow.up.right.square").foregroundStyle(.tint)
                        }
                    }
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) { pendingDelete = channel } label: {
                            Label("Remove", systemImage: "trash")
                        }
                        Button { editing = channel } label: {
                            Label("Edit", systemImage: "pencil")
                        }
                        .tint(.blue)
                    }
                    .contextMenu {
                        Button {
                            UIPasteboard.general.string = channel.url
                        } label: {
                            Label("Copy link", systemImage: "doc.on.doc")
                        }
                        Button { editing = channel } label: {
                            Label("Edit", systemImage: "pencil")
                        }
                    }
                }
            } footer: {
                Text("Tap a page to open it. Swipe to edit or remove. Removing a page here does not touch the real page.")
            }
        }
        .navigationTitle("Social pages")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { adding = true } label: { Image(systemName: "plus") }
                    .accessibilityLabel("Add page")
            }
        }
        .refreshable { await store.refresh() }
        .sheet(isPresented: $adding) { ChannelForm(channel: nil) }
        .sheet(item: $editing) { channel in ChannelForm(channel: channel) }
        .confirmationDialog(
            "Remove this page from the list?",
            isPresented: Binding(get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }),
            titleVisibility: .visible
        ) {
            Button("Remove", role: .destructive) {
                if let channel = pendingDelete {
                    Task {
                        do { try await store.deleteChannel(channel) } catch { store.handle(error) }
                    }
                }
                pendingDelete = nil
            }
            Button("Cancel", role: .cancel) { pendingDelete = nil }
        }
    }
}

struct ChannelForm: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let channel: Channel?
    @State private var platform: String
    @State private var name: String
    @State private var url: String
    @State private var notes: String
    @State private var error: String?
    @State private var busy = false

    init(channel: Channel?) {
        self.channel = channel
        _platform = State(initialValue: channel?.platform ?? "linkedin")
        _name = State(initialValue: channel?.name ?? "")
        _url = State(initialValue: channel?.url ?? "")
        _notes = State(initialValue: channel?.notes ?? "")
    }

    private var platforms: [String] {
        store.channelPlatforms.isEmpty ? ["facebook", "instagram", "linkedin", "twitter", "other"] : store.channelPlatforms
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker("Platform", selection: $platform) {
                        ForEach(platforms, id: \.self) { Text(channelLabel($0)).tag($0) }
                    }
                    TextField("Page name, e.g. Pukeko Construction", text: $name)
                    TextField("https://www.linkedin.com/company/…", text: $url)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("Notes (optional)", text: $notes)
                } footer: {
                    Text("Use the full address of the page, starting with https://")
                }
                if let error {
                    Section { Text(error).foregroundStyle(.red) }
                }
            }
            .navigationTitle(channel == nil ? "Add page" : "Edit page")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                        .disabled(busy || name.trimmingCharacters(in: .whitespaces).isEmpty || url.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await store.saveChannel(id: channel?.id, platform: platform, name: name, url: url, notes: notes)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
