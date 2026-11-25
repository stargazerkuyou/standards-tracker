package com.zevarl.zhunze;

import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.webkit.MimeTypeMap;
import android.widget.Toast;

import java.util.HashSet;
import java.util.Set;

/**
 * 用系统下载器下载附件：
 * - 保存位置：Android 10 及以上在「下载/准则追踪」；更老的系统在 App 自己的下载目录
 * - openAfter=true：下载完成后用手机上的其他应用（WPS、PDF 阅读器等）打开
 */
public class Downloader {
    static final String UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124.0 Mobile Safari/537.36";
    private static final Set<Long> openAfterIds = new HashSet<>();
    private static boolean registered = false;

    static String fileName(String url, String name) {
        String ext = MimeTypeMap.getFileExtensionFromUrl(url);
        if (ext == null || ext.isEmpty()) {
            int dot = url.lastIndexOf('.');
            ext = dot > 0 && url.length() - dot <= 5 ? url.substring(dot + 1) : "";
        }
        String base = (name == null || name.trim().isEmpty()) ? url.substring(url.lastIndexOf('/') + 1) : name.trim();
        base = base.replaceAll("[\\\\/:*?\"<>|\\r\\n]", "_");
        if (base.length() > 80) base = base.substring(0, 80);
        if (!ext.isEmpty() && !base.toLowerCase().endsWith("." + ext.toLowerCase())) base = base + "." + ext;
        return base;
    }

    static String mimeOf(String url) {
        String ext = MimeTypeMap.getFileExtensionFromUrl(url);
        String m = ext == null ? null : MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
        return m == null ? "application/octet-stream" : m;
    }

    static void enqueue(Context ctx, String url, String name, boolean openAfter) {
        try {
            ensureReceiver(ctx.getApplicationContext());
            String fname = fileName(url, name);
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            r.setTitle(fname);
            r.setDescription("准则追踪");
            r.addRequestHeader("User-Agent", UA);
            r.setMimeType(mimeOf(url));
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            if (Build.VERSION.SDK_INT >= 29) {
                r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "准则追踪/" + fname);
            } else {
                r.setDestinationInExternalFilesDir(ctx, Environment.DIRECTORY_DOWNLOADS, fname);
            }
            DownloadManager dm = (DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE);
            long id = dm.enqueue(r);
            if (openAfter) {
                synchronized (openAfterIds) {
                    openAfterIds.add(id);
                }
                Toast.makeText(ctx, "正在下载，完成后自动打开", Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(ctx, Build.VERSION.SDK_INT >= 29 ? "开始下载，保存在「下载/准则追踪」" : "开始下载，完成后可在通知栏打开",
                        Toast.LENGTH_LONG).show();
            }
        } catch (Exception e) {
            Toast.makeText(ctx, "下载失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private static void ensureReceiver(Context app) {
        if (registered) return;
        registered = true;
        BroadcastReceiver rcv = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent intent) {
                long id = intent.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1);
                boolean open;
                synchronized (openAfterIds) {
                    open = openAfterIds.remove(id);
                }
                if (!open) return;
                DownloadManager dm = (DownloadManager) c.getSystemService(Context.DOWNLOAD_SERVICE);
                Uri uri = dm.getUriForDownloadedFile(id);
                if (uri == null) {
                    Toast.makeText(c, "下载没有成功，请稍后再试", Toast.LENGTH_LONG).show();
                    return;
                }
                String mime = dm.getMimeTypeForDownloadedFile(id);
                Intent view = new Intent(Intent.ACTION_VIEW);
                view.setDataAndType(uri, mime == null ? "*/*" : mime);
                view.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                Intent chooser = Intent.createChooser(view, "用其他应用打开");
                chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try {
                    c.startActivity(chooser);
                } catch (ActivityNotFoundException e) {
                    Toast.makeText(c, "手机上没有能打开这种文件的应用", Toast.LENGTH_LONG).show();
                }
            }
        };
        IntentFilter f = new IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= 33) {
            app.registerReceiver(rcv, f, Context.RECEIVER_EXPORTED);
        } else {
            app.registerReceiver(rcv, f);
        }
    }
}
