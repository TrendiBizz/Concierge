from app import media_studio


def test_still_params_are_clamped():
    params = media_studio.params_for("still", "A workshop at dawn", 99, "2k", "qwen")
    assert params == {"prompt": "A workshop at dawn", "count": 12, "preset": "2k", "image_model": "qwen"}


def test_clip_params_keep_prompt():
    assert media_studio.params_for("clip", "Timelapse of a build", 1, None, None) == {"prompt": "Timelapse of a build"}
