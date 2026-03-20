# -*- coding: utf-8 -*-

from config import DATA_BACKEND

if DATA_BACKEND == "firestore":
    from database_firestore import *  # noqa: F401,F403
else:
    from database_sql import *  # noqa: F401,F403
