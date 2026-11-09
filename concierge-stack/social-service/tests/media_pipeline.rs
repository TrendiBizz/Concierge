use base64::Engine;
use concierge_social::{media, vault::Vault};
#[test]
fn normalize_media_and_enforce_download_ownership() {
    let dir = TestDir::new();
    std::env::set_var("SOCIAL_MEDIA_DIR", dir.path());
    std::env::set_var(
        "SOCIAL_PUBLIC_MEDIA_BASE",
        "https://media.example.com/download",
    );
    let fixtures = TestDir::new();
    for (name, args) in [
        ("image.png", vec!["-frames:v", "1"]),
        (
            "video.mp4",
            vec!["-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p"],
        ),
    ] {
        assert!(std::process::Command::new("ffmpeg")
            .args([
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=2048x1024:r=10"
            ])
            .args(args)
            .args(["-threads", "1", "-y"])
            .arg(fixtures.path().join(name))
            .status()
            .unwrap()
            .success());
    }
    let v = Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([9u8; 32]))
        .unwrap();
    for (name, kind) in [("image.png", "image"), ("video.mp4", "video")] {
        let bytes = std::fs::read(fixtures.path().join(name)).unwrap();
        let asset = media::save("tenant-a", &bytes).unwrap();
        assert_eq!(asset.kind, kind);
        assert!(asset.width <= 1920);
        assert_eq!(std::fs::metadata(&asset.path).unwrap().len(), asset.bytes);
        assert!(media::load("tenant-b", &asset.id).is_err());
        let url = media::provider_url(&v, "tenant-a", &asset.id).unwrap();
        let token = url.rsplit('/').next().unwrap();
        assert_eq!(media::download(&v, token).unwrap().id, asset.id);
        assert!(media::download(&v, &(token.to_string() + "x")).is_err());
        if kind == "image" {
            assert_eq!(asset.mime, "image/jpeg");
            assert_eq!(asset.width, 1080);
        } else {
            assert_eq!(asset.width, 1920);
            assert_eq!(media::poster("tenant-a", &asset.id).unwrap().kind, "image");
        }
    }
    assert!(media::save("tenant-a", b"invalid image").is_err());
}

struct TestDir(std::path::PathBuf);
impl TestDir {
    fn new() -> Self {
        let path =
            std::env::temp_dir().join(format!("social-media-test-{}", rand::random::<u128>()));
        std::fs::create_dir_all(&path).unwrap();
        Self(path)
    }
    fn path(&self) -> &std::path::Path {
        &self.0
    }
}
impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
