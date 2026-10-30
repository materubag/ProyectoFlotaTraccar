# -*- coding: utf-8 -*-
try:
    from . import models
    from . import controllers
except ImportError:
    # Standalone execution for pytest when running outside Odoo framework
    pass
