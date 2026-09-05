"""Design tokens for the Reflex web interface.

Actual color values live in ``assets/theme.css``. Components import only these
semantic CSS-variable references, keeping the palette centralized.
"""

PURPLE = "var(--purple)"
PURPLE_DARK = "var(--purple-dark)"
PURPLE_BG = "var(--purple-bg)"
PAGE = "var(--page)"
PANEL = "var(--panel)"
LINE = "var(--line)"
LINE_SOFT = "var(--line-soft)"
LINE_STRONG = "var(--line-strong)"
INK = "var(--ink)"
INK_2 = "var(--ink-2)"
INK_3 = "var(--ink-3)"
WHITE = "var(--white)"
ROW_HOVER = "var(--row-hover)"
TRANSPARENT = "transparent"

STATUS_GRAY_BG = "var(--status-gray-bg)"
STATUS_GRAY_TEXT = "var(--status-gray-text)"
STATUS_BLUE_BG = "var(--status-blue-bg)"
STATUS_BLUE_TEXT = "var(--status-blue-text)"
STATUS_AMBER_BG = "var(--status-amber-bg)"
STATUS_AMBER_TEXT = "var(--status-amber-text)"
STATUS_GREEN_BG = "var(--status-green-bg)"
STATUS_GREEN_TEXT = "var(--status-green-text)"
STATUS_RED_BG = "var(--status-red-bg)"
STATUS_RED_TEXT = "var(--status-red-text)"
OVERLAY = "var(--overlay)"

RADIUS_CONTROL = "var(--radius-control)"
RADIUS_CARD = "var(--radius-card)"
RADIUS_PILL = "var(--radius-pill)"

FONT_FAMILY = "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif"
FONT_SIZE_BODY = "13px"
FONT_SIZE_CAPTION = "11px"
FONT_SIZE_LABEL = "12px"
FONT_SIZE_CARD_TITLE = "14px"
FONT_SIZE_METRIC = "26px"
FONT_WEIGHT_REGULAR = "400"
FONT_WEIGHT_MEDIUM = "500"
FONT_WEIGHT_SEMIBOLD = "600"

STATUS_PAIRS = {
    "gray": (STATUS_GRAY_BG, STATUS_GRAY_TEXT),
    "blue": (STATUS_BLUE_BG, STATUS_BLUE_TEXT),
    "amber": (STATUS_AMBER_BG, STATUS_AMBER_TEXT),
    "green": (STATUS_GREEN_BG, STATUS_GREEN_TEXT),
    "red": (STATUS_RED_BG, STATUS_RED_TEXT),
}
