from pathlib import Path
import hashlib
import io
import os
import re
import sys

import streamlit as st
from streamlit.components.v1 import html as components_html
from wordcloud import WordCloud
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np


# ----------------------------
# App resources / desktop heartbeat
# ----------------------------

def app_resource_path(relative_path: str) -> Path:
    """
    Gets the correct path whether running normally or from a PyInstaller bundle.
    """
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).resolve().parent

    return base_path / relative_path


def get_page_icon():
    icon_path = app_resource_path("assets/icon.ico")

    if icon_path.exists():
        try:
            return Image.open(icon_path)
        except Exception:
            return "☁️"

    return "☁️"


st.set_page_config(
    page_title="WordCloudGenerator",
    page_icon=get_page_icon(),
    layout="centered",
)


def install_desktop_heartbeat():
    """
    Lets launcher.py know that the browser tab is still open.
    When the tab closes, the heartbeat stops and launcher.py exits.
    """
    control_port = os.environ.get("WCG_CONTROL_PORT")

    if not control_port:
        return

    components_html(
        f"""
        <script>
        const heartbeatUrl = "http://127.0.0.1:{control_port}/heartbeat";
        const closingUrl = "http://127.0.0.1:{control_port}/closing";

        function sendHeartbeat() {{
            fetch(heartbeatUrl, {{
                method: "POST",
                mode: "no-cors",
                cache: "no-store",
                keepalive: true
            }}).catch(() => {{}});
        }}

        sendHeartbeat();
        setInterval(sendHeartbeat, 1000);

        function sendClosingSignal() {{
            try {{
                navigator.sendBeacon(closingUrl, "closing");
            }} catch (e) {{
                fetch(closingUrl, {{
                    method: "POST",
                    mode: "no-cors",
                    keepalive: true
                }}).catch(() => {{}});
            }}
        }}

        window.addEventListener("pagehide", sendClosingSignal);
        window.addEventListener("beforeunload", sendClosingSignal);
        </script>
        """,
        height=1,
        width=1,
    )


install_desktop_heartbeat()


# ----------------------------
# Fonts and color palettes
# ----------------------------

COMMON_FONT_PATHS = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\verdana.ttf",
    r"C:\Windows\Fonts\georgia.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

PALETTES = {
    "Soft Jewel": [
        "#355C7D",
        "#6A4C93",
        "#2A9D8F",
        "#577590",
        "#43AA8B",
        "#3D5A80",
        "#8E7DBE",
        "#BC6C25",
        "#1D7874",
        "#4D6CFA",
    ],
    "Cool Calm": [
        "#355070",
        "#4A6FA5",
        "#2C7DA0",
        "#468FAF",
        "#2A9D8F",
        "#5E548E",
        "#6D597A",
        "#4F772D",
    ],
    "Warm & Gentle": [
        "#6D597A",
        "#B56576",
        "#355070",
        "#2A9D8F",
        "#A98467",
        "#7F5539",
        "#577590",
        "#43AA8B",
    ],
    "Bright but Readable": [
        "#2B2D42",
        "#0077B6",
        "#0096C7",
        "#2A9D8F",
        "#6A4C93",
        "#E76F51",
        "#F77F00",
        "#588157",
    ],
}


# ----------------------------
# Word parsing and formatting
# ----------------------------

def parse_words(text):
    """
    Supports:
    kind
    leader
    funny,4
    supportive,2
    """
    freqs = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if "," in line:
            word, weight = line.rsplit(",", 1)
            word = word.strip()

            try:
                weight = float(weight.strip())
            except ValueError:
                weight = 1.0
        else:
            word = line
            weight = 1.0

        if word:
            freqs[word] = freqs.get(word, 0) + weight

    return freqs


def format_cloud_words(freqs, mode):
    """
    UPPERCASE is useful because it avoids dotted lowercase i letters.
    """
    formatted = {}

    for word, weight in freqs.items():
        if mode == "UPPERCASE":
            new_word = word.upper()
        elif mode == "Title Case":
            new_word = word.title()
        else:
            new_word = word.lower()

        formatted[new_word] = formatted.get(new_word, 0) + weight

    return formatted


def spread_equal_weights(freqs, jitter=0.035):
    """
    Slightly spreads words with identical weights so same-weight words
    do not look too identical in size.
    """
    groups = {}

    for word, weight in freqs.items():
        groups.setdefault(weight, []).append(word)

    adjusted = {}

    for weight, words in groups.items():
        words = sorted(words, key=lambda x: x.lower())
        n = len(words)

        if n == 1:
            adjusted[words[0]] = weight
            continue

        center = (n - 1) / 2

        for i, word in enumerate(words):
            factor = 1.0 + jitter * (center - i)
            adjusted[word] = max(0.1, weight * factor)

    return adjusted


# ----------------------------
# Font helpers
# ----------------------------

def resolve_font_path(user_font_path=""):
    if user_font_path and os.path.exists(user_font_path):
        return user_font_path

    for path in COMMON_FONT_PATHS:
        if os.path.exists(path):
            return path

    return None


def load_font(size, user_font_path=""):
    font_path = resolve_font_path(user_font_path)

    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = text.split()

    if not words:
        return ""

    lines = []
    current = words[0]

    for word in words[1:]:
        test = current + " " + word
        bbox = draw.textbbox((0, 0), test, font=font)
        test_width = bbox[2] - bbox[0]

        if test_width <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return "\n".join(lines)


# ----------------------------
# Mask helpers
# ----------------------------

def make_default_heart_mask(width, height):
    """
    Creates a simple black heart on a white background if no mask is uploaded.
    """
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    pts = []
    cx = width // 2
    cy = height // 2 + int(height * 0.04)
    scale = min(width, height) * 0.44

    for t in np.linspace(0, 2 * np.pi, 900):
        x = 16 * (np.sin(t) ** 3)
        y = -(
            13 * np.cos(t)
            - 5 * np.cos(2 * t)
            - 2 * np.cos(3 * t)
            - np.cos(4 * t)
        )

        px = cx + int(scale * x / 18)
        py = cy + int(scale * y / 18)

        pts.append((px, py))

    draw.polygon(pts, fill=0)

    return img


def make_mask_with_center_hole(
    mask_image,
    hole_shape="ellipse",
    hole_width_ratio=0.40,
    hole_height_ratio=0.20,
):
    """
    Input mask:
    - black shape on white background

    Returned WordCloud mask:
    - 0 means words can be placed there
    - 255 means blocked

    The center hole is blocked so words do not go behind the name/message.
    """
    img = mask_image.convert("L")
    arr = np.array(img)

    # Black area is allowed, white area is blocked.
    arr = np.where(arr > 200, 255, 0).astype(np.uint8)

    h, w = arr.shape
    cx, cy = w // 2, h // 2

    hw = int(w * hole_width_ratio / 2)
    hh = int(h * hole_height_ratio / 2)

    if hole_shape == "rectangle":
        y0 = max(0, cy - hh)
        y1 = min(h, cy + hh)
        x0 = max(0, cx - hw)
        x1 = min(w, cx + hw)

        arr[y0:y1, x0:x1] = 255
    else:
        yy, xx = np.ogrid[:h, :w]

        ellipse = (
            ((xx - cx) / max(hw, 1)) ** 2
            + ((yy - cy) / max(hh, 1)) ** 2
        ) <= 1

        arr[ellipse] = 255

    return arr


def draw_outer_mask_outline(
    image,
    original_mask_image,
    outline_width=3,
    color=(0, 0, 0, 255),
):
    """
    Draws only the outer outline of the original heart/mask.

    This avoids WordCloud's built-in contour, which also outlines the
    center hole.
    """
    if outline_width <= 0:
        return image.convert("RGB")

    img = image.convert("RGBA")

    mask_l = original_mask_image.convert("L").resize(img.size)
    arr = np.array(mask_l)

    allowed = arr < 200

    padded = np.pad(allowed, 1, constant_values=False)

    has_blocked_neighbor = (
        (~padded[1:-1, :-2])
        | (~padded[1:-1, 2:])
        | (~padded[:-2, 1:-1])
        | (~padded[2:, 1:-1])
    )

    border = allowed & has_blocked_neighbor

    border_alpha = Image.fromarray((border * 255).astype(np.uint8))

    kernel = max(1, int(outline_width))

    if kernel % 2 == 0:
        kernel += 1

    if kernel > 1:
        border_alpha = border_alpha.filter(ImageFilter.MaxFilter(kernel))

    outline = Image.new("RGBA", img.size, color)
    outline.putalpha(border_alpha)

    return Image.alpha_composite(img, outline).convert("RGB")


# ----------------------------
# Color helpers
# ----------------------------

def stable_index(text, mod):
    digest = hashlib.md5(text.lower().encode("utf-8")).hexdigest()
    return int(digest, 16) % mod


def hex_to_rgba(hex_color, alpha=255):
    hex_color = hex_color.strip().lstrip("#")

    if len(hex_color) != 6:
        return (0, 0, 0, alpha)

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    return (r, g, b, alpha)


def make_color_func(freqs, palette):
    """
    Forces the biggest words to use different colors so nearby large words
    do not visually merge.
    """
    if not palette:
        palette = ["#000000"]

    ordered_words = [
        w for w, _ in sorted(
            freqs.items(),
            key=lambda x: (-x[1], x[0].lower())
        )
    ]

    top_words = ordered_words[:min(len(palette), 10)]

    forced_colors = {}

    for i, word in enumerate(top_words):
        forced_colors[word.lower()] = palette[i % len(palette)]

    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        lw = word.lower()

        if lw in forced_colors:
            return forced_colors[lw]

        return palette[stable_index(lw, len(palette))]

    return color_func


def palette_preview_html(palette):
    blocks = []

    for color in palette:
        safe_color = color if re.match(r"^#[0-9a-fA-F]{6}$", color) else "#000000"

        blocks.append(
            f'<span style="'
            f'display:inline-block;'
            f'width:36px;'
            f'height:28px;'
            f'background:{safe_color};'
            f'border:1px solid #999;'
            f'border-radius:6px;'
            f'margin-right:8px;'
            f'margin-bottom:8px;'
            f'"></span>'
        )

    return (
        '<div style="'
        'display:flex;'
        'flex-wrap:wrap;'
        'gap:8px;'
        'margin-top:4px;'
        'margin-bottom:12px;'
        '">'
        + "".join(blocks)
        + "</div>"
    )


# ----------------------------
# Layout scoring
# ----------------------------

def score_cloud(wc, allowed_mask):
    """
    Scores a generated layout.

    Higher is better:
    - more fill inside the shape
    - more even distribution
    - fewer extreme empty zones
    """
    arr = wc.to_array()

    if arr.shape[-1] == 4:
        occupied = arr[..., 3] > 0
    else:
        occupied = np.any(arr < 245, axis=2)

    allowed = allowed_mask == 0

    if allowed.sum() == 0:
        return -1e9

    fill_ratio = occupied[allowed].mean()

    rows, cols = 7, 7
    h, w = allowed.shape
    cell_ratios = []

    for r in range(rows):
        for c in range(cols):
            y0 = r * h // rows
            y1 = (r + 1) * h // rows
            x0 = c * w // cols
            x1 = (c + 1) * w // cols

            sub_allowed = allowed[y0:y1, x0:x1]

            if sub_allowed.sum() < 100:
                continue

            sub_occ = occupied[y0:y1, x0:x1]
            cell_ratios.append(sub_occ[sub_allowed].mean())

    if not cell_ratios:
        return fill_ratio

    uniformity_penalty = float(np.std(cell_ratios))
    empty_cell_penalty = sum(1 for x in cell_ratios if x < 0.025) / len(cell_ratios)

    return fill_ratio - 0.45 * uniformity_penalty - 0.20 * empty_cell_penalty


def generate_best_wordcloud(
    freqs,
    mask,
    width,
    height,
    background_mode,
    max_words,
    font_path,
    color_func,
    n_tries=30,
    repeat_words=True,
    word_margin=16,
    max_font_ratio=0.13,
):
    best_wc = None
    best_score = -1e9

    for seed in range(n_tries):
        wc = WordCloud(
            width=width,
            height=height,
            background_color=None if background_mode == "transparent" else "white",
            mode="RGBA" if background_mode == "transparent" else "RGB",
            mask=mask,

            # Do not use WordCloud contour. It also outlines the center hole.
            contour_width=0,

            collocations=False,
            max_words=max_words,

            # No sideways words.
            prefer_horizontal=1.0,

            # Useful when there are not many unique words.
            repeat=repeat_words,

            # Smaller number means less extreme size differences.
            relative_scaling=0.20,

            # Keeps the largest words from becoming too huge.
            max_font_size=int(min(width, height) * max_font_ratio),
            min_font_size=max(9, width // 135),

            # More margin helps avoid i-dots looking like punctuation
            # beside nearby words.
            margin=word_margin,

            font_step=1,
            random_state=seed,
            font_path=font_path,
        )

        wc.generate_from_frequencies(freqs)
        wc.recolor(color_func=color_func, random_state=seed)

        score = score_cloud(wc, mask)

        if score > best_score:
            best_score = score
            best_wc = wc

    return best_wc


# ----------------------------
# Center text
# ----------------------------

def add_center_text(
    image,
    name,
    message,
    hole_width_ratio,
    hole_height_ratio,
    user_font_path="",
    draw_box=False,
    text_color="#000000",
    glow_color="#FFFFFF",
):
    """
    Adds the name/message in the center.

    draw_box=False removes the rectangular box, but the center hole still
    keeps words away from the text.
    """
    img = image.convert("RGBA")
    draw = ImageDraw.Draw(img)

    w, h = img.size
    cx, cy = w // 2, h // 2

    text_area_w = int(w * hole_width_ratio * 0.90)
    text_area_h = int(h * hole_height_ratio * 0.85)

    x0 = cx - text_area_w // 2
    y0 = cy - text_area_h // 2
    x1 = cx + text_area_w // 2
    y1 = cy + text_area_h // 2

    name_font = load_font(max(44, w // 22), user_font_path)
    msg_font = load_font(max(22, w // 50), user_font_path)

    if draw_box:
        draw.rounded_rectangle(
            [x0, y0, x1, y1],
            radius=max(16, w // 90),
            fill=(255, 255, 255, 245),
            outline=(170, 170, 170, 255),
            width=2,
        )

    max_text_width = int(text_area_w * 0.95)
    wrapped_message = wrap_text(draw, message, msg_font, max_text_width)

    name_bbox = draw.textbbox((0, 0), name, font=name_font)
    name_h = name_bbox[3] - name_bbox[1]

    msg_bbox = draw.multiline_textbbox(
        (0, 0),
        wrapped_message,
        font=msg_font,
        spacing=8,
        align="center",
    )
    msg_h = msg_bbox[3] - msg_bbox[1]

    gap = max(12, h // 85)
    total_h = name_h + gap + msg_h

    name_y = cy - total_h / 2 + name_h / 2
    msg_y = name_y + name_h / 2 + gap + msg_h / 2

    main_text_rgba = hex_to_rgba(text_color, 255)
    glow_rgba = hex_to_rgba(glow_color, 235)

    # Soft glow behind text so it stays readable without a box.
    shadow_offsets = [
        (-3, -3), (0, -3), (3, -3),
        (-3, 0),           (3, 0),
        (-3, 3),  (0, 3),  (3, 3),
    ]

    for dx, dy in shadow_offsets:
        draw.text(
            (cx + dx, name_y + dy),
            name,
            anchor="mm",
            fill=glow_rgba,
            font=name_font,
        )

        draw.multiline_text(
            (cx + dx, msg_y + dy),
            wrapped_message,
            anchor="mm",
            fill=glow_rgba,
            font=msg_font,
            align="center",
            spacing=8,
        )

    # Main text.
    draw.text(
        (cx, name_y),
        name,
        anchor="mm",
        fill=main_text_rgba,
        font=name_font,
    )

    draw.multiline_text(
        (cx, msg_y),
        wrapped_message,
        anchor="mm",
        fill=main_text_rgba,
        font=msg_font,
        align="center",
        spacing=8,
    )

    return img.convert("RGB")


def safe_filename(name):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or "wordcloud"


# ----------------------------
# Streamlit UI
# ----------------------------

st.title("WordCloudGenerator")

recipient_name = st.text_input("Recipient name", "Adam")
message = st.text_input("Short message", "On behalf of the club, thank you!")

words_text = st.text_area(
    "Words: one per line, or word,weight",
    value="""kind,5
caring,4.7
helpful,4.4
supportive,4.2
loving,4
thoughtful,3
compassionate,3
friendly,3
sweet,2.7
funny,2.4
creative,2.3
generous,2.2
responsive,2.1
honest,2
smart,1.8
cooperative,1.7
nice,1.5
fun-loving,1.5""",
    height=280,
)

uploaded_mask = st.file_uploader("Upload shape mask PNG/JPG", type=["png", "jpg", "jpeg"])

col1, col2 = st.columns(2)

with col1:
    width = st.number_input(
        "Output width",
        min_value=600,
        max_value=5000,
        value=1800,
        step=100,
    )

    background_mode = st.selectbox(
        "Background",
        ["white", "transparent"],
        index=0,
    )

    center_shape = st.selectbox(
        "Center empty area shape",
        ["ellipse", "rectangle"],
        index=0,
    )

with col2:
    height = st.number_input(
        "Output height",
        min_value=600,
        max_value=5000,
        value=1400,
        step=100,
    )

    outer_outline_width = st.slider(
        "Outer shape outline thickness",
        0,
        8,
        3,
    )

    max_words = st.slider(
        "Max words",
        20,
        800,
        240,
    )

    n_tries = st.slider(
        "Layout attempts",
        3,
        80,
        32,
    )

col3, col4 = st.columns(2)

with col3:
    hole_width_ratio = st.slider(
        "Center hole width (%)",
        20,
        70,
        40,
    ) / 100

    word_margin = st.slider(
        "Word spacing / margin",
        2,
        35,
        16,
    )

with col4:
    hole_height_ratio = st.slider(
        "Center hole height (%)",
        12,
        45,
        20,
    ) / 100

    max_font_ratio = st.slider(
        "Largest word size (%)",
        8,
        22,
        13,
    ) / 100

word_case = st.selectbox(
    "Cloud word style",
    ["lowercase", "Title Case", "UPPERCASE"],
    index=0,
)

repeat_words = st.checkbox(
    "Repeat words to fill empty space",
    value=True,
)

auto_spread = st.checkbox(
    "Auto-spread equal weights slightly",
    value=True,
)

draw_center_box = st.checkbox(
    "Show center box",
    value=False,
)

# ----------------------------
# Color UI
# ----------------------------

st.subheader("Colors")

palette_choice = st.selectbox(
    "Word color palette",
    list(PALETTES.keys()) + ["Custom palette"],
    index=0,
)

if palette_choice == "Custom palette":
    custom_count = st.slider(
        "Number of custom colors",
        min_value=2,
        max_value=12,
        value=5,
    )

    default_custom_colors = [
        "#355C7D",
        "#6A4C93",
        "#2A9D8F",
        "#BC6C25",
        "#577590",
        "#43AA8B",
        "#3D5A80",
        "#8E7DBE",
        "#1D7874",
        "#4D6CFA",
        "#B56576",
        "#A98467",
    ]

    palette = []

    picker_cols = st.columns(min(custom_count, 4))

    for i in range(custom_count):
        with picker_cols[i % len(picker_cols)]:
            palette.append(
                st.color_picker(
                    f"Color {i + 1}",
                    value=default_custom_colors[i % len(default_custom_colors)],
                    key=f"custom_palette_color_{i}",
                )
            )
else:
    palette = PALETTES[palette_choice]

st.markdown(palette_preview_html(palette), unsafe_allow_html=True)

color_col1, color_col2, color_col3 = st.columns(3)

with color_col1:
    center_text_color = st.color_picker(
        "Center text color",
        "#000000",
    )

with color_col2:
    center_glow_color = st.color_picker(
        "Center text glow",
        "#FFFFFF",
    )

with color_col3:
    outer_outline_color = st.color_picker(
        "Outer outline color",
        "#000000",
    )

font_path_input = st.text_input(
    "Optional font path",
    value="",
    help=r"Example on Windows: C:\Windows\Fonts\segoeui.ttf",
)

generate = st.button("Generate")

if generate:
    freqs = parse_words(words_text)

    if not freqs:
        st.error("Please enter at least one word.")
        st.stop()

    freqs = format_cloud_words(freqs, word_case)

    if auto_spread:
        freqs = spread_equal_weights(freqs, jitter=0.035)

    resolved_font_path = resolve_font_path(font_path_input)

    if uploaded_mask is not None:
        mask_img = Image.open(uploaded_mask).resize((width, height))
    else:
        mask_img = make_default_heart_mask(width, height)

    mask = make_mask_with_center_hole(
        mask_img,
        hole_shape=center_shape,
        hole_width_ratio=hole_width_ratio,
        hole_height_ratio=hole_height_ratio,
    )

    color_func = make_color_func(freqs, palette)

    wc = generate_best_wordcloud(
        freqs=freqs,
        mask=mask,
        width=width,
        height=height,
        background_mode=background_mode,
        max_words=max_words,
        font_path=resolved_font_path,
        color_func=color_func,
        n_tries=n_tries,
        repeat_words=repeat_words,
        word_margin=word_margin,
        max_font_ratio=max_font_ratio,
    )

    img = wc.to_image()

    final_img = add_center_text(
        img,
        recipient_name,
        message,
        hole_width_ratio=hole_width_ratio,
        hole_height_ratio=hole_height_ratio,
        user_font_path=resolved_font_path or font_path_input,
        draw_box=draw_center_box,
        text_color=center_text_color,
        glow_color=center_glow_color,
    )

    final_img = draw_outer_mask_outline(
        final_img,
        mask_img,
        outline_width=outer_outline_width,
        color=hex_to_rgba(outer_outline_color, 255),
    )

    st.image(
        final_img,
        caption="Generated word cloud",
        use_container_width=True,
    )

    buf = io.BytesIO()
    final_img.save(buf, format="PNG")

    st.download_button(
        "Download PNG",
        data=buf.getvalue(),
        file_name=f"{safe_filename(recipient_name)}_wordcloud.png",
        mime="image/png",
    )