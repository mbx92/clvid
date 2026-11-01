from copy import deepcopy

import pytest

from app.media.gaming import GAMING_LAYOUT_VERSION, gaming_filter, panel_geometry, source_rectangle, validate_gaming
from app.media.process import MediaError


def crop():
    return {"mode": "gaming", "tracking": "static", "x": .5, "y": .5, "gaming": {
        "facecam": {"x": 0., "y": 0., "width": .25, "height": .5},
        "gameplay": {"x": .25, "y": 0., "width": .75, "height": 1.},
        "facecam_height": .28, "facecam_fit": "fill", "gameplay_fit": "fit"}}


@pytest.mark.parametrize("mutate", [
    lambda value: value.update(tracking="speaker"),
    lambda value: value.pop("gaming"),
    lambda value: value["gaming"].pop("facecam"),
    lambda value: value["gaming"]["gameplay"].update(width=.01),
    lambda value: value["gaming"]["gameplay"].update(x=.9),
    lambda value: value["gaming"]["facecam"].update(x=float("nan")),
    lambda value: value["gaming"]["facecam"].update(y=float("inf")),
    lambda value: value["gaming"]["facecam"].update(width=10**1000),
    lambda value: value["gaming"]["facecam"].update(height=True),
    lambda value: value["gaming"].update(facecam_height=.5),
    lambda value: value["gaming"].update(gameplay_fit="fit;movie=secret"),
])
def test_invalid_gaming_geometry_cannot_become_filter_syntax(mutate):
    value = crop()
    mutate(value)
    with pytest.raises(MediaError) as error:
        validate_gaming(value)
    assert error.value.code == "invalid_gaming_layout"


def test_overlap_is_allowed_and_defaults_preserve_whole_gameplay():
    value = crop()
    value["gaming"] = {"facecam": value["gaming"]["facecam"], "gameplay": {"x": 0, "y": 0, "width": 1, "height": 1}}
    result = validate_gaming(value)
    assert result["facecam_height"] == .28 and result["facecam_fit"] == "fill" and result["gameplay_fit"] == "fit"
    assert result["gameplay"] == {"x": 0, "y": 0, "width": 1, "height": 1}


def test_region_expands_outward_at_all_four_source_edges():
    assert source_rectangle({"x": .123, "y": .234, "width": .222, "height": .333}, 640, 360) == (78, 84, 143, 121)
    assert source_rectangle({"x": .98, "y": .98, "width": .02, "height": .02}, 640, 360) == (627, 352, 13, 8)
    assert source_rectangle({"x": 0, "y": 0, "width": 1, "height": 1}, 641, 361) == (0, 0, 641, 361)


@pytest.mark.parametrize("ratio,height,expected", [(.15, 1280, 192), (.28, 1280, 358), (.45, 1280, 576), (.28, 1920, 538)])
def test_composite_panels_and_subtitles_share_final_canvas(ratio, height, expected):
    value = crop()
    value["gaming"]["facecam_height"] = ratio
    original = deepcopy(value)
    graph, metadata = gaming_filter(value, {"width": 640, "height": 360, "display_width": 1280, "display_height": 360},
                                    height * 9 // 16, height, final_filters="ass=filename=captions.ass,fps=30,format=yuv420p")
    assert metadata["panel_heights"] == {"facecam": expected, "gameplay": height - expected}
    assert metadata["source_display_size"] == {"width": 1280, "height": 360}
    assert graph.startswith("[0:v:0]scale=1280:360,setsar=1")
    assert "vstack=inputs=2,ass=filename=captions.ass" in graph
    assert metadata["method"] == GAMING_LAYOUT_VERSION and metadata["mode"] == "static"
    assert "detected_frames" not in metadata and value == original


def test_fit_preserves_entire_region_and_even_padding():
    plan = panel_geometry(480, 360, 720, 922, "fit")
    assert (plan["scaled_width"], plan["scaled_height"], plan["x"], plan["y"]) == (720, 540, 0, 190)
    assert plan["source_crop"] is None


def test_thin_fill_region_is_cropped_before_scaling_to_bound_memory():
    plan = panel_geometry(44, 3840, 1080, 538, "fill")
    assert plan["source_crop"] == (0, 1909, 44, 22)
    assert plan["scaled_width"] == 1080 and plan["scaled_height"] == 538
    value = crop()
    value["gaming"]["facecam"] = {"x": 0, "y": 0, "width": .02, "height": 1}
    graph, _ = gaming_filter(value, {"width": 2160, "height": 3840}, 1080, 1920, final_filters="fps=30")
    assert "crop=44:3840:0:0:exact=1,crop=44:22:0:1909:exact=1,scale=1080:538" in graph
