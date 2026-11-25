package com.zevarl.zhunze;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.util.LruCache;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.ScaleGestureDetector;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;

/**
 * App 内阅读 PDF：用系统自带的 PdfRenderer 逐页渲染。
 * 双指缩放或点 －/＋ 调整大小；放大后可左右滑动。
 * 打不开的 PDF（加密、格式特殊）提示用其他应用打开。
 */
public class PdfActivity extends Activity {
    private static final float[] ZOOMS = {1f, 1.5f, 2f, 3f};
    private static final int MAX_RENDER_W = 2200;   // 渲染宽度上限，防止放大后内存不够

    private String url, name;
    private File file;
    private ParcelFileDescriptor pfd;
    private PdfRenderer renderer;
    private final Object lock = new Object();
    private int zoomIdx = 0, baseWidth = 0;
    private float pinch = 1f;

    private ListView list;
    private HorizontalScrollView hsv;
    private TextView status, pageInfo;
    private ProgressBar progress;
    private LruCache<String, Bitmap> cache;
    private PageAdapter adapter;

    private int dp(float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private TextView barButton(String text, View.OnClickListener l) {
        TextView b = new TextView(this);
        b.setText(text);
        b.setTextColor(Color.WHITE);
        b.setTextSize(15);
        b.setPadding(dp(12), dp(10), dp(12), dp(10));
        b.setOnClickListener(l);
        return b;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        url = getIntent().getStringExtra("url");
        name = getIntent().getStringExtra("name");
        int maxKb = (int) (Runtime.getRuntime().maxMemory() / 1024 / 5);
        cache = new LruCache<String, Bitmap>(maxKb) {
            @Override
            protected int sizeOf(String k, Bitmap b) {
                return b.getByteCount() / 1024;
            }
        };

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor("#E9EBEF"));

        // 顶栏
        LinearLayout bar = new LinearLayout(this);
        bar.setBackgroundColor(Color.parseColor("#1B2A41"));
        bar.setGravity(Gravity.CENTER_VERTICAL);
        TextView back = barButton("‹ 返回", v -> finish());
        TextView title = new TextView(this);
        title.setText(name == null ? "PDF" : name);
        title.setTextColor(Color.WHITE);
        title.setTextSize(14);
        title.setSingleLine(true);
        title.setEllipsize(android.text.TextUtils.TruncateAt.MIDDLE);
        bar.addView(back);
        bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        bar.addView(barButton("下载", v -> Downloader.enqueue(this, url, name, false)));
        bar.addView(barButton("其他应用", v -> Downloader.enqueue(this, url, name, true)));
        root.addView(bar);

        // 内容区
        FrameLayout content = new FrameLayout(this);
        hsv = new HorizontalScrollView(this);
        hsv.setFillViewport(true);
        list = new ListView(this);
        list.setPadding(dp(8), dp(8), dp(8), dp(8));
        list.setClipToPadding(false);
        list.setDividerHeight(dp(8));
        list.setDivider(new android.graphics.drawable.ColorDrawable(Color.TRANSPARENT));
        hsv.addView(list, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        content.addView(hsv);
        LinearLayout loading = new LinearLayout(this);
        loading.setOrientation(LinearLayout.VERTICAL);
        loading.setGravity(Gravity.CENTER);
        progress = new ProgressBar(this);
        status = new TextView(this);
        status.setText("正在下载附件…");
        status.setTextColor(Color.parseColor("#646A73"));
        status.setGravity(Gravity.CENTER);
        status.setPadding(dp(24), dp(12), dp(24), 0);
        loading.addView(progress);
        loading.addView(status);
        content.addView(loading, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        root.addView(content, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        // 底栏：页码 + 缩放
        LinearLayout foot = new LinearLayout(this);
        foot.setBackgroundColor(Color.WHITE);
        foot.setGravity(Gravity.CENTER_VERTICAL);
        foot.setPadding(dp(12), 0, dp(4), 0);
        pageInfo = new TextView(this);
        pageInfo.setTextColor(Color.parseColor("#646A73"));
        foot.addView(pageInfo, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        TextView minus = barButton("－", v -> setZoom(zoomIdx - 1));
        TextView plus = barButton("＋", v -> setZoom(zoomIdx + 1));
        minus.setTextColor(Color.parseColor("#1B2A41"));
        plus.setTextColor(Color.parseColor("#1B2A41"));
        minus.setTextSize(20);
        plus.setTextSize(20);
        foot.addView(minus);
        foot.addView(plus);
        root.addView(foot);
        setContentView(root);

        // 双指缩放：松手时取最接近的档位
        ScaleGestureDetector sgd = new ScaleGestureDetector(this, new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override
            public boolean onScaleBegin(ScaleGestureDetector d) {
                pinch = 1f;
                return true;
            }

            @Override
            public boolean onScale(ScaleGestureDetector d) {
                pinch *= d.getScaleFactor();
                return true;
            }

            @Override
            public void onScaleEnd(ScaleGestureDetector d) {
                float target = ZOOMS[zoomIdx] * pinch;
                int best = 0;
                for (int i = 0; i < ZOOMS.length; i++)
                    if (Math.abs(ZOOMS[i] - target) < Math.abs(ZOOMS[best] - target)) best = i;
                setZoom(best);
            }
        });
        list.setOnTouchListener((v, e) -> {
            sgd.onTouchEvent(e);
            return e.getPointerCount() > 1;
        });
        list.setOnScrollListener(new AbsListView.OnScrollListener() {
            public void onScrollStateChanged(AbsListView v, int s) { }

            public void onScroll(AbsListView v, int first, int visible, int total) {
                if (total > 0) pageInfo.setText((first + 1) + " / " + total + " 页");
            }
        });

        new Thread(this::download).start();
    }

    private void fail(String msg) {
        runOnUiThread(() -> {
            progress.setVisibility(View.GONE);
            status.setText(msg + "\n\n可以点右上角「其他应用」用手机上的 PDF 阅读器打开，或点「下载」保存。");
        });
    }

    private void download() {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-1");
            StringBuilder h = new StringBuilder();
            for (byte b : md.digest(url.getBytes("UTF-8"))) h.append(String.format("%02x", b));
            File dir = new File(getCacheDir(), "pdf");
            dir.mkdirs();
            file = new File(dir, h + ".pdf");
            if (!file.exists() || file.length() == 0) {
                String u = url;
                HttpURLConnection c = null;
                for (int i = 0; i < 5; i++) {          // 手动跟随跳转（http ↔ https 之间系统不会自动跳）
                    c = (HttpURLConnection) new URL(u).openConnection();
                    c.setInstanceFollowRedirects(false);
                    c.setRequestProperty("User-Agent", Downloader.UA);
                    c.setConnectTimeout(20000);
                    c.setReadTimeout(60000);
                    int code = c.getResponseCode();
                    if (code >= 300 && code < 400 && c.getHeaderField("Location") != null) {
                        u = new URL(new URL(u), c.getHeaderField("Location")).toString();
                        c.disconnect();
                        continue;
                    }
                    if (code != 200) throw new Exception("服务器返回 " + code);
                    break;
                }
                long total = c.getContentLength();
                File tmp = new File(dir, h + ".part");
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(tmp)) {
                    byte[] buf = new byte[32768];
                    long got = 0;
                    int n;
                    long lastUi = 0;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n);
                        got += n;
                        if (total > 0 && System.currentTimeMillis() - lastUi > 200) {
                            lastUi = System.currentTimeMillis();
                            final int pct = (int) (got * 100 / total);
                            runOnUiThread(() -> status.setText("正在下载附件… " + pct + "%"));
                        }
                    }
                }
                c.disconnect();
                if (!tmp.renameTo(file)) throw new Exception("保存失败");
            }
            runOnUiThread(this::openPdf);
        } catch (Exception e) {
            fail("下载失败：" + e.getMessage());
        }
    }

    private void openPdf() {
        try {
            pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
            renderer = new PdfRenderer(pfd);
        } catch (Exception e) {
            file.delete();
            fail("这个文件无法在应用内显示（可能不是 PDF，或者加了密）。");
            return;
        }
        ((View) progress.getParent()).setVisibility(View.GONE);
        hsv.post(() -> {
            baseWidth = hsv.getWidth() - dp(16);
            applyWidth();
            adapter = new PageAdapter();
            list.setAdapter(adapter);
            pageInfo.setText("1 / " + renderer.getPageCount() + " 页");
        });
    }

    private void applyWidth() {
        int w = (int) (baseWidth * ZOOMS[zoomIdx]) + dp(16);
        ViewGroup.LayoutParams lp = list.getLayoutParams();
        lp.width = zoomIdx == 0 ? ViewGroup.LayoutParams.MATCH_PARENT : w;
        list.setLayoutParams(lp);
    }

    private void setZoom(int idx) {
        if (renderer == null || adapter == null) return;
        idx = Math.max(0, Math.min(ZOOMS.length - 1, idx));
        if (idx == zoomIdx) return;
        int pos = list.getFirstVisiblePosition();
        zoomIdx = idx;
        cache.evictAll();
        applyWidth();
        adapter.notifyDataSetChanged();
        list.setSelection(pos);
    }

    private Bitmap render(int page, int width) {
        String key = page + "@" + width;
        Bitmap b = cache.get(key);
        if (b != null) return b;
        synchronized (lock) {
            if (renderer == null) return null;
            PdfRenderer.Page p = renderer.openPage(page);
            int rw = Math.min(width, MAX_RENDER_W);
            int rh = (int) ((long) rw * p.getHeight() / p.getWidth());
            b = Bitmap.createBitmap(rw, rh, Bitmap.Config.ARGB_8888);
            b.eraseColor(Color.WHITE);
            p.render(b, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
            p.close();
        }
        cache.put(key, b);
        return b;
    }

    private class PageAdapter extends BaseAdapter {
        public int getCount() {
            return renderer == null ? 0 : renderer.getPageCount();
        }

        public Object getItem(int i) {
            return i;
        }

        public long getItemId(int i) {
            return i;
        }

        public View getView(int pos, View convert, ViewGroup parent) {
            ImageView iv = convert instanceof ImageView ? (ImageView) convert : new ImageView(PdfActivity.this);
            iv.setScaleType(ImageView.ScaleType.FIT_XY);
            int w = (int) (baseWidth * ZOOMS[zoomIdx]);
            Bitmap b = render(pos, w);
            int h = b == null ? w : (int) ((long) w * b.getHeight() / b.getWidth());
            iv.setLayoutParams(new AbsListView.LayoutParams(w, h));
            iv.setImageBitmap(b);
            iv.setPadding(0, 0, 0, 0);
            return iv;
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        synchronized (lock) {
            try {
                if (renderer != null) renderer.close();
                if (pfd != null) pfd.close();
            } catch (Exception ignored) {
            }
            renderer = null;
        }
    }
}
