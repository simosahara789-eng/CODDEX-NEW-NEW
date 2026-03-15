diff --git a/app.py b/app.py
new file mode 100644
index 0000000000000000000000000000000000000000..b5b396e3f5f49f9338ee3deb01832b9687748e3d
--- /dev/null
+++ b/app.py
@@ -0,0 +1,108 @@
+import streamlit as st
+
+from reverb_cloner.core import (
+    cleanup_images,
+    create_listing,
+    download_images,
+    extract_listing_id,
+    get_listing,
+    parse_new_listing_id,
+    publish_listing,
+    upload_images,
+    wait_until_listing_ready,
+)
+
+st.set_page_config(page_title="Reverb Cloner PRO", page_icon="🎸", layout="centered")
+st.title("🎸 Reverb Cloner PRO")
+st.caption("Clone listing data + images to a new draft and optionally publish.")
+st.markdown("---")
+
+with st.sidebar:
+    st.header("⚙️ Settings")
+    price_multiplier = st.slider("Price Multiplier", 0.1, 2.0, 0.7, 0.05)
+    keep_images = st.checkbox("Keep images in local ./images folder", value=False)
+    auto_publish = st.checkbox("Auto publish after upload", value=False)
+
+api_key = st.text_input("🔑 API Key", type="password")
+shipping_profile_id = st.text_input("📦 Shipping Profile ID")
+source_listing_url = st.text_input("🔗 Source Listing URL")
+
+if st.button("🚀 Start Cloning", type="primary", use_container_width=True):
+    if not api_key or not shipping_profile_id or not source_listing_url:
+        st.error("Please fill in API key, shipping profile ID, and source URL.")
+        st.stop()
+
+    listing_id = extract_listing_id(source_listing_url)
+    if not listing_id:
+        st.error("Could not parse listing ID from URL.")
+        st.stop()
+
+    st.info(f"Source listing ID: {listing_id}")
+
+    source_result = get_listing(api_key, listing_id)
+    if not source_result.ok or not source_result.payload:
+        st.error(f"Failed to fetch source listing: {source_result.status_code}")
+        st.code(source_result.text[:500] or "No response body")
+        st.stop()
+
+    with st.spinner("Downloading source images..."):
+        image_paths = download_images(source_result.payload)
+    st.success(f"Downloaded {len(image_paths)} images.")
+
+    with st.spinner("Creating new draft listing..."):
+        create_result = create_listing(
+            api_key=api_key,
+            original_listing=source_result.payload,
+            shipping_profile_id=shipping_profile_id,
+            price_multiplier=price_multiplier,
+        )
+
+    if not create_result.ok:
+        st.error(f"Listing creation failed: {create_result.status_code}")
+        st.code(create_result.text[:500] or "No response body")
+        cleanup_images(image_paths, keep_images=True)
+        st.stop()
+
+    new_listing_id = parse_new_listing_id(create_result)
+    if not new_listing_id:
+        st.error("Created listing but could not parse new listing ID from API response.")
+        st.code(str(create_result.payload))
+        cleanup_images(image_paths, keep_images=True)
+        st.stop()
+
+    st.success(f"Created draft listing: {new_listing_id}")
+
+    with st.spinner("Waiting until new listing is ready..."):
+        ready = wait_until_listing_ready(api_key, new_listing_id)
+    if not ready:
+        st.warning("Listing may not be fully ready yet. Upload may fail if Reverb is still processing it.")
+
+    if image_paths:
+        st.subheader("📤 Upload Images")
+        with st.spinner("Uploading images to new draft..."):
+            uploaded_count, upload_logs = upload_images(api_key, new_listing_id, image_paths)
+
+        st.write(f"Uploaded {uploaded_count}/{len(image_paths)} images.")
+        with st.expander("Detailed upload logs"):
+            for log in upload_logs:
+                st.write(f"- {log}")
+
+        if uploaded_count == 0:
+            st.warning("No images were uploaded by API. Use manual upload for this draft.")
+            st.markdown(f"[Open draft editor](https://reverb.com/item/{new_listing_id}/edit)")
+
+    if auto_publish:
+        with st.spinner("Publishing listing..."):
+            publish_result = publish_listing(api_key, new_listing_id)
+
+        if publish_result.ok:
+            st.success("Listing published successfully ✅")
+        else:
+            st.warning("Publish API call failed. You can publish manually from the listing editor.")
+
+    cleanup_images(image_paths, keep_images=keep_images)
+
+    st.markdown("---")
+    st.success("Clone flow completed.")
+    st.markdown(f"🔗 [View listing](https://reverb.com/item/{new_listing_id})")
+    st.markdown(f"✏️ [Edit listing](https://reverb.com/item/{new_listing_id}/edit)")
