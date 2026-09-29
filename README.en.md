# inemadlp

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

Personal video and audio downloader (FastAPI + yt-dlp) that runs on your VPS. You
paste the link on your phone, the VPS downloads the file and sends it back — it
deletes itself after 6 hours.

## 📖 User guide

Complete guide (landing page + step-by-step instructions): **https://inematds.github.io/inemadlp/guia/en/**

---

## Table of contents

1. [The three `.env` keys](#the-three-env-keys)
2. [Before you begin](#before-you-begin)
3. [Deployment step by step](#deployment-step-by-step)
4. [Remote access and ports](#remote-access-and-ports)
5. [After startup: your first download](#after-startup-your-first-download)
6. [Cookies](#cookies)
7. [Transcription](#transcription)
8. [Update](#update)
9. [Day-to-day operation](#day-to-day-operation)
10. [When something goes wrong](#when-something-goes-wrong)

---

## The three `.env` keys

The `.env` file has three secrets with **different** roles. It’s worth understanding
them before generating them, because the consequences of exposing or changing each
one are different.

### `DLP_PASSWORD` — the password **you** type

The only one you use yourself. It appears on the login screen. You type it once
on your phone and never again, because the session does not expire.

- **To change it:** edit the line and run `docker compose restart app`. Existing
  sessions remain valid (this is intentional — changing the password does not log
  you out).
- **Be careful:** it’s the only thing between the internet and your `cookies.txt`,
  which contains your Google/YouTube/Instagram session. There is no lockout for
  incorrect attempts, by design. So it **needs to be long and random**, not a
  password you can memorize.

### `DLP_SECRET_KEY` — the session cookie signature

You never type this. When you enter the correct password, the server returns a
cookie signed with this key. With each request, it checks the signature to make
sure it issued the cookie itself, and that nobody made it up.

- **If it leaks:** anyone can create a valid cookie and log in **without knowing
  the password**. This is just as serious as leaking the password.
- **If you change it:** everyone is logged out, including you. It’s the “end all
  sessions” button — use it if you lose your phone.
- It’s **independent of the password**, which is why changing the password does
  not log anyone out.

### `DLP_UPLOAD_TOKEN` — the script credential

Used only by `sync-cookies.sh`. It runs by itself in cron, without a browser or
session, so it needs another way to prove its identity: it sends the token in the
`X-Upload-Token` header.

It’s a machine password for **one route only** (`POST /api/cookies`). It doesn’t
list jobs, download files, or create downloads.

- **If it leaks:** the damage is limited — someone could replace your
  `cookies.txt`, which would break your downloads, but nothing is exposed (the
  route only receives the file; it never sends it back).
- **If you change it:** you just need to update the cron entry.

**In short:** password = you log in · secret key = the server recognizes you
afterward · upload token = the script logs in by itself through a single small
door.

---

## Before you begin

You need to have three things ready:

| What | Why |
|---|---|
| A **Linux VPS** with `ssh` access | it’s where everything runs |
| **Docker + Compose** installed on it | the only dependency; ffmpeg, yt-dlp, and a JS runtime (Deno) are included in the image |
| A **subdomain** pointed to the VPS IP | Caddy issues the HTTPS certificate automatically |

> YouTube started requiring a JavaScript runtime to solve its challenges before
> it releases video formats. That’s why the image already includes Deno and
> yt-dlp’s EJS support, updated at each boot along with yt-dlp itself.

Install Docker if you don’t already have it:

```bash
curl -fsSL https://get.docker.com | sh
```

DNS must be pointed **before** you start the service. In your domain provider’s
control panel, create an A record:

```
Type   Name            Value
A      dlp             203.0.113.10      ← your VPS IP
```

Check that it has propagated (it may take a few minutes):

```bash
dig +short dlp.seudominio    # it should return the VPS IP
```

---

## Deployment step by step

Everything below runs **inside the VPS**, over `ssh`.

### Quick option: the installer

It does everything — generates the three secrets, writes the `.env` file with the
correct permissions, starts the containers, and prints the password at the end:

```bash
ssh usuario@203.0.113.10

git clone https://github.com/inematds/inemadlp.git
cd inemadlp
./instalar.sh dlp.seudominio
```

It warns you if DNS doesn’t point to the machine yet, normalizes the domain if
you accidentally include `https://`, and asks before changing an existing `.env`
(adjusting only the domain without changing your password). If you run it again
later, it also detects and fixes duplicate `DLP_DOMAIN` lines.

Afterward, skip to [After startup](#after-startup-your-first-download).

### Manual option

If you prefer to do it by hand or understand each part:

### 1. Connect to the VPS and clone the repository

```bash
ssh usuario@203.0.113.10

git clone https://github.com/inematds/inemadlp.git
cd inemadlp
```

### 2. Generate the three secrets

Run the three commands and **save each output** — you’ll paste them into `.env`
in the next step:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(24))"   # → DLP_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → DLP_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → DLP_UPLOAD_TOKEN
```

The password from the first command is the one you’ll type on your phone — save
it in your password manager.

### 3. Fill in `.env`

```bash
cp .env.example .env
nano .env          # or vim
```

Set it up like this, using the values you just generated:

```ini
DLP_PASSWORD=<output from the 1st command>
DLP_SECRET_KEY=<output from the 2nd command>
DLP_UPLOAD_TOKEN=<output from the 3rd command>
DLP_TTL_HOURS=6
DLP_DATA_DIR=/data
DLP_DOMAIN=dlp.seudominio
```

> **Edit the existing `DLP_DOMAIN` line** — don’t add another one with
> `echo ... >> .env`. When there are two identical lines, Docker uses the last
> one, and Caddy ends up requesting a certificate for the wrong domain. The
> symptom is that the site won’t open because of a certificate error, even
> though everything else appears to be correct.

Protect the file — it contains all three secrets in plain text:

```bash
chmod 600 .env
```

### 4. Start the service

```bash
docker compose up --build -d
```

The first build takes a few minutes (it downloads Python and ffmpeg). Follow the
logs:

```bash
docker compose logs -f
```

You should see `uvicorn running on http://0.0.0.0:8000` from the app and Caddy
obtaining the certificate. Press `Ctrl-C` to exit the logs without stopping
anything.

### 5. Confirm it’s running

```bash
curl -I https://dlp.seudominio
```

An `HTTP/2 200` means Caddy has obtained the certificate and the app is responding.
If there’s a certificate error, it’s almost always because DNS hasn’t propagated
yet or port 80 is closed — see the next section.

---

## Remote access and ports

**You don’t need to configure anything for remote access beyond DNS.** Access it
through the site itself: open `https://dlp.seudominio` from anywhere, on your
phone or desktop, and log in with your password. No VPN, tunnel, or strange port
to remember.

### Ports involved

| Port | Used by | Does it need to be open? |
|---|---|---|
| **443** | HTTPS — how you access inemadlp | **yes** |
| **80** | Caddy, to issue/renew the certificate and redirect to 443 | **yes** (without it, HTTPS won’t be issued) |
| **22** | Your `ssh` connection for managing the VPS | **yes** |
| 8000 | The app, **only inside** the Docker network | **no** — and it should stay that way |

A note about port 8000: in `docker-compose.yml`, the `app` service uses
`expose`, not `ports`. This means it can be reached **only** by Caddy, from
inside Docker’s internal network. It doesn’t exist on the internet. That ensures
nobody can reach the service by bypassing HTTPS and the password.

### Open the firewall

Most VPS providers have **two** firewalls: the system firewall and the
provider’s firewall.

On the system (Ubuntu, with `ufw`):

```bash
sudo ufw allow OpenSSH      # don’t lock yourself out
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status              # check before ending the ssh session
```

In the provider’s control panel (AWS security group, Oracle Cloud firewall,
DigitalOcean, Hetzner…), allow the same ports — **22, 80, and 443**. This step
is easy to forget: `ufw` is configured correctly, but the control panel blocks
traffic, so the certificate is never issued.

### Make the VPS more secure (optional, recommended)

Since the machine is now exposed, it’s worth hardening `ssh`:

```bash
# use a key instead of a password, and disable password login
sudo nano /etc/ssh/sshd_config
#   PasswordAuthentication no
#   PermitRootLogin no
sudo systemctl restart ssh
```

---

## After startup: your first download

### 1. Install it on your phone

Open `https://dlp.seudominio` in your phone’s browser, enter the password, and
select **"Add to Home Screen"**. It becomes an icon that works like an app. The
session doesn’t expire, so you won’t need to enter the password again.

### 2. Upload cookies

Without this, YouTube will probably refuse downloads from your VPS because its IP
is from a data center. In Edge or Chrome, while **logged in** to YouTube:

1. install the [**Get cookies.txt LOCALLY**](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension;
2. open YouTube, click the extension, and export `cookies.txt`;
3. in inemadlp, open the **Cookies** panel and upload the file.

The panel will show the date of the latest upload.

### 3. Download

Paste the URL, choose **Video** (MP4, up to 1080p) or **Audio** (M4A), and submit.
The item appears in the list as “queued,” changes to “downloading NN%,” and
finishes with the video title and a **Download** button.

Remember: the file is available for **6 hours**. After that, it disappears from
the VPS and you’ll need to queue it again. To keep it longer, change
`DLP_TTL_HOURS` in `.env` and restart.

---

## Cookies

### Why this is necessary

YouTube (and Instagram, TikTok…) distrusts connections from data centers. Your
VPS is a data center. Without cookies, the download fails with a message like
*"Sign in to confirm you're not a bot"*.

The cookies prove that an account is logged in. You get them from **your
browser**, where you’re already logged in, and give them to the VPS to use.

Cookies are **not your password**. They’re your active session. Even so, anyone
with the file can access your account — which is why it lives only on your VPS,
protected by your inemadlp password.

### Step by step (Windows, Edge, or Chrome)

**1. Install the extension** — just once.

**Get cookies.txt LOCALLY** — direct link:
https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc

It’s open source and works offline: it reads cookies from your browser and
creates a file without sending anything anywhere.

It works with Chrome and Edge — Edge installs it from the same store (the first
time, it asks you to confirm that extensions from another store are allowed).

**2. Open the site and confirm you’re logged in**

Go to `https://www.youtube.com` and check whether your profile picture appears in
the top-right corner. If you’re not logged in, sign in. **This step matters** —
the extension only copies what’s there at that moment.

**3. Export**

Still on the YouTube tab, click the extension icon (you may need to click the
puzzle piece 🧩 to find it) and choose **Export** (or *Export as*
→ `cookies.txt`).

A `cookies.txt` file will appear in your Downloads folder. It starts with the
line `# Netscape HTTP Cookie File` — inemadlp rejects the file if that line
isn’t there, precisely because yt-dlp would reject it too.

inemadlp also accepts the **JSON** export offered by some versions of this and
other extensions. If the export page lets you choose between `cookies.txt` and
JSON, **prefer `cookies.txt`**: it’s the format yt-dlp reads natively, so there’s
one less conversion step and less chance of an error. If the panel rejects the
file, the message now explains why (malformed JSON, an HTML page saved by
mistake, fields separated by spaces instead of TABs, an empty file, etc.) and
how to fix it.

**4. Upload to inemadlp**

1. open `https://seu-dominio` (on your PC; it’s easier than on your phone);
2. log in with your password if prompted;
3. at the bottom, click **Cookies** to open the panel;
4. click the file picker and select the `cookies.txt` you just downloaded;
5. the panel responds with the number of cookies received and shows the upload
   date.

That’s it. Now you can queue a link.

**5. Delete the downloaded file**

The `cookies.txt` file in your Downloads folder gives access to your account.
Delete it after uploading.

### When to do this again

Only when a download fails. The interface says *"cookies expired — upload a new
cookies.txt"* when it recognizes the cause, so you don’t have to guess.

In practice, YouTube cookies last for weeks, sometimes months. Instagram and
TikTok cookies expire much faster. Repeat steps 2 through 5 and queue the link
again — there’s no automatic retry.

### Why this can’t be automated on Windows

Edge and Chrome started encrypting cookies with App-Bound Encryption in version
127: only the browser process itself can access the key. No external script can
read those cookies, no matter what permissions it has. That’s why you need to
export them through the extension.

### Shortcut, only if you use Firefox on Linux

Firefox stores cookies without this encryption, so you can automate the process.
On a Linux machine with Firefox logged in:

```bash
# get the token from the VPS:  grep DLP_UPLOAD_TOKEN .env
DLP_URL=https://seu-dominio DLP_UPLOAD_TOKEN=<token> ./sync-cookies.sh
```

If you never want to see the error again, set up a weekly cron job:

```cron
0 9 * * 1 DLP_URL=https://seu-dominio DLP_UPLOAD_TOKEN=<token> /caminho/para/inemadlp/sync-cookies.sh
```

---

## Transcription

There’s a third option alongside Video and Audio: **Transcription**, using
Whisper (`whisper-large-v3-turbo`) through the Groq API. There are two ways to
request it:

- Directly: paste the link and choose **Transcription** in the form — the job
  downloads and transcribes the audio from scratch.
- From a completed job: video or audio jobs with “ready” status get a
  **Transcribe** button, which reuses the file already downloaded instead of
  fetching the source again (it downloads it again only if the file has expired).

The text appears on the same screen in an expandable block with a copy button —
designed for phones, where opening a downloaded `.txt` file is a hassle — and
you can also download the `.txt` using the usual button.

**Known limitation, by design: long videos are excluded.**

Groq’s transcription API accepts files up to **25 MB**. The audio is resampled
to 16 kHz mono — the format Whisper uses internally — and compressed to mp3 at
64 kbit/s (constant bitrate, so the file size doesn’t depend on the content).
Measured at about 481 KB per minute, the 25 MB limit is reached at approximately
**54 minutes of audio**.

Above that limit, the job is **rejected with a notice** stating the audio duration
and the limit, without making an API call. There is no automatic splitting: it
would be possible to cut the audio into pieces and stitch the text together, but
that was deliberately left out to keep things simple. So long classes and
podcasts aren’t transcribed here — use inemavox for those.

Requires `GROQ_API_KEY` in `.env`. Without the key, the option doesn’t appear in
the interface.

Other Groq limits, for reference: 7,200 seconds of audio and 2,000 requests per
quota window. The `whisper-large-v3-turbo` model costs around US$ 0.04 per hour
of audio.

---

## Update

On the VPS, run one command:

```bash
cd inemadlp
./atualizar.sh
```

It fetches the new code, rebuilds the image, recreates the containers, and checks
that the site responds again. Before doing any of that, if there are uncommitted
local edits, it **warns you and asks** — anything you want to keep goes into
`git stash`, where you can restore it with `git stash pop`. The `.env` file is
never touched: your password, keys, cookies, and downloaded files stay where
they are.

If the local history has diverged from the remote, it stops instead of creating
a silent merge and explains how to resolve the issue.

Or do it by hand:

```bash
git pull
docker compose up -d --build
```

`--build` is required — without it, Docker reuses the old image and the update
has no effect.

After updating, the version appears discreetly in the interface footer
(`inemadlp vX.Y.Z`) — just open the site and check that it matches the new
version before considering the VPS updated.

---

## Day-to-day operation

```bash
docker compose logs -f app     # see what’s happening
docker compose restart app     # restarts and updates yt-dlp
docker compose down            # shuts down (the data in ./data remains)
docker compose up -d           # starts it again
```

**Change the password:** edit `DLP_PASSWORD` in `.env` and run
`docker compose restart app`. Existing sessions remain valid.

**End all sessions** (lost phone): also change `DLP_SECRET_KEY` and restart.
Then everyone, including you, will need to log in again.

**Update the code:**

```bash
git pull && docker compose up --build -d
```

---

## When something goes wrong

| Symptom | Likely cause | What to do |
|---|---|---|
| The site won’t open; certificate error | DNS hasn’t propagated, or port 80 is closed | `dig +short dlp.seudominio` and check the provider firewall |
| Download fails with “cookies expired” | the cookies expired | export and upload them again, then queue the link again (there’s no automatic retry) |
| Download fails with “Requested format is not available” or the format list is empty | YouTube requires a JS runtime (Deno/EJS) and the image is outdated | `docker compose pull && docker compose up -d --build`; boot already updates yt-dlp/deno automatically, but a very old image may not yet support EJS |
| Download fails with another message | the source isn’t supported, or the URL is wrong | the raw yt-dlp message appears in the list |
| The file disappeared | the 6-hour TTL has passed | queue it again, or increase `DLP_TTL_HOURS` |
| Job is stuck on “downloading” after a restart | the container restarted mid-download | it changes to “error” by itself on boot; queue it again |
| Disk is filling up | unlikely (automatic cleanup is enabled) | `du -sh data/downloads` and `docker compose logs app` |
