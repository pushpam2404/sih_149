# Walkthrough: Erase a File, Then Try to Recover It

This walkthrough is for anyone who wants to use this app, even if you are not
very technical. It explains:

1. What the app does, in plain words
2. How to start it
3. What each page is for
4. A hands-on practice exercise: delete one photo the normal way, securely
   erase another photo, and then see which one can be recovered

You do **not** need to understand programming. You will need to copy and
paste a few commands into the **Terminal** app. Each command is explained.

> **Which computers?** The app runs on Windows, Linux and macOS (its
> automated tests run on all three). The full practice exercise in Part 4
> uses Mac-only commands and was run step by step on a Mac on 2026-09-17.
> **On Windows or Linux, use Part 4B** instead.

---

## Part 1: What does this app do?

When you delete a file normally (Trash, or the `rm` command), the file is
usually **not really gone**. The computer just forgets *where* the file
was, and marks that space as "free to reuse". The actual contents stay on
the disk until something else is written over them. Recovery tools can
often find them.

This app has two sides:

| Side | What it does |
|---|---|
| **Erasing** | Writes random data over a file (or a whole drive) *before* deleting it, so the old contents are replaced with junk. |
| **Recovery** | Scans a disk and tries to find deleted files and bring them back. |

The two sides are meant to be used **together**, to show the difference:
a normally deleted file can often be recovered, a securely erased file
cannot.

> **Important: the Recovery page is not an "undo" button.**
> If you securely erase a file with this app, it is gone. The Recovery
> page will not bring it back — that is the whole point of secure
> erasing. The only way to get it back is from a copy somewhere else
> (Time Machine backup, iCloud, the original download, your phone, etc.).
> **Practice only on files you have copies of.**

### Honest limits

- This is a hackathon prototype, not a certified tool.
- On Mac internal drives (SSD, APFS) the overwrite may not land on the
  same physical spot as the original data. The app warns you about this.
- On USB sticks / FAT-formatted disks, the file's **contents** are
  destroyed, but a leftover record of the **file name** can still be
  found (see Part 5).
- More details: [user_manual.md](user_manual.md) and
  [compliance_mapping.md](compliance_mapping.md).

---

## Part 2: Starting the app

**On a Mac:** open the **Terminal** app (press `⌘ Space`, type `Terminal`,
press Enter) and run:

```bash
cd ~/Desktop/SIH_149
.venv/bin/python -m app.main
```

**On Windows:** open **PowerShell** (press the Windows key, type
`PowerShell`, press Enter) and run:

```powershell
cd $HOME\Desktop\SIH_149
.venv\Scripts\python.exe -m app.main
```

**On Linux:** open a terminal and run the same commands as on a Mac.

- The first line moves into the project folder. If you put the project
  somewhere else, change the path.
- The second line starts the app.

If it says something is missing, follow the setup steps in the
[README](../README.md) first (on Windows that's a single script:
`scripts\setup_env.ps1`).

**Keep this window open** while you use the app — closing it closes the
app.

---

## Part 3: The pages, explained

Use the menu on the left side of the app to switch between pages. The
badge at the bottom of that menu reminds you that **Simulation mode** is
on by default.

| Page | What it's for |
|---|---|
| **Dashboard** | A summary at the top (how many actions are logged, whether the audit log is intact, how many reports exist, the last action), shortcuts to the three main tools, and a list of recent activity. On a fresh install it's empty and fills up as you use the app. |
| **Drive Eraser** | Wipes a **whole** drive or disk image. Your Mac's own internal drive is always shown as `BLOCKED` and can never be picked. "Simulation mode" is on by default, which wipes a copy instead of the real thing. |
| **File & Folder Eraser** | Securely erases **individual files or a folder**. Use this for normal files like photos and documents. The red **Securely erase queue** button starts the erase. |
| **Recovery** | Scans a disk image or a plugged-in drive for deleted files. Results appear in two tabs at the bottom: **Recovered Files** and **PII / Metadata Artifacts**, each with a count. |
| **Audit Log** | A record of everything the app did. **Verify chain integrity** checks if anyone edited the record. |
| **Reports** | PDF reports the app created after each erase or scan. Double-click one to open it. |

### The file window (same on Windows, Linux and Mac)

Whenever the app asks you to pick a file or folder, it opens **its own**
dark file window, which looks and works the same on every computer
(not the usual Finder or File Explorer window):

- **Left side:** your Home, Desktop, Documents and Downloads folders, and
  **every drive** that is plugged in (on a Mac, e.g. `Macintosh HD` or a
  USB stick; on Windows, `C:\`, `D:\` …). Click one to jump there.
- **"File name" box at the bottom:** you can also type or paste a full
  path here (e.g. `/Volumes/DEMOVOL` or `E:\`) and press **Enter** to go
  straight to it.
- **"Files of type" box below it:** limits which files are shown.
- The buttons at the top go back, forward, up one folder, create a new
  folder, and switch between list and detail view.

Drives are listed when the window opens — if you plug one in while it's
open, close the window and open it again.

### "Why can't I see my file?"

The **Select disk image file...** button (Drive Eraser) and **Browse
Image...** button (Recovery) only show disk image files (`.img`, `.dd`,
`.dmg`) by default. Everything else is hidden.

- That's on purpose — these pages work on **whole disks**, not single
  photos or documents.
- If you really need another file: at the bottom of the file window,
  click the **Files of type** box (it says **"Disk images (*.img *.dd
  *.dmg)"**) and change it to **"All files (*)"**.
- **Want to erase a normal file?** Use the **File & Folder Eraser** page
  instead. Its file picker shows all files.

---

## Part 4: Practice exercise — erase vs. recover

We will build a small **pretend USB stick** (a "disk image" file on your
Desktop), put two photos on it, remove them in two different ways, and
then scan it.

Using a disk image means **your real drive is never touched**, and you can
throw it away and start again anytime.

**You need:** two picture files (`.jpg` or `.png`) that you have copies of.

> ⚠️ **The order of steps matters.** Do them exactly as written. The
> reason is explained at the end of this part.

### Step 1 — Create the pretend USB stick

In Terminal:

```bash
cd ~/Desktop
dd if=/dev/zero of=demo.img bs=1m count=64
```

This creates an empty 64 MB file called `demo.img` on your Desktop.

### Step 2 — Connect it to your Mac

```bash
hdiutil attach -imagekey diskimage-class=CRawDiskImage -nomount demo.img
```

It prints a name like **`/dev/disk4`**. **Write this down.**

In the next steps you'll see **`/dev/diskN`**. **`N` is not something to
type** — replace it with the number you just got. For example, if Step 2
printed `/dev/disk4`, then `/dev/diskN` means `/dev/disk4`:

| Guide says | You type (if you got disk4) |
|---|---|
| `diskutil list /dev/diskN` | `diskutil list /dev/disk4` |
| `diskutil eraseVolume MS-DOS DEMOVOL /dev/diskN` | `diskutil eraseVolume MS-DOS DEMOVOL /dev/disk4` |

> **Why is it usually 4?** Your Mac numbers every disk it knows about,
> starting from 0. On a typical Apple Silicon Mac, **disk0 to disk3 are
> already taken by the Mac's own internal drive** (you can see them in
> the app's **Drive Eraser** page, marked `BLOCKED`, or by running
> `diskutil list`). So the pretend stick gets the next free number,
> which is usually **4**.
>
> It can be **higher** (5, 6, …) if you have a USB drive plugged in, or
> another disk image still connected from an earlier try. That's why you
> should always use **the number Step 2 actually printed**, not assume 4.
>
> ⚠️ **Never use 0, 1, 2 or 3.** Those are your Mac's own drive.

You may also see:
```
hdiutil: WARNING: 'hdiutil attach -nomount ...' is deprecated.
```
**Ignore this.** It's just a notice, the command still worked.

### Step 3 — Double-check you have the right disk

This step protects you from formatting the wrong disk by accident.

```bash
diskutil list /dev/diskN
```

It **must** say `(disk image)` and a size of about **67.1 MB**, like:

```
/dev/disk4 (disk image):
   0:                          +67.1 MB    disk4
```

🛑 **If it says anything else (like `internal` or `external, physical`,
or a size in GB), STOP.** You typed the wrong number. Go back to Step 2.

### Step 4 — Format it

```bash
diskutil eraseVolume MS-DOS DEMOVOL /dev/diskN
```

This formats the pretend stick (like a real USB stick) and names it
`DEMOVOL`. It now appears in Finder and at `/Volumes/DEMOVOL`.

### Step 4b — Stop macOS from writing its own logs onto the stick

macOS quietly writes small log files (in a hidden folder called
`.fseventsd`) onto every disk you connect. It does this **on its own, at
random times** — and if it happens after you delete photo1, those logs can
land right on top of photo1 and ruin the recovery. These three commands
turn that off for this pretend stick (replace `N` as before):

```bash
touch /Volumes/DEMOVOL/.fseventsd/no_log
diskutil unmount /dev/diskN
diskutil mount /dev/diskN
```

- The first line creates an empty "no_log" file, which tells macOS "don't
  keep logs on this disk".
- The next two lines disconnect and reconnect the stick so macOS notices.
  After the last one you should see `Volume DEMOVOL on diskN mounted`.

### Step 5 — Copy two photos onto it

```bash
cp "/path/to/your/first picture.png" /Volumes/DEMOVOL/photo1.png
cp "/path/to/your/second picture.jpg" /Volumes/DEMOVOL/photo2.jpg
sync
```

Tips:
- **Always put the path in quotes** `"..."`. File names with spaces
  (like `Screenshot 2026-09-17 at 18.42.51.png`) break without quotes and
  give a confusing `Not a directory` error.
- **Easiest way to get a path:** type `cp ` (with a space), then **drag the
  file from Finder into the Terminal window**. Terminal fills in the path
  for you.
- **Keep the real extension.** A `.jpg` should stay `.jpg`, a `.png` should
  stay `.png`.
- `sync` makes sure everything is really saved to the disk.

Check it worked:

```bash
ls /Volumes/DEMOVOL
```

You should see `photo1.png` and `photo2.jpg`. (macOS also adds hidden
files starting with `._` — that's normal, ignore them.)

### Step 6 — Securely erase photo2 (in the app)

1. In the app, click **File & Folder Eraser** in the left menu.
2. Click **Add files...**
3. In the file window, click **DEMOVOL** on the left side. (Or type
   `/Volumes/DEMOVOL` in the **File name** box and press Enter.)
4. Select **photo2.jpg** and click **Open**.
5. Click **Securely erase queue**.
6. In the confirmation window, type exactly `ERASE FILES`, tick the
   checkbox, and click **Erase permanently**.
7. You'll see `Erase complete — PASS`. A warning window about filesystem
   limits may pop up — that's expected, read it and close it.

**If DEMOVOL looks empty or you get a permission error:** macOS may be
blocking the app from reading removable disks. Go to **System Settings →
Privacy & Security → Files & Folders → Terminal** and turn on
**Removable Volumes**. Then quit the app, start it again (Part 2), and
retry.

### Step 7 — Delete photo1 the normal way

Back in Terminal:

```bash
rm /Volumes/DEMOVOL/photo1.png
sync
```

Use `rm`, **not** Finder's "Move to Trash". Finder only moves it to a
hidden Trash folder on the same disk, so it isn't really deleted.

### Step 8 — Disconnect the pretend stick

```bash
diskutil eject /dev/diskN
```

**Do this right away** after Step 7. Don't copy anything else onto the
stick first. Ejecting makes sure everything is saved into `demo.img`.

### Step 9 — Scan it for deleted files

1. In the app, click **Recovery** in the left menu.
2. Click **Browse image...** and pick **demo.img** on your Desktop.
3. Click **Start recovery scan**. On a 64 MB image this takes a few
   seconds.

### Step 10 — Read the results

The results are in the **Recovered Files** tab at the bottom of the
Recovery page. The **Confidence** column is coloured: green for high,
amber for medium, grey for low. What we saw when we tested this:

| What you'll see | What it means |
|---|---|
| `_hoto1.png` (engine **pytsk3**), type **PNG**, confidence **100** | ✅ **photo1 recovered!** The first letter is replaced by `_` because that's how FAT marks a file as deleted. |
| `f000….png` (engine **photorec**), same size, type **PNG** | ✅ **photo1 again**, found a second way (by searching for picture data). Same SHA-256 = identical file. |
| `_hoto2.jpg` and a random name like `ktrvjgwx7ul31092`, type **unknown**, confidence **20 (low)** | ❌ **photo2 — erased.** The entries still exist, but the contents are random junk. It won't open as a picture. |
| Names starting with `._`, `.gz` files, `.apple` files | Leftover macOS system/housekeeping data. Ignore. |

**If photo1 did NOT come back** — for example `_hoto1.png` shows type
**GZIP** or **unknown** with a tiny size (like 2048), and there is no
**PNG** row from photorec — then something was written on top of the
start of photo1 before the scan. See "Why the order matters" below, then
start over and make sure you did Step 4b.

To **prove** photo1 came back: click its row, click **Export Selected
File...**, save it to your Desktop, and open it. It's your picture.

Try the same with photo2's rows — the exported file won't open as an
image.

**The engines explained:**
- **pytsk3** reads the disk's "table of contents" to find deleted entries.
- **photorec** ignores the table of contents and scans raw data looking
  for patterns that look like the start of a picture, PDF, etc.
- If the status line says `engines unavailable: bulk_extractor`, that's
  fine — that optional tool just isn't installed. It only fills the
  "PII / Metadata Artifacts" table.

### Why the order matters (and why Step 4b exists)

When you delete a file normally, its space is marked as **free**. On FAT
disks (like USB sticks), the next thing written to the disk usually goes
into the **first free space** — which is exactly where photo1 was. Even a
tiny write there destroys the start of photo1 (its "header"). Without the
header, neither recovery engine can recognize it, even if 99.9% of the
picture is still on the disk.

Two things can write to the disk after photo1 is deleted:

1. **The app itself**, when it securely erases photo2 (it creates a few
   small new entries). → That's why you **erase photo2 first** (Step 6)
   and **delete photo1 last** (Step 7).
2. **macOS**, which writes its own `.fseventsd` log files at random times,
   including when you eject. → That's what **Step 4b** turns off.

We hit both of these while writing this walkthrough: once photo1's start was
overwritten by the `.fseventsd` log files (they then showed up in the
results as `f0000297.gz` and `f0000301.gz`, sitting exactly where photo1
used to start). With Step 4b, our test runs wrote **no** log files to the
stick and photo1's start stayed intact in both runs.

So: **Step 4b, erase first, delete normally last, eject immediately.**

### Starting over

```bash
rm ~/Desktop/demo.img
```

Then go back to Step 1. (Make sure it's ejected first — Step 8.)

---

## Part 4B: Practice on Windows or Linux

The Mac exercise above uses `hdiutil` and `diskutil`, which only exist on
macOS. On Windows or Linux there are two options.

### Option 1 — Recovery demo with a practice image (easy, no admin needed)

The project includes a script that builds a small practice disk image
containing a **deleted** copy of any photo you give it. Nothing gets
mounted and no admin rights are needed.

1. In PowerShell (Windows) or a terminal (Linux), go to the project folder
   (see Part 2), then run — replacing the path with a real picture under
   15 MB:

   **Windows:**
   ```powershell
   .venv\Scripts\python.exe -m scripts.make_practice_image "C:\Users\you\Pictures\holiday.jpg"
   ```
   **Linux:**
   ```bash
   .venv/bin/python -m scripts.make_practice_image ~/Pictures/holiday.jpg
   ```

   It prints where it saved `practice.img` (in the project folder).

2. In the app, click **Recovery** in the left menu → **Browse image...** →
   pick `practice.img` → **Start recovery scan**.
3. You should see `_HOTO1.JPG` (engine **pytsk3**) and, if PhotoRec is
   installed, an `f….jpg` (engine **photorec**) — both type **JPEG**,
   confidence **100**. Select one and click **Export selected file...** to
   get your photo back.

We tested this on a Mac with a 10 MB JPEG: both engines returned the photo
byte-for-byte. The script itself is covered by automated tests on Windows
and Linux too.

**What this does *not* show:** the photo on this image was deleted the
normal way. It does not show the File & Folder Eraser beating recovery —
for that, use Option 2.

### Option 2 — Full erase-vs-recover on a spare USB stick

⚠️ **Use a USB stick with nothing on it you need.** Its contents will be
deleted. We have **not** run this option on Windows or Linux ourselves, so
treat it as untested.

1. Format the stick as **FAT32** (Windows: right-click it in File Explorer →
   **Format…**; Linux: the Disks app).
2. Copy two photos onto it: `photo1.jpg` and `photo2.jpg`.
3. **Erase photo2 first:** in the app, **File & Folder Eraser** →
   **Add files...** → click the USB stick's drive on the left side of the
   file window → pick `photo2.jpg` → **Securely Erase
   Queue** → type `ERASE FILES`, tick the box, **Erase permanently**.
4. **Then delete photo1 normally:** Windows — select it and press
   **Shift + Delete** (skips the Recycle Bin). Linux — `rm` it in a terminal.
5. **Don't copy anything else onto the stick, and don't unplug it.**
   Plugging a drive back in lets the OS write its own housekeeping files
   (Windows: `System Volume Information`), which can land on top of photo1.
6. Close the app and start it again **as Administrator** (Windows: right-click
   PowerShell → **Run as administrator**, then start the app as in Part 2)
   or with `sudo` (Linux). Reading a whole USB stick needs these rights.
7. **Recovery** → **Or attached device:** pick the USB stick
   (`\\.\PhysicalDriveN` on Windows, `/dev/sdX` on Linux) → **Start Recovery
   Scan**.
8. Expected, as in the Mac test: photo1 comes back as a JPEG; photo2 only
   appears as random data (type **unknown**, low confidence).

Why the order matters is explained in Part 4 ("Why the order matters").
Anything written to the stick after step 4 — by you or by the operating
system — can overwrite photo1.

---

## Part 5: Things that surprise people

- **The erased file's name can still show up.** In Step 10, `_hoto2.jpg`
  still shows most of photo2's original name. On FAT disks, the app
  renames the file before deleting it, but FAT keeps a deleted record of
  the old name anyway. The **contents** are destroyed; the **name** is not
  fully hidden.
- **Type "unknown" with low confidence** is what an erased file *should*
  look like — random data isn't any known file type.
- **Confidence scores** only compare results within the same scan. "100"
  does not mean "100% guaranteed".
- **Scanning your Mac's internal drive** won't work well. It needs special
  permissions, and Mac SSDs clean up deleted space quickly on their own.
  Use disk images or USB sticks for practice.

---

## Part 6: Quick troubleshooting

| Problem | Fix |
|---|---|
| `cp: ... Not a directory` | The file path has spaces. Put it in quotes, or drag the file into Terminal. |
| `No such file or directory` | Typo in the path or wrong extension (e.g. `.jpg` vs `.png`). Run `ls /Volumes/DEMOVOL` to see real names. |
| `/Volumes/DEMOVOL` doesn't exist | You skipped Step 4 (format), or the image was already ejected. |
| `Could not find disk for /dev/diskN` | You typed the letter `N`. Replace it with your number from Step 2, e.g. `/dev/disk4`. |
| Forgot the number from Step 2 | Run `diskutil list` and find the line that says `(disk image)` with a size of about 67.1 MB — e.g. `/dev/disk4 (disk image):`. That's your number. |
| `diskutil image attach ... doesn't exist` | Don't use `diskutil image attach`. Use the `hdiutil attach` command from Step 2 exactly. |
| A drive looks empty in the File & Folder Eraser (Mac) | See the note at the end of Step 6 (Removable Volumes permission). |
| My file isn't shown in Drive Eraser / Recovery | Change **Files of type** to "All files (*)" — see Part 3. |
| A USB stick isn't on the left side of the file window | It was plugged in after the window opened. Close the window and open it again. |
| Recovery finds nothing from the normally deleted file (photo1 shows as GZIP/unknown, no PNG row) | Something wrote over the start of photo1: Step 4b was skipped, steps were done out of order, or something was copied onto the stick after deleting. Start over. |
| `touch: /Volumes/DEMOVOL/.fseventsd/no_log: No such file or directory` | The stick isn't mounted, or Step 4 didn't finish. Run `ls /Volumes` — you should see `DEMOVOL`. |
| Recovery shows 0 results at all | Check the status line for `engines unavailable`. If both `pytsk3` and `photorec` are listed, the setup is incomplete — see the README. |
