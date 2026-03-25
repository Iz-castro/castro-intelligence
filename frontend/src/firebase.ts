import { initializeApp, type FirebaseApp } from "firebase/app";
import { browserLocalPersistence, getAuth, GoogleAuthProvider, setPersistence, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

import type { FirebaseWebConfig } from "./types";

export type FirebaseBundle = {
  app: FirebaseApp;
  auth: Auth;
  db: Firestore;
  provider: GoogleAuthProvider;
};

let bundle: FirebaseBundle | null = null;

export async function initializeFirebaseBundle(config: FirebaseWebConfig): Promise<FirebaseBundle> {
  if (bundle) {
    return bundle;
  }

  const app = initializeApp({
    apiKey: config.apiKey,
    authDomain: config.authDomain,
    projectId: config.projectId,
    storageBucket: config.storageBucket,
    appId: config.appId,
    messagingSenderId: config.messagingSenderId || undefined,
    measurementId: config.measurementId || undefined,
  });

  const auth = getAuth(app);
  await setPersistence(auth, browserLocalPersistence);
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });

  bundle = {
    app,
    auth,
    db: getFirestore(app),
    provider,
  };

  return bundle;
}
