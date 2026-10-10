"""backend item families (one module per family group)."""
from .data_systems import FAMILIES as _data_systems
from .python_core import FAMILIES as _python_core
from .sql_group_having import FAMILY as _sql_group_having
from .sql_more import FAMILIES as _sql_more
from .web_api import FAMILIES as _web_api

FAMILIES = [_sql_group_having, *_sql_more, *_python_core, *_web_api, *_data_systems]
