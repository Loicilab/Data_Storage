package app.datastore;

import android.app.Activity;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.net.Uri;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Shows the shared Data Store UI. The same Python engine as the PC app runs inside this process
 * (via Chaquopy) and serves the UI on 127.0.0.1; uploads go straight from the phone to the providers.
 */
public class MainActivity extends Activity {
    private static final int PICK_FILES = 1;
    private static final String TAG = "DataStore";

    private final ExecutorService background = Executors.newCachedThreadPool();
    private final long created = SystemClock.elapsedRealtime();
    private WebView web;
    private TextView splash;
    private ValueCallback<Uri[]> pendingPick;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Start Python and the engine first, in the background, while the WebView is being set up.
        String filesDir = getFilesDir().getAbsolutePath();
        String rclone = getApplicationInfo().nativeLibraryDir + "/librclone.so";
        String cacheDir = getCacheDir().getAbsolutePath();
        AndroidPlatform platform = new AndroidPlatform(getApplicationContext());
        background.execute(() -> {
            try {
                synchronized (MainActivity.class) {
                    if (!Python.isStarted()) {
                        Python.start(platform);
                    }
                }
                Log.i(TAG, "Python runtime up after " + (SystemClock.elapsedRealtime() - created) + " ms");
                String url = Python.getInstance().getModule("datastore.mobile")
                        .callAttr("start", filesDir, rclone, cacheDir).toString();
                Log.i(TAG, "Engine serving " + url + " after " + (SystemClock.elapsedRealtime() - created) + " ms");
                runOnUiThread(() -> web.loadUrl(url));
            } catch (Throwable error) {
                runOnUiThread(() -> splash.setText(getString(R.string.start_failed, String.valueOf(error))));
            }
        });

        WebView.setWebContentsDebuggingEnabled((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0);
        web = new WebView(this);
        splash = new TextView(this);
        splash.setText(R.string.starting);
        splash.setGravity(Gravity.CENTER);
        FrameLayout root = new FrameLayout(this);
        root.addView(web);
        root.addView(splash);
        setContentView(root);
        configureWebView();
    }

    private void configureWebView() {
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setAllowFileAccess(false);
        settings.setUserAgentString(settings.getUserAgentString() + " DataStoreApp/1");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("127.0.0.1".equals(uri.getHost())) {
                    return false;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));  // external links open in the browser
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (splash.getVisibility() == View.VISIBLE) {
                    Log.i(TAG, "UI shown " + (SystemClock.elapsedRealtime() - created) + " ms after launch");
                }
                splash.setVisibility(View.GONE);
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (pendingPick != null) {
                    pendingPick.onReceiveValue(null);
                }
                pendingPick = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT)
                        .addCategory(Intent.CATEGORY_OPENABLE)
                        .setType("*/*")
                        .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try {
                    startActivityForResult(pick, PICK_FILES);
                } catch (Exception error) {
                    pendingPick = null;
                    callback.onReceiveValue(null);
                }
                return true;
            }
        });

        web.setDownloadListener((url, userAgent, disposition, mimeType, length) -> download(url, disposition, mimeType));
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != PICK_FILES || pendingPick == null) {
            super.onActivityResult(requestCode, resultCode, data);
            return;
        }
        Uri[] picked = null;
        if (resultCode == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                picked = new Uri[data.getClipData().getItemCount()];
                for (int i = 0; i < picked.length; i++) {
                    picked[i] = data.getClipData().getItemAt(i).getUri();
                }
            } else if (data.getData() != null) {
                picked = new Uri[] {data.getData()};
            }
        }
        pendingPick.onReceiveValue(picked);
        pendingPick = null;
    }

    /** Saves a file served by the local engine into the phone's Downloads folder. */
    private void download(String url, String disposition, String mimeType) {
        String name = fileName(url, disposition, mimeType);
        String cookie = CookieManager.getInstance().getCookie(url);
        toast(getString(R.string.downloading, name));
        background.execute(() -> {
            Uri item = null;
            try {
                HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
                if (cookie != null) {
                    connection.setRequestProperty("Cookie", cookie);
                }
                ContentValues values = new ContentValues();
                values.put(MediaStore.Downloads.DISPLAY_NAME, name);
                values.put(MediaStore.Downloads.MIME_TYPE, mimeType);
                values.put(MediaStore.Downloads.IS_PENDING, 1);
                item = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                try (InputStream in = connection.getInputStream();
                     OutputStream out = getContentResolver().openOutputStream(item)) {
                    byte[] buffer = new byte[1 << 16];
                    for (int n; (n = in.read(buffer)) > 0; ) {
                        out.write(buffer, 0, n);
                    }
                }
                values.clear();
                values.put(MediaStore.Downloads.IS_PENDING, 0);
                getContentResolver().update(item, values, null, null);
                toast(getString(R.string.downloaded, name));
            } catch (Exception error) {
                if (item != null) {
                    getContentResolver().delete(item, null, null);
                }
                toast(getString(R.string.download_failed, name));
            }
        });
    }

    private static String fileName(String url, String disposition, String mimeType) {
        if (disposition != null) {
            int at = disposition.indexOf("filename*=UTF-8''");
            if (at >= 0) {
                return Uri.decode(disposition.substring(at + 17).split(";")[0].trim());
            }
        }
        return URLUtil.guessFileName(url, disposition, mimeType);
    }

    private void toast(String text) {
        runOnUiThread(() -> Toast.makeText(this, text, Toast.LENGTH_SHORT).show());
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
