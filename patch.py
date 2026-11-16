#!/usr/bin/env python3
import os

RES_DIR = os.path.join("app", "src", "main", "res")

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Päivitetty: {path}")

# 1. Väriresurssit vaalealle ja tummalle tilalle
colors_day = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="notif_title_color">#0F1722</color>
    <color name="notif_subtitle_color">#334155</color>
</resources>
"""

colors_night = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="notif_title_color">#F1F5F9</color>
    <color name="notif_subtitle_color">#CBD5E1</color>
</resources>
"""

# 2. Päivitetyt ilmoitusasettelut (@color-viittauksilla)
layout_notif_expanded = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="12dp">

    <TextView
        android:id="@+id/notifTitle"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Vuoro alkaa klo 07:00"
        android:textColor="@color/notif_title_color"
        android:textSize="15sp"
        android:textStyle="bold" />

    <TextView
        android:id="@+id/notifSubtitle"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="2dp"
        android:text="Aamuvuoro"
        android:textColor="@color/notif_subtitle_color"
        android:textSize="13sp" />

    <TextView
        android:id="@+id/btnNotifStamp"
        android:layout_width="match_parent"
        android:layout_height="40dp"
        android:layout_marginTop="10dp"
        android:background="@drawable/bg_notif_btn_in"
        android:clickable="true"
        android:focusable="true"
        android:gravity="center"
        android:text="LEIMAA SISÄÄN"
        android:textColor="#FFFFFF"
        android:textSize="14sp"
        android:textStyle="bold" />
</LinearLayout>
"""

layout_notif_collapsed = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:gravity="center_vertical"
    android:orientation="horizontal"
    android:padding="10dp">

    <LinearLayout
        android:layout_width="0dp"
        android:layout_height="wrap_content"
        android:layout_weight="1"
        android:orientation="vertical"
        android:paddingEnd="8dp">

        <TextView
            android:id="@+id/notifTitleCollapsed"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:ellipsize="end"
            android:maxLines="1"
            android:text="Vuoro alkaa klo 07:00"
            android:textColor="@color/notif_title_color"
            android:textSize="14sp"
            android:textStyle="bold" />

        <TextView
            android:id="@+id/notifSubtitleCollapsed"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:ellipsize="end"
            android:maxLines="1"
            android:text="Aamuvuoro"
            android:textColor="@color/notif_subtitle_color"
            android:textSize="12sp" />
    </LinearLayout>

    <TextView
        android:id="@+id/btnNotifStampCollapsed"
        android:layout_width="wrap_content"
        android:layout_height="34dp"
        android:background="@drawable/bg_notif_btn_in"
        android:clickable="true"
        android:focusable="true"
        android:gravity="center"
        android:paddingStart="14dp"
        android:paddingEnd="14dp"
        android:text="SISÄÄN"
        android:textColor="#FFFFFF"
        android:textSize="12sp"
        android:textStyle="bold" />
</LinearLayout>
"""

write_file(os.path.join(RES_DIR, "values", "notif_colors.xml"), colors_day)
write_file(os.path.join(RES_DIR, "values-night", "notif_colors.xml"), colors_night)
write_file(os.path.join(RES_DIR, "layout", "notification_stamp_expanded.xml"), layout_notif_expanded)
write_file(os.path.join(RES_DIR, "layout", "notification_stamp_collapsed.xml"), layout_notif_collapsed)

print("Notifikaation tekstivärit päivitetty vaalealle ja tummalle tilalle!")
