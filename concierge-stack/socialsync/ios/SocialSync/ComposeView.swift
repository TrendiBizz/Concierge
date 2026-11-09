import PhotosUI
import SwiftUI

struct ComposeView: View {
    @Environment(AppStore.self) private var store
    @State private var check: Check?
    @State private var checkTask: Task<Void, Never>?
    @State private var showLibrary = false
    @State private var pickerItems: [PhotosPickerItem] = []
    @State private var busy = false
    @State private var message: String?
    @State private var messageIsError = false

    private var platforms: [Platform] {
        let order = store.rules?.platformOrder.compactMap { Platform(rawValue: $0) } ?? []
        return order.isEmpty ? Platform.allCases : order
    }

    private var locked: Bool { store.draft.status == .posted }

    var body: some View {
        @Bindable var store = store
        NavigationStack {
            Form {
                if let message {
                    Section {
                        Text(message).foregroundStyle(messageIsError ? Color.red : Color.green)
                    }
                }

                if locked {
                    Section {
                        Text("This post is already marked as posted. Use Duplicate on the Posts tab to reuse it.")
                            .foregroundStyle(.orange)
                    }
                }

                Section("Platforms") {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(platforms) { platform in
                            platformChip(platform)
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section {
                    TextEditor(text: $store.draft.content)
                        .frame(minHeight: 140)
                    HStack {
                        Spacer()
                        Text("\(store.draft.content.count) characters")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Post text")
                }

                Section("Link and hashtags") {
                    TextField("Link (optional)", text: $store.draft.link)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("#recladding #auckland", text: $store.draft.hashtags)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                Section("Photos and videos") {
                    if store.draft.mediaIds.isEmpty {
                        Text("No photos or videos added.").foregroundStyle(.secondary)
                    } else {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 10) {
                                ForEach(store.draft.mediaIds, id: \.self) { id in
                                    if let item = store.media.first(where: { $0.id == id }) {
                                        ZStack(alignment: .topTrailing) {
                                            MediaThumb(item: item, size: 84)
                                            if !locked {
                                                Button {
                                                    store.draft.mediaIds.removeAll { $0 == id }
                                                } label: {
                                                    Image(systemName: "xmark.circle.fill")
                                                        .font(.title3)
                                                        .foregroundStyle(.white, .black.opacity(0.6))
                                                }
                                                .buttonStyle(.borderless)
                                                .padding(3)
                                                .accessibilityLabel("Remove")
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    if !locked {
                        Button("Choose from library") { showLibrary = true }
                        PhotosPicker(
                            selection: $pickerItems,
                            maxSelectionCount: 10,
                            matching: .any(of: [.images, .videos])
                        ) {
                            Label("Upload new", systemImage: "plus")
                        }
                    }
                }

                Section("Publish") {
                    DatePicker("Date and time", selection: $store.draft.when, displayedComponents: [.date, .hourAndMinute])
                        .disabled(locked)
                }

                checksSection
                previewSection

                if !locked {
                    Section {
                        Button("Save draft") { Task { _ = await save() } }
                        Button(store.draft.status == .scheduled ? "Update schedule" : "Schedule") {
                            Task { await schedule() }
                        }
                        .bold()
                        if store.draft.status == .scheduled, store.draft.id != nil {
                            Button("Unschedule") { Task { await unschedule() } }
                        }
                    }
                    .disabled(busy)
                }
            }
            .navigationTitle(store.draft.id == nil ? "New post" : "Edit post")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("New") {
                        store.startNewPost()
                        check = nil
                        message = nil
                    }
                }
            }
            .onChange(of: store.draft) { _, _ in scheduleCheck() }
            .onChange(of: pickerItems) { _, items in
                if !items.isEmpty { Task { await upload(items) } }
            }
            .onAppear { scheduleCheck() }
            .sheet(isPresented: $showLibrary) {
                LibraryPicker(selection: $store.draft.mediaIds)
            }
        }
    }

    // MARK: Sections

    private func platformChip(_ platform: Platform) -> some View {
        let isOn = store.draft.platforms.contains(platform.rawValue)
        return Button {
            if isOn {
                store.draft.platforms.remove(platform.rawValue)
            } else {
                store.draft.platforms.insert(platform.rawValue)
            }
        } label: {
            HStack(spacing: 6) {
                PlatformBadge(platform: platform)
                Text(platform.label).lineLimit(1)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(isOn ? platform.color.opacity(0.18) : Color(.secondarySystemBackground), in: Capsule())
            .overlay(Capsule().stroke(isOn ? platform.color : Color.clear, lineWidth: 1.5))
        }
        .buttonStyle(.borderless)
        .disabled(locked)
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }

    @ViewBuilder
    private var checksSection: some View {
        Section("Checks") {
            if let check {
                ForEach(check.errors) { issue in
                    Label(issue.message, systemImage: "xmark.octagon.fill").foregroundStyle(.red)
                }
                ForEach(check.warnings) { issue in
                    Label(issue.message, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                }
                if check.ok, check.warnings.isEmpty, !store.draft.content.isEmpty, !store.draft.platforms.isEmpty {
                    Label("Passes all Pukeko checks.", systemImage: "checkmark.seal.fill").foregroundStyle(.green)
                }
            } else {
                Text("Checks run as you type.").foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var previewSection: some View {
        Section("Preview") {
            let selected = platforms.filter { store.draft.platforms.contains($0.rawValue) }
            if selected.isEmpty {
                Text("Pick a platform to see how the post will look.").foregroundStyle(.secondary)
            }
            ForEach(selected) { platform in
                let rule = store.rules?.platforms[platform.rawValue]
                let length = store.draft.length(for: rule)
                let over = rule.map { length > $0.limit } ?? false
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        PlatformBadge(platform: platform)
                        Text(platform.label).font(.subheadline.bold())
                    }
                    Text(store.draft.content.isEmpty ? "Your text appears here." : store.draft.content)
                    if !store.draft.link.isEmpty {
                        Text(store.draft.link).foregroundStyle(.tint)
                    }
                    if !store.draft.hashtags.isEmpty {
                        Text(store.draft.hashtags).foregroundStyle(.tint)
                    }
                    MediaStrip(ids: store.draft.mediaIds)
                    HStack {
                        Spacer()
                        Text("\(length) / \(rule?.limit ?? 0) characters")
                            .font(.caption)
                            .foregroundStyle(over ? Color.red : Color.secondary)
                            .bold(over)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }

    // MARK: Actions

    private func show(_ text: String, isError: Bool) {
        message = text
        messageIsError = isError
    }

    private func report(_ error: Error) {
        if let api = error as? APIError, api.status == 401 {
            store.handle(error)
        } else {
            show(error.localizedDescription, isError: true)
        }
    }

    private func scheduleCheck() {
        checkTask?.cancel()
        let snapshot = store.draft
        checkTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            do {
                let result = try await store.check(snapshot)
                if !Task.isCancelled { check = result }
            } catch {
                if let api = error as? APIError, api.status == 401 { store.handle(error) }
            }
        }
    }

    private func save() async -> Bool {
        busy = true
        defer { busy = false }
        do {
            let post = try await store.save(store.draft)
            store.draft.id = post.id
            store.draft.status = post.status
            show(post.status == .scheduled ? "Changes saved." : "Draft saved.", isError: false)
            return true
        } catch {
            report(error)
            return false
        }
    }

    private func schedule() async {
        guard await save(), let id = store.draft.id else { return }
        busy = true
        defer { busy = false }
        do {
            let day = store.draft.when
            try await store.schedule(postID: id, at: day)
            store.draft = Draft()
            store.calendarFocus = day
            store.selectedTab = .calendar
            check = nil
            message = nil
        } catch {
            report(error)
        }
    }

    private func unschedule() async {
        guard let id = store.draft.id, let post = store.posts.first(where: { $0.id == id }) else { return }
        busy = true
        defer { busy = false }
        do {
            try await store.unschedule(post)
            store.draft.status = .draft
            show("Moved back to drafts.", isError: false)
        } catch {
            report(error)
        }
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        busy = true
        defer {
            busy = false
            pickerItems = []
        }
        for item in items {
            do {
                let media = try await store.upload(item, project: "", caption: "")
                store.draft.mediaIds.append(media.id)
            } catch {
                report(error)
            }
        }
    }
}

struct LibraryPicker: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    @Binding var selection: [Int]

    var body: some View {
        NavigationStack {
            ScrollView {
                if store.media.isEmpty {
                    ContentUnavailableView(
                        "No photos yet",
                        systemImage: "photo.on.rectangle",
                        description: Text("Upload job photos from the Photos tab.")
                    )
                } else {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 8)], spacing: 8) {
                        ForEach(store.media) { item in
                            Button {
                                if let index = selection.firstIndex(of: item.id) {
                                    selection.remove(at: index)
                                } else {
                                    selection.append(item.id)
                                }
                            } label: {
                                MediaThumb(item: item)
                                    .overlay(alignment: .topTrailing) {
                                        if selection.contains(item.id) {
                                            Image(systemName: "checkmark.circle.fill")
                                                .font(.title2)
                                                .foregroundStyle(.white, .tint)
                                                .padding(4)
                                        }
                                    }
                            }
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(selection.contains(item.id) ? .isSelected : [])
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle("Photo library")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
