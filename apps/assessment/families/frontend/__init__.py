"""frontend item families (one module per family group)."""
from .css import FAMILIES as _css
from .js_core import FAMILIES as _js_core
from .js_event_loop import FAMILY as _js_event_loop
from .react_web import FAMILIES as _react_web

FAMILIES = [_js_event_loop, *_js_core, *_css, *_react_web]
