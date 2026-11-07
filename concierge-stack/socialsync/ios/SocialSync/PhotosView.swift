import PhotosUI
import SwiftUI

struct PhotosView: View {
    @Environment(AppStore.self) private var store
    @State private var projectFilter = ""
    @State private var newProject = ""
    @State private var newCaption = ""
    @State private var pickerItems: [PhotosPickerItem] = []
    @State private var uploading = false
    @State private var editing: MediaItem?

    private var projects: [String] {
        Array(Set(store.media.map(\.project).filter { !$0.isEmpty })).sorted()
    }

    private var shown: [MediaItem] {
        store.media.filter { projectFilter.isEmpty || $0.project == projectFilter }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    uploadCard

                    if !projects.isEmpty {
                        Picker("Project", selection: $projectFilter) {
                            Text("All projects").tag("")
                            ForEach(projects, id: \.self) { Text($0).tag($0) }
                        }
                        .pickerStyle(.menu)
                    }

                    if shown.isEmpty {
                        ContentUnavailableView(
                            "No photos yet",
                            systemImage: "photo.on.rectangle",
                            description: Text("Upload job photos once, then reuse them in any post.")
                        )
                    } else {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 10)], spacing: 10) {
                            ForEach(shown) { item in
                                Button { editing = item } label: {
                                    VStack(alignment: .leading, spacing: 4) {
                                        MediaThumb(item: item)
                                        Text(item.project.isEmpty ? "No project" : item.project)
                                            .font(.caption.bold())
                                            .lineLimit(1)
                                        if !item.caption.isEmpty {
                                            Text(item.caption)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                                .lineLimit(1)
                                        }
                                    }
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Photos")
            .refreshable { await store.refresh() }
            .onChange(of: pickerItems) { _, items in
                if !items.isEmpty { Task { await upload(items) } }
            }
            .sheet(item: $editing) { item in
                MediaDetailView(item: item)
            }
        }
    }

    private var uploadCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Add to the library").font(.headline)
            TextField("Project, e.g. Ponsonby recladding", text: $newProject)
                .textFieldStyle(.roundedBorder)
            TextField("Caption, e.g. Before", text: $newCaption)
                .textFieldStyle(.roundedBorder)
            PhotosPicker(
                selection: $pickerItems,
                maxSelectionCount: 20,
                matching: .any(of: [.images, .videos])
            ) {
                HStack {
                    Label("Upload photos or videos", systemImage: "square.and.arrow.up")
                    if uploading { ProgressView() }
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(uploading)
        }
        .padding()
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        uploading = true
        defer {
            uploading = false
            pickerItems = []
        }
        for item in items {
            do {
                _ = try await store.upload(
                    item,
                    project: newProject.trimmingCharacters(in: .whitespaces),
                    caption: newCaption.trimmingCharacters(in: .whitespaces)
                )
            } catch {
                store.handle(error)
            }
        }
    }
}

struct MediaDetailView: View {
    @Environment(AppStore.self) private var store
    @Environment(\.dismiss) private var dismiss
    let item: MediaItem
    @State private var project: String
    @State private var caption: String
    @State private var confirmDelete = false
    @State private var error: String?

    init(item: MediaItem) {
        self.item = item
        _project = State(initialValue: item.project)
        _caption = State(initialValue: item.caption)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    MediaThumb(item: item)
                        .listRowInsets(EdgeInsets())
                }
                Section("Details") {
                    TextField("Project", text: $project)
                    TextField("Caption", text: $caption)
                }
                if let error {
                    Section { Text(error).foregroundStyle(.red) }
                }
                Section {
                    Button("Delete photo", role: .destructive) { confirmDelete = true }
                }
            }
            .navigationTitle(item.filename)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { Task { await save() } }
                }
            }
            .confirmationDialog("Delete this photo?", isPresented: $confirmDelete, titleVisibility: .visible) {
                Button("Delete", role: .destructive) { Task { await remove() } }
                Button("Cancel", role: .cancel) {}
            }
        }
    }

    private func save() async {
        do {
            try await store.updateMedia(
                item,
                caption: caption.trimmingCharacters(in: .whitespaces),
                project: project.trimmingCharacters(in: .whitespaces)
            )
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func remove() async {
        do {
            try await store.deleteMedia(item)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
