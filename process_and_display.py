#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import sys
import time
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

import cv2
import numpy as np
import requests
from PIL import Image, ImageOps

import firebase_admin
from firebase_admin import credentials, firestore, storage
import face_recognition


# =========================
# CONFIG
# =========================
SERVICE_KEY = "serviceAccountKey.json"
FIRESTORE_COLLECTION = "images"
KNOWN_FACES_DIR = Path("./known_faces")
TOLERANCE = 0.55
POLL_INTERVAL = 5
MAX_RETRIES = 3
STORAGE_BUCKET = "project-9a95e.firebasestorage.app"

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


# =========================
# DATA STRUCTURES
# =========================
@dataclass
class KnownFacesDB:
    encodings: List[np.ndarray]
    names: List[str]


# =========================
# IMAGE HELPERS
# =========================
def load_image_and_fix_orientation(path: Path | str) -> Image.Image:
    img = Image.open(path)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def pil_to_rgb_array(pil_img: Image.Image) -> np.ndarray:
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    return np.array(pil_img)


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_IMAGE_EXTS


# =========================
# FIREBASE INIT
# =========================
def init_firebase() -> tuple[firestore.Client, storage.Bucket]:
    if not os.path.exists(SERVICE_KEY):
        raise SystemExit(
            f"Erreur : fichier de clé de service introuvable : {SERVICE_KEY}\n"
            "Place serviceAccountKey.json dans le dossier du script."
        )

    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_KEY)
        firebase_admin.initialize_app(cred, {"storageBucket": STORAGE_BUCKET})

    db = firestore.client()
    bucket = storage.bucket()
    print("✅ Firebase initialisé. Bucket :", bucket.name)
    return db, bucket


# =========================
# KNOWN FACES LOADING
# =========================
def build_known_faces_db(known_dir: Path) -> KnownFacesDB:
    print("Chargement des visages connus depuis", known_dir)
    encs: List[np.ndarray] = []
    names: List[str] = []

    if not known_dir.exists():
        print("⚠️ Dossier known_faces absent. Crée-le et ajoute des images.")
        return KnownFacesDB(encodings=encs, names=names)

    for entry in sorted(known_dir.iterdir()):
        if entry.is_dir():
            person_name = entry.name
            for imgf in sorted(entry.iterdir()):
                if not imgf.is_file():
                    continue
                if not is_image_file(imgf):
                    print(f"⚠️ Fichier ignoré (non-image) : {imgf}")
                    continue

                try:
                    pil = load_image_and_fix_orientation(imgf)
                    rgb = pil_to_rgb_array(pil)
                    face_encs = face_recognition.face_encodings(rgb)

                    if not face_encs:
                        print(f"⚠️ Aucun visage détecté dans {imgf.name}, ignoré.")
                        continue

                    encs.append(face_encs[0])
                    names.append(person_name)
                    print(f"Known: {imgf.name} -> {person_name} encodé")
                except Exception as e:
                    print("Erreur chargement", imgf, e)

        elif entry.is_file():
            if not is_image_file(entry):
                print(f"⚠️ Fichier ignoré (non-image) : {entry}")
                continue

            person_name = entry.stem
            try:
                pil = load_image_and_fix_orientation(entry)
                rgb = pil_to_rgb_array(pil)
                face_encs = face_recognition.face_encodings(rgb)

                if not face_encs:
                    print(f"⚠️ Aucun visage détecté dans {entry.name}, ignoré.")
                    continue

                encs.append(face_encs[0])
                names.append(person_name)
                print(f"Known: {entry.name} -> {person_name} encodé")
            except Exception as e:
                print("Erreur chargement", entry, e)

    uniq = sorted(set(names))
    print(f"Total visages connus : {len(uniq)} -> {uniq}")
    return KnownFacesDB(encodings=encs, names=names)


# =========================
# STORAGE PATH INFERENCE
# =========================
def candidate_paths_from_url(download_url: str) -> List[str]:
    if not download_url:
        return []

    cands: List[str] = []
    try:
        if "/o/" in download_url:
            tail = download_url.split("/o/", 1)[1].split("?", 1)[0]
            path = unquote(tail)
            cands.append(path)
            cands.append(path.lstrip("/"))

        if "%2F" in download_url and "raw_images" in download_url:
            part = download_url.split("raw_images%2F", 1)[1].split("?", 1)[0]
            maybe = "raw_images/" + unquote(part)
            cands.append(maybe)

        new: List[str] = []
        for p in cands:
            new.append(p)
            if not p.startswith("raw_images/"):
                new.append("raw_images/" + p)
            if p.startswith("/"):
                new.append(p.lstrip("/"))

        seen = set()
        out: List[str] = []
        for x in new:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out
    except Exception:
        return []


def find_storage_path_from_url(bucket: storage.Bucket, download_url: str) -> Optional[str]:
    candidates = candidate_paths_from_url(download_url)

    for c in candidates:
        blob = bucket.blob(c)
        if blob.exists():
            return c

    for c in candidates:
        name = Path(c).name
        alt = f"raw_images/{name}"
        if bucket.blob(alt).exists():
            return alt

    return None


# =========================
# DOWNLOAD HELPERS
# =========================
def download_blob_to_file(bucket: storage.Bucket, blob_path: str) -> str:
    blob = bucket.blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError(f"Blob introuvable dans Storage: {blob_path}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(blob_path).suffix or ".jpg")
    tmp.close()
    blob.download_to_filename(tmp.name)
    return tmp.name


def download_via_http_and_upload(bucket: storage.Bucket, download_url: str, target_path: str) -> str:
    r = requests.get(download_url, stream=True, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP GET a renvoyé {r.status_code}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(target_path).suffix or ".jpg")
    tmp.close()

    with open(tmp.name, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    blob = bucket.blob(target_path)
    blob.upload_from_filename(tmp.name)
    return tmp.name


# =========================
# FACE RECOGNITION + DISPLAY
# =========================
def distance_to_confidence(distance: float) -> float:
    confidence = (1.0 - distance) * 100.0
    return round(max(0.0, min(confidence, 100.0)), 2)


def recognize_and_display(
    local_path: str,
    known_db: KnownFacesDB,
    show_window: bool = True,
) -> List[Dict[str, object]]:
    pil = load_image_and_fix_orientation(local_path)
    img_rgb = pil_to_rgb_array(pil)
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    small_rgb = cv2.resize(img_rgb, (0, 0), fx=0.25, fy=0.25)

    face_locations = face_recognition.face_locations(small_rgb)
    face_encodings = face_recognition.face_encodings(small_rgb, face_locations)

    results: List[Dict[str, object]] = []

    for enc in face_encodings:
        if not known_db.encodings:
            results.append({
                "name": "inconnue",
                "confidence": 0.0,
                "best_distance": None,
            })
            continue

        matches = face_recognition.compare_faces(
            known_db.encodings,
            enc,
            tolerance=TOLERANCE
        )
        distances = face_recognition.face_distance(known_db.encodings, enc)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        confidence = distance_to_confidence(best_distance)

        print("Distances:", [round(float(x), 4) for x in distances])
        print("Best match probable:", known_db.names[best_idx], "| distance:", round(best_distance, 4))

        if matches[best_idx]:
            results.append({
                "name": known_db.names[best_idx],
                "confidence": confidence,
                "best_distance": round(best_distance, 4),
            })
        else:
            results.append({
                "name": "inconnue",
                "confidence": confidence,
                "best_distance": round(best_distance, 4),
            })

    img_display = img_bgr.copy()
    if small_rgb.shape[1] == 0 or small_rgb.shape[0] == 0:
        h_scale = v_scale = 4.0
    else:
        h_scale = img_bgr.shape[1] / small_rgb.shape[1]
        v_scale = img_bgr.shape[0] / small_rgb.shape[0]

    for i, (top, right, bottom, left) in enumerate(face_locations):
        y1 = int(top * v_scale)
        x2 = int(right * h_scale)
        y2 = int(bottom * v_scale)
        x1 = int(left * h_scale)

        cv2.rectangle(img_display, (x1, y1), (x2, y2), (0, 255, 0), 2)

        if i < len(results):
            label = f'{results[i]["name"]} ({results[i]["confidence"]}%)'
        else:
            label = "inconnue"

        cv2.rectangle(img_display, (x1, max(y2 - 30, 0)), (x2, y2), (0, 255, 0), cv2.FILLED)
        cv2.putText(
            img_display,
            label,
            (x1 + 6, max(y2 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            2,
        )

    if len(face_locations) == 0:
        cv2.putText(
            img_display,
            "Aucun visage detecte",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
        )

    if show_window:
        winname = "Detection - appuie une touche pour fermer"
        try:
            cv2.namedWindow(winname, cv2.WINDOW_NORMAL)

            screen_w, screen_h = 1200, 800
            img_h, img_w = img_display.shape[:2]
            scale = min(screen_w / img_w, screen_h / img_h, 1.0)
            display_w = int(img_w * scale)
            display_h = int(img_h * scale)

            cv2.resizeWindow(winname, display_w, display_h)
            cv2.imshow(winname, img_display)
            cv2.waitKey(0)

            try:
                cv2.destroyWindow(winname)
            except Exception:
                try:
                    cv2.destroyAllWindows()
                except Exception:
                    pass
        except Exception as e:
            print("Erreur affichage OpenCV (ignore) :", e)

    return results


# =========================
# PROCESS ONE DOC
# =========================
def process_doc_by_ref(
    db: firestore.Client,
    bucket: storage.Bucket,
    known_db: KnownFacesDB,
    doc_ref: firestore.DocumentReference,
    show_window: bool = False,
) -> None:
    doc = doc_ref.get()
    if not doc.exists:
        print("Document introuvable:", doc_ref.id)
        return

    data = doc.to_dict() or {}
    print("Traitement d'un document unique:", doc_ref.id)

    try:
        storage_path: Optional[str] = data.get("storagePath")
        download_url: Optional[str] = data.get("url") or data.get("downloadURL")

        if not storage_path and download_url:
            sp = find_storage_path_from_url(bucket, download_url)
            if sp:
                print(" -> inférer storagePath depuis URL:", sp)
                storage_path = sp
                try:
                    doc_ref.update({"storagePath": storage_path})
                except Exception:
                    pass

        local_path: Optional[str] = None

        if storage_path:
            try:
                local_path = download_blob_to_file(bucket, storage_path)
                print(" -> téléchargé depuis Storage:", storage_path)
            except FileNotFoundError:
                print(" -> Blob introuvable dans Storage:", storage_path)

        if local_path is None and download_url:
            target_path = storage_path or find_storage_path_from_url(bucket, download_url) or f"raw_images/{doc_ref.id}.jpg"
            local_path = download_via_http_and_upload(bucket, download_url, target_path)
            doc_ref.update({"storagePath": target_path})
            print(" -> téléchargé via HTTP puis upload Storage:", target_path)

        if not local_path:
            raise RuntimeError("Aucun fichier local à traiter (ni storagePath ni downloadURL valides).")

        recognized = recognize_and_display(local_path, known_db, show_window=show_window)

        doc_ref.update(
            {
                "recognized": recognized,
                "processed": True,
                "processedAt": firestore.SERVER_TIMESTAMP,
                "status": "processed",
                "error": firestore.DELETE_FIELD,
            }
        )
        print(f"OK -> mis à jour {doc_ref.id} : {recognized}")

        try:
            os.remove(local_path)
        except Exception:
            pass

    except Exception as e:
        print("Erreur lors du traitement :", e)
        traceback.print_exc()

        try:
            new_retry = int(data.get("retry_count", 0)) + 1
            updates = {
                "error": str(e),
                "retry_count": new_retry,
                "status": "error",
            }

            if new_retry >= MAX_RETRIES:
                updates["processed"] = True
                updates["processedAt"] = firestore.SERVER_TIMESTAMP
                updates["note"] = f"Auto-stopped after {new_retry} retries"

            doc_ref.update(updates)
            print(f"Écrit erreur dans doc (retry_count={new_retry}).")
        except Exception as e2:
            print("Impossible de mettre à jour le doc avec l'erreur:", e2)


# =========================
# POLL LOOP
# =========================
def poll_loop(db: firestore.Client, bucket: storage.Bucket, known_db: KnownFacesDB) -> None:
    print(f"Démarrage du poller (scan toutes les {POLL_INTERVAL} s).")

    while True:
        try:
            docs = db.collection(FIRESTORE_COLLECTION).limit(50).get()

            docs_to_process = []
            for d in docs:
                data = d.to_dict() or {}

                already_processed = data.get("processed", False) is True
                has_input = bool(data.get("url") or data.get("downloadURL") or data.get("storagePath"))

                if (not already_processed) and has_input:
                    docs_to_process.append(d)

            if docs_to_process:
                print(f"{len(docs_to_process)} document(s) à traiter.")
                for d in docs_to_process:
                    process_doc_by_ref(
                        db,
                        bucket,
                        known_db,
                        d.reference,
                        show_window=False
                    )

        except Exception as e:
            print("Erreur pendant poll:", e)
            traceback.print_exc()

        time.sleep(POLL_INTERVAL)


# =========================
# MAIN
# =========================
def main() -> None:
    db, bucket = init_firebase()
    known_db = build_known_faces_db(KNOWN_FACES_DIR)

    if len(sys.argv) >= 2:
        doc_id = sys.argv[1]
        doc_ref = db.collection(FIRESTORE_COLLECTION).document(doc_id)
        process_doc_by_ref(db, bucket, known_db, doc_ref, show_window=True)
    else:
        poll_loop(db, bucket, known_db)


if __name__ == "__main__":
    main()