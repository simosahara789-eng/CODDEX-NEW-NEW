diff --git a/app.py b/app.py
new file mode 100644
index 0000000000000000000000000000000000000000..b02ec08f8d812583928d644c3a72ea835fb6984d
--- /dev/null
+++ b/app.py
@@ -0,0 +1,478 @@
+import os
+import time
+from pathlib import Path
+from typing import Any, Dict, List, Optional, Tuple
+
+import requests
+import streamlit as st
+
+# Page configuration
+st.set_page_config(page_title="Reverb Cloner PRO", page_icon="🎸", layout="centered")
+st.title("🎸 Reverb Cloner PRO MAX - FINAL VERSION")
+st.markdown("---")
+
+API_BASE = "https://api.reverb.com/api"
+
+
+def extract_listing_id(url: str) -> Optional[str]:
+    """Extract listing ID from Reverb URL."""
+    try:
+        if "/item/" in url:
+            part = url.split("/item/")[1]
+            return part.split("-")[0]
+        if "reverb.com/item/" in url:
+            part = url.split("reverb.com/item/")[1]
+            return part.split("-")[0]
+        return None
+    except Exception as exc:  # noqa: BLE001
+        st.error(f"Error parsing URL: {exc}")
+        return None
+
+
+def _auth_headers(api_key: str, json_mode: bool = False) -> Dict[str, str]:
+    headers = {
+        "Authorization": f"Bearer {api_key}",
+        "Accept-Version": "3.0",
+        "Accept": "application/json",
+    }
+    if json_mode:
+        headers["Content-Type"] = "application/json"
+    return headers
+
+
+def get_listing(api_key: str, listing_id: str) -> Optional[Dict[str, Any]]:
+    """Fetch listing data."""
+    try:
+        response = requests.get(
+            f"{API_BASE}/listings/{listing_id}",
+            headers=_auth_headers(api_key, json_mode=True),
+            timeout=20,
+        )
+        if response.status_code != 200:
+            st.error(f"Error fetching listing: {response.status_code} - {response.text}")
+            return None
+        return response.json()
+    except Exception as exc:  # noqa: BLE001
+        st.error(f"Connection error: {exc}")
+        return None
+
+
+def extract_make_model(listing: Dict[str, Any]) -> Tuple[str, str]:
+    """Extract make and model from listing."""
+    make = listing.get("make")
+    model = listing.get("model")
+
+    def norm(value: Any) -> str:
+        if value is None:
+            return "Unknown"
+        if isinstance(value, dict):
+            return str(value.get("name") or value.get("_id") or "Unknown")
+        if isinstance(value, (str, int, float)):
+            return str(value)
+        return "Unknown"
+
+    return norm(make), norm(model)
+
+
+def download_images(listing: Dict[str, Any]) -> List[str]:
+    """Download images from original listing."""
+    photos = listing.get("photos", [])
+    paths: List[str] = []
+
+    if not photos:
+        st.warning("No images found in this listing")
+        return []
+
+    Path("images").mkdir(exist_ok=True)
+    for old_file in Path("images").glob("*"):
+        try:
+            old_file.unlink()
+        except OSError:
+            pass
+
+    progress_bar = st.progress(0)
+    status_text = st.empty()
+
+    for i, photo in enumerate(photos):
+        status_text.text(f"Downloading image {i+1} of {len(photos)}")
+        image_url = None
+
+        try:
+            links = photo.get("_links", {}) if isinstance(photo, dict) else {}
+            for key in ("full", "download", "original", "small"):
+                if key in links and isinstance(links[key], dict):
+                    image_url = links[key].get("href")
+                    if image_url:
+                        break
+
+            if not image_url and isinstance(photo, dict):
+                for value in photo.values():
+                    if isinstance(value, str) and value.startswith(("http://", "https://")):
+                        image_url = value
+                        break
+
+            if not image_url:
+                st.warning(f"Could not find image URL for image {i+1}")
+                continue
+
+            img_response = requests.get(image_url, timeout=20)
+            if img_response.status_code == 200:
+                ext = ".jpg"
+                content_type = (img_response.headers.get("content-type") or "").lower()
+                if "png" in content_type:
+                    ext = ".png"
+                file_path = f"images/img_{i}_{int(time.time())}{ext}"
+                with open(file_path, "wb") as handle:
+                    handle.write(img_response.content)
+                paths.append(file_path)
+            else:
+                st.warning(f"Failed to download image {i+1}: HTTP {img_response.status_code}")
+        except Exception as exc:  # noqa: BLE001
+            st.warning(f"Error downloading image {i+1}: {exc}")
+
+        progress_bar.progress((i + 1) / len(photos))
+
+    status_text.text("All images downloaded!")
+    progress_bar.empty()
+    return paths
+
+
+def create_listing(
+    api_key: str,
+    original_listing: Dict[str, Any],
+    shipping_profile_id: str,
+    price_multiplier: float,
+) -> Optional[str]:
+    """Create new listing based on original listing."""
+    make_name, model_name = extract_make_model(original_listing)
+
+    original_price = float(original_listing["price"]["amount"])
+    new_price = round(original_price * price_multiplier, 2)
+
+    condition = original_listing.get("condition")
+    condition_uuid = (
+        condition.get("uuid")
+        if isinstance(condition, dict)
+        else condition if isinstance(condition, str) else None
+    )
+    if not condition_uuid:
+        condition_uuid = "df268ad1-c462-4ba6-b6db-e007e23922ea"
+
+    title = original_listing.get("title") or f"{make_name} {model_name}".strip()
+    description = original_listing.get("description") or f"Original listing: {title}"
+
+    payload: Dict[str, Any] = {
+        "title": title,
+        "description": description,
+        "price": {
+            "amount": new_price,
+            "currency": original_listing["price"]["currency"],
+        },
+        "condition": {"uuid": condition_uuid},
+        "make": make_name,
+        "model": model_name,
+        "finish": original_listing.get("finish", ""),
+        "year": original_listing.get("year", ""),
+        "shipping_profile_id": int(shipping_profile_id),
+        "state": "draft",
+    }
+
+    categories = original_listing.get("categories", [])
+    category_uuids = [c.get("uuid") for c in categories if isinstance(c, dict) and c.get("uuid")]
+    if category_uuids:
+        payload["category_uuids"] = category_uuids
+
+    response = requests.post(
+        f"{API_BASE}/listings",
+        headers=_auth_headers(api_key, json_mode=True),
+        json=payload,
+        timeout=30,
+    )
+
+    if response.status_code not in (200, 201):
+        st.error(f"Error creating listing: {response.status_code}")
+        st.error(response.text)
+        return None
+
+    data = response.json()
+    if isinstance(data, dict):
+        listing_data = data.get("listing") if isinstance(data.get("listing"), dict) else data
+        return str(listing_data.get("id")) if listing_data.get("id") else None
+    return None
+
+
+def _candidate_upload_endpoints(listing: Dict[str, Any], listing_id: str) -> List[str]:
+    links = listing.get("_links", {}) if isinstance(listing, dict) else {}
+    candidates: List[str] = []
+
+    for key in ("photos", "images", "photo_upload", "image_upload"):
+        link_data = links.get(key)
+        if isinstance(link_data, dict) and link_data.get("href"):
+            candidates.append(link_data["href"])
+
+    # Fallback candidates for old/new API variations.
+    candidates.extend(
+        [
+            f"{API_BASE}/listings/{listing_id}/images",
+            f"{API_BASE}/listings/{listing_id}/photos",
+            f"{API_BASE}/my/listings/{listing_id}/images",
+            f"{API_BASE}/my/listings/{listing_id}/photos",
+        ]
+    )
+
+    deduped: List[str] = []
+    for url in candidates:
+        if url not in deduped:
+            deduped.append(url)
+    return deduped
+
+
+def upload_images(api_key: str, listing_id: str, image_paths: List[str]) -> bool:
+    """Upload images to listing, using HATEOAS links first then fallback endpoints."""
+    if not image_paths:
+        st.warning("No images to upload")
+        return False
+
+    listing = get_listing(api_key, str(listing_id))
+    if not listing:
+        st.error("❌ Cannot access the listing. It may not be ready yet.")
+        return False
+
+    endpoints = _candidate_upload_endpoints(listing, str(listing_id))
+    st.write(f"Found {len(endpoints)} candidate upload endpoints")
+
+    progress_bar = st.progress(0)
+    status_text = st.empty()
+    successful_uploads = 0
+
+    for i, image_path in enumerate(image_paths):
+        status_text.text(f"Uploading image {i+1} of {len(image_paths)}")
+        if not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
+            st.warning(f"Invalid image file: {image_path}")
+            progress_bar.progress((i + 1) / len(image_paths))
+            continue
+
+        if i > 0:
+            time.sleep(1.5)
+
+        uploaded = False
+        filename = os.path.basename(image_path)
+        mime_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
+
+        for endpoint in endpoints:
+            if uploaded:
+                break
+
+            for field_name in ("photo", "image", "file"):
+                with open(image_path, "rb") as img_file:
+                    files = {field_name: (filename, img_file, mime_type)}
+                    try:
+                        response = requests.post(
+                            endpoint,
+                            headers=_auth_headers(api_key),
+                            files=files,
+                            timeout=45,
+                        )
+                    except requests.RequestException:
+                        continue
+
+                if response.status_code in (200, 201, 202, 204):
+                    st.write(f"✅ Uploaded image {i+1} via {endpoint} ({field_name})")
+                    successful_uploads += 1
+                    uploaded = True
+                    break
+
+                if response.status_code not in (404, 405):
+                    st.caption(
+                        f"{endpoint} ({field_name}) -> {response.status_code}: "
+                        f"{response.text[:180]}"
+                    )
+
+            if uploaded:
+                break
+
+        if not uploaded:
+            st.error(f"❌ Failed to upload image {i+1} after trying all endpoints.")
+
+        progress_bar.progress((i + 1) / len(image_paths))
+
+    status_text.text(f"Upload complete! {successful_uploads}/{len(image_paths)} images uploaded")
+    progress_bar.empty()
+
+    if successful_uploads == 0:
+        st.warning("⚠️ Could not upload images via API.")
+        st.info("📌 Manual upload path:")
+        st.markdown("1. Open your draft listing edit page")
+        st.markdown(f"2. Upload from local folder: `images/`")
+        st.markdown(f"3. Link: https://reverb.com/item/{listing_id}/edit")
+
+    return successful_uploads > 0
+
+
+def publish_listing(api_key: str, listing_id: str) -> bool:
+    """Publish listing using dynamic publish link first, then fallbacks."""
+    listing = get_listing(api_key, str(listing_id))
+    if not listing:
+        st.warning("Could not refresh listing before publish.")
+        return False
+
+    links = listing.get("_links", {}) if isinstance(listing, dict) else {}
+    publish_url = None
+    if isinstance(links.get("publish"), dict):
+        publish_url = links["publish"].get("href")
+
+    candidates: List[Tuple[str, str, Optional[Dict[str, Any]]]] = []
+    if publish_url:
+        candidates.append(("put", publish_url, None))
+        candidates.append(("post", publish_url, None))
+
+    candidates.extend(
+        [
+            ("put", f"{API_BASE}/listings/{listing_id}/publish", None),
+            ("post", f"{API_BASE}/listings/{listing_id}/publish", None),
+            ("put", f"{API_BASE}/listings/{listing_id}", {"state": "live"}),
+            ("patch", f"{API_BASE}/listings/{listing_id}", {"state": "live"}),
+        ]
+    )
+
+    for method, url, payload in candidates:
+        try:
+            if method == "put":
+                response = requests.put(
+                    url,
+                    headers=_auth_headers(api_key, json_mode=payload is not None),
+                    json=payload,
+                    timeout=20,
+                )
+            elif method == "post":
+                response = requests.post(
+                    url,
+                    headers=_auth_headers(api_key, json_mode=payload is not None),
+                    json=payload,
+                    timeout=20,
+                )
+            else:
+                response = requests.patch(
+                    url,
+                    headers=_auth_headers(api_key, json_mode=True),
+                    json=payload,
+                    timeout=20,
+                )
+
+            if response.status_code in (200, 201, 202, 204):
+                st.success(f"✅ Listing {listing_id} published")
+                return True
+        except requests.RequestException:
+            continue
+
+    st.warning("Could not publish listing by API.")
+    st.info(f"Publish manually: https://reverb.com/item/{listing_id}/edit")
+    return False
+
+
+def cleanup_images(image_paths: List[str], keep_images: bool = False) -> None:
+    if keep_images:
+        return
+    for image_path in image_paths:
+        try:
+            if os.path.exists(image_path):
+                os.remove(image_path)
+        except OSError:
+            pass
+
+
+# ===== Streamlit UI =====
+with st.sidebar:
+    st.header("⚙️ Settings")
+
+    price_multiplier = st.slider(
+        "Price Multiplier",
+        min_value=0.1,
+        max_value=2.0,
+        value=0.7,
+        step=0.05,
+        help="Multiply original price by this value",
+    )
+
+    keep_images = st.checkbox(
+        "Keep images after upload",
+        value=False,
+        help="Keep downloaded images locally after upload",
+    )
+
+    auto_publish = st.checkbox(
+        "Auto-publish listing",
+        value=True,
+        help="Automatically publish listing after image upload",
+    )
+
+    st.markdown("---")
+    st.markdown("### 📌 Note")
+    st.markdown("If API upload fails, images are saved in the 'images' folder for manual upload.")
+
+api_key = st.text_input("🔑 API Key", type="password", help="Enter your Reverb API key")
+shipping_profile_id = st.text_input("📦 Shipping Profile ID", help="Enter your Shipping Profile ID")
+listing_url = st.text_input("🔗 Listing URL", help="Paste the Reverb listing URL you want to clone")
+
+if st.button("🚀 Start Cloning", type="primary", use_container_width=True):
+    if not api_key:
+        st.error("❌ Please enter your API Key")
+        st.stop()
+    if not shipping_profile_id:
+        st.error("❌ Please enter your Shipping Profile ID")
+        st.stop()
+    if not listing_url:
+        st.error("❌ Please enter a Listing URL")
+        st.stop()
+
+    with st.spinner("Processing your request..."):
+        listing_id = extract_listing_id(listing_url)
+        if not listing_id:
+            st.error("❌ Invalid URL format")
+            st.stop()
+
+        st.info(f"📋 Original Listing ID: {listing_id}")
+
+        original_listing = get_listing(api_key, listing_id)
+        if not original_listing:
+            st.stop()
+
+        st.info("📥 Downloading images...")
+        image_paths = download_images(original_listing)
+        st.success(f"✅ Downloaded {len(image_paths)} images")
+
+        st.info("📝 Creating new listing...")
+        new_listing_id = create_listing(api_key, original_listing, shipping_profile_id, price_multiplier)
+        if not new_listing_id:
+            cleanup_images(image_paths, keep_images=True)
+            st.stop()
+
+        st.success(f"✅ Created new listing with ID: {new_listing_id}")
+
+        st.write("⏳ Waiting for listing to be ready...")
+        for _ in range(6):
+            time.sleep(5)
+            if get_listing(api_key, str(new_listing_id)):
+                break
+
+        if image_paths:
+            st.info("📤 Uploading images...")
+            upload_success = upload_images(api_key, str(new_listing_id), image_paths)
+            if upload_success:
+                st.success("✅ Images uploaded successfully")
+            else:
+                st.warning("⚠️ Some images failed to upload")
+
+        if auto_publish and new_listing_id:
+            st.info("📢 Publishing listing...")
+            publish_listing(api_key, str(new_listing_id))
+
+        cleanup_images(image_paths, keep_images)
+
+        st.balloons()
+        st.success("🎉 Clone completed")
+        st.markdown(f"🔗 [View listing](https://reverb.com/item/{new_listing_id})")
+        st.markdown(f"✏️ [Edit listing](https://reverb.com/item/{new_listing_id}/edit)")
+
+st.markdown("---")
+st.markdown("Made with 🎸 for Reverb sellers")
