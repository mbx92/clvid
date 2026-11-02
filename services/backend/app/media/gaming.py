from copy import deepcopy
import math
from .process import MediaError

GAMING_LAYOUT_VERSION = "gaming-layout-1"


def finite(value, lower, upper):
    try:
        return type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper
    except OverflowError:
        return False


def validate_gaming(crop):
    try:
        assert crop.get("tracking", "static") == "static"
        value = deepcopy(crop["gaming"])
        for name in ("facecam", "gameplay"):
            rect = value[name]
            for key in ("x", "y", "width", "height"):
                assert finite(rect[key], .02 if key in ("width", "height") else 0, 1)
            assert rect["x"] + rect["width"] <= 1 + 1e-9 and rect["y"] + rect["height"] <= 1 + 1e-9
        value.setdefault("facecam_height", .28)
        assert finite(value["facecam_height"], .15, .45)
        for name, default in (("facecam_fit", "fill"), ("gameplay_fit", "fit")):
            value.setdefault(name, default)
            assert value[name] in ("fill", "fit")
        return value
    except (AssertionError, KeyError, TypeError):
        raise MediaError("invalid_gaming_layout", "Area atau susunan gaming tidak valid.") from None


def source_rectangle(region, width, height):
    x, y = math.floor(region["x"]*width), math.floor(region["y"]*height)
    right = min(width, math.ceil((region["x"]+region["width"])*width))
    bottom = min(height, math.ceil((region["y"]+region["height"])*height))
    return x, y, right-x, bottom-y


def panel_geometry(sw, sh, tw, th, fit):
    if fit == "fill":
        cw, ch = sw, sh
        if sw/sh > tw/th:
            cw = max(1, round(sh*tw/th))
        else:
            ch = max(1, round(sw*th/tw))
        return dict(source_crop=((sw-cw)//2, (sh-ch)//2, cw, ch), scaled_width=tw, scaled_height=th, x=0, y=0)
    factor = min(tw/sw, th/sh)
    w, h = max(2, int(sw*factor)//2*2), max(2, int(sh*factor)//2*2)
    return dict(source_crop=None, scaled_width=w, scaled_height=h, x=(tw-w)//4*2, y=(th-h)//4*2)


def gaming_filter(crop, meta, width, height, final_filters="fps=30,format=yuv420p"):
    gaming = validate_gaming(crop)
    sw, sh = meta.get("display_width", meta["width"]), meta.get("display_height", meta["height"])
    top = round(height*gaming["facecam_height"]/2)*2
    graph = f"[0:v:0]scale={sw}:{sh},setsar=1,split=2[face][game];"
    for name, label, h in (("facecam", "face", top), ("gameplay", "game", height-top)):
        x, y, w, rh = source_rectangle(gaming[name], sw, sh)
        plan = panel_geometry(w, rh, width, h, gaming[name+"_fit"])
        graph += f"[{label}]crop={w}:{rh}:{x}:{y}:exact=1,"
        if plan["source_crop"]:
            cx, cy, cw, ch = plan["source_crop"]
            graph += f"crop={cw}:{ch}:{cx}:{cy}:exact=1,"
        graph += f"scale={plan['scaled_width']}:{plan['scaled_height']},setsar=1"
        if gaming[name+"_fit"] == "fit":
            graph += f",pad={width}:{h}:{plan['x']}:{plan['y']}:color=0x181b1a"
        graph += f"[{label}out];"
    graph += f"[faceout][gameout]vstack=inputs=2,{final_filters}[v]"
    return graph, dict(mode="static", method=GAMING_LAYOUT_VERSION, layout="gaming", gaming=gaming,
                       panel_heights=dict(facecam=top, gameplay=height-top), source_display_size=dict(width=sw, height=sh))
