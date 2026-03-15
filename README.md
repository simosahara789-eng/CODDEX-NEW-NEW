# Reverb Cloner PRO (Streamlit)

This app clones a Reverb listing into a new draft, downloads source images, uploads them to the new draft, and can optionally publish.

## Files included

- `app.py` — Streamlit UI.
- `reverb_cloner/core.py` — Reverb API logic (fetch/create/upload/publish/cleanup).
- `requirements.txt` — Python dependencies.
- `.env.example` — Example environment variables.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Why image upload previously failed (404)

Reverb endpoints can differ by account/api behavior. Hardcoding only `/photos` often returns `404`.
This implementation:

1. Reads upload links from listing `_links` first.
2. Falls back to both `images` and `photos` endpoint variants.
3. Tries multipart field names: `photo`, `image`, `file`.

## Manual fallback

If API upload still fails for your account, keep the downloaded files and upload in the listing edit page:

`https://reverb.com/item/<new_listing_id>/edit`

