"""Thumbnails for the gallery: Pillow on the PC, Android's own decoders (incl. HEIC and video) in the app.
Without either, the UI falls back to file icons."""
import importlib.util

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    Image = None

THUMB_SIZE = 480
ON_ANDROID = importlib.util.find_spec("java") is not None  # Chaquopy's Java bridge


def make_thumbnail(source, destination, mime):
    try:
        if ON_ANDROID:
            return _android_thumbnail(source, destination, mime)
        if Image is None or not mime.startswith("image/"):
            return False
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((THUMB_SIZE, THUMB_SIZE))
            image.convert("RGB").save(destination, "JPEG", quality=82)
        return True
    except Exception:
        return False


def _android_thumbnail(source, destination, mime):
    from java import jclass

    File = jclass("java.io.File")
    Size = jclass("android.util.Size")
    ThumbnailUtils = jclass("android.media.ThumbnailUtils")
    if mime.startswith("image/"):
        bitmap = ThumbnailUtils.createImageThumbnail(File(str(source)), Size(THUMB_SIZE, THUMB_SIZE), None)
    elif mime.startswith("video/"):
        bitmap = ThumbnailUtils.createVideoThumbnail(File(str(source)), Size(THUMB_SIZE, THUMB_SIZE), None)
    else:
        return False
    out = jclass("java.io.FileOutputStream")(str(destination))
    try:
        bitmap.compress(jclass("android.graphics.Bitmap$CompressFormat").JPEG, 82, out)
    finally:
        out.close()
        bitmap.recycle()
    return True
