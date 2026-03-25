# -*- coding: utf-8 -*-

import firebase_admin
from firebase_admin import auth

from config import FIREBASE_STORAGE_BUCKET, FIRESTORE_PROJECT_ID


def get_firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        options = {}
        if FIRESTORE_PROJECT_ID:
            options["projectId"] = FIRESTORE_PROJECT_ID
        if FIREBASE_STORAGE_BUCKET:
            options["storageBucket"] = FIREBASE_STORAGE_BUCKET
        return firebase_admin.initialize_app(options=options or None)


def verify_firebase_id_token(id_token):
    app = get_firebase_app()
    return auth.verify_id_token(id_token, app=app, check_revoked=False)
