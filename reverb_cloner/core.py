from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

API_BASE = "https://api.reverb.com/api"
DEFAULT_CONDITION_UUID = "df268ad1-c462-4ba6-b6db-e007e23922ea"


@dataclass
class APIResult:
    ok: bool
    status_code: int
    payload: Optional[Dict[str, Any]] = None
    text: str = ""


def extract_listing_id(url: str) -> Optional[str]:
    """Extract numeric listing id from Reverb listing URL."""
    if not url:
        return None

    markers = ["/item/", "reverb.com/item/"]
    for marker in markers:
        if marker in url:
            part = url.split(marker, 1)[1]
            listing_id = part.split("-", 1)[0].split("/", 1)[0].strip()
            return listing_id or None
    return None


def auth_headers(api_key: str, json_mode: bool = False) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept-Version": "3.0",
        "Accept": "application/json",
    }
    if json_mode:
        headers["Content-Type"] = "application/json"
    return headers


def call_json(method: str, url: str, headers: Dict[str, str], **kwargs: Any) -> APIResult:
    try:
        response = requests.request(method=method, url=url, headers=headers, timeout=30, **kwargs)
    except requests.RequestException as exc:
        return APIResult(ok=False, status_code=0, text=str(exc))

    payload = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    return APIResult(
        ok=200 <= response.status_code < 300,
        status_code=response.status_code,
        payload=payload,
        text=response.text,
    )


def get_listing(api_key: str, listing_id: str) -> APIResult:
    return call_json(
        "GET",
        f"{API_BASE}/listings/{listing_id}",
        auth_headers(api_key, json_mode=True),
    )


def extract_make_model(listing: Dict[str, Any]) -> Tuple[str, str]:
    def normalize(value: Any) -> str:
        if value is None:
            return "Unknown"
        if isinstance(value, dict):
            return str(value.get("name") or value.get("_id") or "Unknown")
        return str(value)

    return normalize(listing.get("make")), normalize(listing.get("model"))


def image_url_from_photo(photo: Dict[str, Any]) -> Optional[str]:
    links = photo.get("_links", {}) if isinstance(photo, dict) else {}
    for key in ("full", "download", "original", "small"):
        data = links.get(key)
        if isinstance(data, dict) and data.get("href"):
            return data["href"]

    if isinstance(photo, dict):
        for value in photo.values():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value

    return None


def download_images(listing: Dict[str, Any], image_dir: str = "images") -> List[str]:
    photos = listing.get("photos", [])
    if not photos:
        return []

    image_root = Path(image_dir)
    image_root.mkdir(exist_ok=True)

    for old_file in image_root.glob("*"):
        try:
            old_file.unlink()
        except OSError:
            pass

    local_paths: List[str] = []
    for index, photo in enumerate(photos):
        image_url = image_url_from_photo(photo)
        if not image_url:
            continue

        try:
            response = requests.get(image_url, timeout=30)
        except requests.RequestException:
            continue

        if response.status_code != 200:
            continue

        content_type = (response.headers.get("content-type") or "").lower()
        ext = ".png" if "png" in content_type else ".jpg"
        filename = image_root / f"img_{index}_{int(time.time())}{ext}"
        filename.write_bytes(response.content)
        local_paths.append(str(filename))

    return local_paths


def create_listing(
    api_key: str,
    original_listing: Dict[str, Any],
    shipping_profile_id: str,
    price_multiplier: float,
) -> APIResult:
    make_name, model_name = extract_make_model(original_listing)

    base_price = float(original_listing["price"]["amount"])
    new_price = round(base_price * price_multiplier, 2)

    condition = original_listing.get("condition")
    condition_uuid = (
        condition.get("uuid")
        if isinstance(condition, dict)
        else condition if isinstance(condition, str) else DEFAULT_CONDITION_UUID
    )

    payload: Dict[str, Any] = {
        "title": original_listing.get("title") or f"{make_name} {model_name}".strip(),
        "description": original_listing.get("description") or "Cloned listing.",
        "price": {
            "amount": new_price,
            "currency": original_listing["price"]["currency"],
        },
        "condition": {"uuid": condition_uuid},
        "make": make_name,
        "model": model_name,
        "finish": original_listing.get("finish", ""),
        "year": original_listing.get("year", ""),
        "shipping_profile_id": int(shipping_profile_id),
        "state": "draft",
    }

    categories = original_listing.get("categories", [])
    category_uuids = [c.get("uuid") for c in categories if isinstance(c, dict) and c.get("uuid")]
    if category_uuids:
        payload["category_uuids"] = category_uuids

    return call_json(
        "POST",
        f"{API_BASE}/listings",
        auth_headers(api_key, json_mode=True),
        json=payload,
    )


def parse_new_listing_id(create_result: APIResult) -> Optional[str]:
    payload = create_result.payload
    if not isinstance(payload, dict):
        return None

    listing = payload.get("listing") if isinstance(payload.get("listing"), dict) else payload
    listing_id = listing.get("id") if isinstance(listing, dict) else None
    return str(listing_id) if listing_id else None


def upload_candidates(listing: Dict[str, Any], listing_id: str) -> List[str]:
    links = listing.get("_links", {}) if isinstance(listing, dict) else {}
    urls: List[str] = []

    for key in ("photos", "images", "photo_upload", "image_upload"):
        link_data = links.get(key)
        if isinstance(link_data, dict) and link_data.get("href"):
            urls.append(link_data["href"])

    urls.extend(
        [
            f"{API_BASE}/listings/{listing_id}/images",
            f"{API_BASE}/listings/{listing_id}/photos",
            f"{API_BASE}/my/listings/{listing_id}/images",
            f"{API_BASE}/my/listings/{listing_id}/photos",
        ]
    )

    deduped: List[str] = []
    for url in urls:
        if url not in deduped:
            deduped.append(url)
    return deduped


def upload_images(
    api_key: str,
    listing_id: str,
    image_paths: Sequence[str],
) -> Tuple[int, List[str]]:
    listing_result = get_listing(api_key, listing_id)
    if not listing_result.ok or not isinstance(listing_result.payload, dict):
        return 0, [f"Listing not ready or unavailable: {listing_result.status_code} {listing_result.text[:200]}"]

    endpoints = upload_candidates(listing_result.payload, listing_id)
    logs: List[str] = []
    success_count = 0

    for image_path in image_paths:
        if not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
            logs.append(f"Skipped invalid image file: {image_path}")
            continue

        filename = os.path.basename(image_path)
        mime_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        uploaded = False

        for endpoint in endpoints:
            if uploaded:
                break

            for field_name in ("photo", "image", "file"):
                with open(image_path, "rb") as img_file:
                    files = {field_name: (filename, img_file, mime_type)}
                    try:
                        response = requests.post(
                            endpoint,
                            headers=auth_headers(api_key),
                            files=files,
                            timeout=45,
                        )
                    except requests.RequestException as exc:
                        logs.append(f"{endpoint} ({field_name}) network error: {exc}")
                        continue

                if response.status_code in (200, 201, 202, 204):
                    success_count += 1
                    logs.append(f"Uploaded {filename} via {endpoint} ({field_name})")
                    uploaded = True
                    break

                if response.status_code not in (404, 405):
                    logs.append(
                        f"{endpoint} ({field_name}) -> {response.status_code}: {response.text[:180]}"
                    )

        if not uploaded:
            logs.append(f"Failed to upload {filename} with all endpoint/field combos")

        time.sleep(1.0)

    return success_count, logs


def publish_listing(api_key: str, listing_id: str) -> APIResult:
    listing_result = get_listing(api_key, listing_id)
    if not listing_result.ok or not isinstance(listing_result.payload, dict):
        return APIResult(ok=False, status_code=listing_result.status_code, text=listing_result.text)

    links = listing_result.payload.get("_links", {})
    publish_link = links.get("publish", {}).get("href") if isinstance(links, dict) else None

    candidates = []
    if publish_link:
        candidates.extend([
            ("PUT", publish_link, None),
            ("POST", publish_link, None),
        ])

    candidates.extend(
        [
            ("PUT", f"{API_BASE}/listings/{listing_id}/publish", None),
            ("POST", f"{API_BASE}/listings/{listing_id}/publish", None),
            ("PATCH", f"{API_BASE}/listings/{listing_id}", {"state": "live"}),
            ("PUT", f"{API_BASE}/listings/{listing_id}", {"state": "live"}),
        ]
    )

    for method, url, payload in candidates:
        result = call_json(
            method,
            url,
            auth_headers(api_key, json_mode=payload is not None),
            json=payload,
        )
        if result.ok:
            return result

    return APIResult(ok=False, status_code=400, text="All publish attempts failed.")


def wait_until_listing_ready(api_key: str, listing_id: str, attempts: int = 8, delay_s: float = 3.0) -> bool:
    for _ in range(attempts):
        result = get_listing(api_key, listing_id)
        if result.ok:
            return True
        time.sleep(delay_s)
    return False


def cleanup_images(image_paths: Sequence[str], keep_images: bool = False) -> None:
    if keep_images:
        return

    for image_path in image_paths:
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except OSError:
            pass
