# Local Hosting Playbook

Host a project from your own computer and make it reachable from anywhere on Earth: first over plain HTTP with router port forwarding, then over HTTPS with a real or self-signed certificate.

This playbook was written from a real run on a MacBook (macOS, Apple Silicon) behind a JioFiber home router. Each step says whether it was **✅ tested**, **❌ failed (and why)**, or **⚠️ documented but not tested** in that run.

> Placeholders used below. Replace them with your own values:
>
> | Placeholder | Meaning | Example |
> |---|---|---|
> | `<LAN_IP>` | Your computer's address on the home network | `192.168.29.114` |
> | `<ROUTER_IP>` | Your router / gateway | `192.168.29.1` |
> | `<PUBLIC_IP>` | Your internet-facing address | `49.x.x.x` |
> | `<PORT>` | Port your site runs on | `8080` |

---

## How it fits together

```
                Internet
                    │
   visitor ──► <PUBLIC_IP>:<PORT>          (path A: port forwarding)
                    │
              ┌─────▼─────┐
              │  Router   │  port-forward rule: <PORT> → <LAN_IP>:<PORT>
              └─────┬─────┘
                    │  home network
              ┌─────▼─────┐
              │ Your Mac  │  python3 -m http.server <PORT>
              └─────▲─────┘
                    │  outbound connection, no open ports needed
              ┌─────┴─────┐
   visitor ──►│Cloudflare │◄── https://xxxx.trycloudflare.com   (path B: tunnel)
              └───────────┘
```

* **Path A: port forwarding.** Your router passes outside traffic on a port to your computer. You get a link on your own IP.
* **Path B: tunnel.** Your computer connects out to Cloudflare, and Cloudflare serves it on HTTPS. No router changes and no open ports. Use it when your ISP blocks ports or puts you behind CGNAT.

---

## Prerequisites

| Tool | Why | Install (macOS) |
|---|---|---|
| Python 3 | Built-in web server | Ships with Xcode Command Line Tools (`xcode-select --install`) |
| Homebrew | Installs everything else | <https://brew.sh> |
| `certbot` | Let's Encrypt certificates | `brew install certbot` |
| `cloudflared` | Cloudflare Tunnel | `brew install cloudflared` |
| `openssl` | Self-signed certificates | Already on macOS, or `brew install openssl` |

On Linux, use your package manager (`apt install python3 certbot openssl`). cloudflared has packages at <https://pkg.cloudflare.com>.

---

## Part 1: Create the site ✅

Any folder with an `index.html` will do. A sample is in [`site/index.html`](site/index.html).

```bash
mkdir -p ~/mini-site
cp site/index.html ~/mini-site/
```

Using your own project: point the server at its build output folder (`dist/`, `build/`, `public/`), or run its own dev server and use that port in the steps below.

---

## Part 2: Serve it locally ✅

```bash
cd ~/mini-site && python3 -m http.server 8080 --bind 0.0.0.0
```

* `--bind 0.0.0.0` accepts connections from other devices. Without it, only this computer can open the site.
* Leave this terminal open. Each visit prints a log line, and **Ctrl+C** stops the server.
* Check it: open <http://localhost:8080>.

Run it in the background instead:

```bash
cd ~/mini-site && nohup python3 -m http.server 8080 --bind 0.0.0.0 > server.log 2>&1 &
```

---

## Part 3: Find your three addresses ✅

```bash
ipconfig getifaddr en0                                # <LAN_IP>    (try en1 if empty)
route -n get default | awk '/gateway/{print $2}'      # <ROUTER_IP>
curl -s https://api.ipify.org                         # <PUBLIC_IP>
```

Linux: `hostname -I`, `ip route | grep default`, same `curl`.

Test from another device on the same Wi-Fi: `http://<LAN_IP>:8080`.

### CGNAT check (do this before port forwarding)

Open your router's status page and find its **WAN IP**:

* **WAN IP = `<PUBLIC_IP>`.** You have a real public IP, so port forwarding can work.
* **WAN IP differs** (often `100.64.x.x`–`100.127.x.x` or `10.x.x.x`). Your ISP shares one public IP among many customers (CGNAT), so port forwarding **cannot** work. Skip to [Part 7: Cloudflare Tunnel](#part-7-https-via-cloudflare-tunnel-).

---

## Part 4: Port-forward on the router ✅

1. Open `http://<ROUTER_IP>` and log in.
2. Find **Port Forwarding** (also called *Virtual Server*, *NAT*, or *Applications*). On JioFiber it's under **Security → Port Forwarding**.
3. Add a rule:

   | Field | Value |
   |---|---|
   | External / WAN port | `8080` |
   | Internal / Destination IP | `<LAN_IP>` |
   | Internal port | `8080` |
   | Protocol | TCP |
   | Source IP (if asked) | Any |
   | Action (JioFiber) | Allow Always |

   JioFiber's form has a **Services** dropdown. **HTTP** means port 80 and **HTTPS** means port 443. For other ports, choose a custom or user-defined service.
4. Save.
5. **Recommended:** in the router's DHCP settings, reserve `<LAN_IP>` for your computer, so the rule doesn't break when the address changes.
6. macOS: if a dialog asks to *allow incoming connections* for `python3`, click **Allow**. Check the firewall state with:
   ```bash
   /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
   ```

---

## Part 5: Test from the outside world ✅

**Test from outside your network.** On a phone, turn **Wi-Fi off** (use mobile data) and open:

```
http://<PUBLIC_IP>:8080
```

Testing from inside your home network often fails even when everything is set up right, because many routers can't loop traffic back to themselves (no NAT hairpin support).

The site is now reachable from anywhere, but only over plain HTTP. The next parts add HTTPS.

---

## Choosing an HTTPS method

Browsers show a padlock only for a certificate from a trusted authority, issued for the exact **domain name** or **IP address** in the URL.

| Method | Link looks like | Browser trust | Needs open ports? | Status in our run |
|---|---|---|---|---|
| [A. Let's Encrypt for a bare IP](#part-6a-lets-encrypt-certificate-for-a-bare-ip-) | `https://<PUBLIC_IP>` | ✅ trusted | **80 or 443 inbound** | ❌ ISP blocked 80/443 |
| [B. Free domain + Let's Encrypt (DNS-01)](#part-6b-free-domain--lets-encrypt-via-dns-01-%EF%B8%8F) | `https://name.duckdns.org:8443` | ✅ trusted | Only your site's port | ⚠️ not tested |
| [C. Self-signed](#part-6c-self-signed-certificate-) | `https://<PUBLIC_IP>:8443` | ⚠️ warning page | Only your site's port | ✅ works |
| [D. Cloudflare Tunnel](#part-7-https-via-cloudflare-tunnel-) | `https://random.trycloudflare.com` | ✅ trusted | **None** | ✅ works |

All of these HTTPS options use [`scripts/serve_https.py`](scripts/serve_https.py), a tiny static HTTPS server built on Python's standard library:

```bash
python3 scripts/serve_https.py --dir ~/mini-site --port 8443 --cert <cert-file> --key <key-file>
```

---

## Part 6A: Let's Encrypt certificate for a bare IP ❌

Let's Encrypt can issue certificates for IP addresses. They are **short-lived** (about 6 days), so renewal must be automatic. Let's Encrypt proves you control the IP by fetching a file from `http://<PUBLIC_IP>/` on **port 80**. That port must reach your computer from the internet.

**What happened in our run:** ports 80 and 443 timed out from the outside, even with router rules in place and the Mac's firewall off. Port 8080 worked. The ISP (JioFiber) blocks inbound 80 and 443, which is common on home connections. If that happens to you too, use B, C, or D.

### Steps (they will work if port 80 reaches your machine)

1. Install certbot (needs v5.1 or later for `--ip-address`):
   ```bash
   brew install certbot && certbot --version
   ```
2. Forward **port 80** (and **443** for the final site) on the router to `<LAN_IP>`, as in Part 4.
3. Serve the site folder on port 80. Let's Encrypt fetches the challenge file from `<site>/.well-known/acme-challenge/`. macOS 10.14+ lets normal users bind port 80 on `0.0.0.0`; on Linux, run with `sudo`.
   ```bash
   mkdir -p ~/mini-site/.well-known/acme-challenge ~/.certbot/{config,work,logs}
   cd ~/mini-site && nohup python3 -m http.server 80 --bind 0.0.0.0 > http80.log 2>&1 &
   ```
4. Test from mobile data first: `http://<PUBLIC_IP>` must show your page. If it times out, stop here: port 80 is blocked.
5. Request the certificate. This stores everything in your home folder, so no `sudo` is needed. `--agree-tos` accepts the [Let's Encrypt Subscriber Agreement](https://letsencrypt.org/repository/).
   ```bash
   certbot certonly --webroot -w ~/mini-site \
     --ip-address <PUBLIC_IP> --preferred-profile shortlived \
     --config-dir ~/.certbot/config --work-dir ~/.certbot/work --logs-dir ~/.certbot/logs \
     --agree-tos --register-unsafely-without-email --non-interactive
   ```
   Files land in `~/.certbot/config/live/<PUBLIC_IP>/`: `fullchain.pem` (the certificate) and `privkey.pem` (the key).
6. Serve HTTPS on 443:
   ```bash
   python3 scripts/serve_https.py --dir ~/mini-site --port 443 \
     --cert ~/.certbot/config/live/<PUBLIC_IP>/fullchain.pem \
     --key  ~/.certbot/config/live/<PUBLIC_IP>/privkey.pem
   ```
   Open `https://<PUBLIC_IP>`.
7. Set up auto-renewal (required: the certificate expires in about 6 days). Run `crontab -e` and add:
   ```cron
   0 */12 * * * /opt/homebrew/bin/certbot renew --config-dir ~/.certbot/config --work-dir ~/.certbot/work --logs-dir ~/.certbot/logs --quiet --deploy-hook "pkill -f serve_https.py"
   ```
   Then keep `serve_https.py` running under something that restarts it, such as a `launchd` agent or a `while true; do …; done` loop, so it picks up the new certificate.

**Caveat:** home public IPs change. If yours changes, the certificate no longer matches and the link changes too.

### Our failed output, for reference

```
Detail: <PUBLIC_IP>: Fetching http://<PUBLIC_IP>/.well-known/acme-challenge/…:
        Timeout during connect (likely firewall problem)
```

The diagnosis: `http80.log` showed no outside visits, and the macOS firewall was off. So the block was upstream, at the router or ISP.

---

## Part 6B: Free domain + Let's Encrypt via DNS-01 ⚠️

This is the best option when ports 80 and 443 are blocked but you still want a trusted padlock on your own connection. Let's Encrypt checks a **DNS TXT record** instead of a port, so it needs no inbound ports at all.

*Not tested in our run. Follow the official docs linked below for exact flags.*

1. Sign up at <https://www.duckdns.org>, create a subdomain (for example `myname.duckdns.org`), point it at `<PUBLIC_IP>`, and copy your **token**.
2. Install [acme.sh](https://github.com/acmesh-official/acme.sh), which has built-in DuckDNS support:
   ```bash
   curl https://get.acme.sh | sh -s email=you@example.com
   ```
3. Issue the certificate:
   ```bash
   export DuckDNS_Token="<your-token>"
   ~/.acme.sh/acme.sh --issue --dns dns_duckdns -d myname.duckdns.org --server letsencrypt
   ```
4. Forward a non-blocked port (for example **8443**) on the router to `<LAN_IP>:8443`, then serve:
   ```bash
   python3 scripts/serve_https.py --dir ~/mini-site --port 8443 \
     --cert ~/.acme.sh/myname.duckdns.org_ecc/fullchain.cer \
     --key  ~/.acme.sh/myname.duckdns.org_ecc/myname.duckdns.org.key
   ```
5. Open `https://myname.duckdns.org:8443`. acme.sh installs its own renewal cron job (90-day certificates).

---

## Part 6C: Self-signed certificate ✅

Anyone can generate this in seconds, with no domain or authority. Traffic is encrypted, but browsers show **"Your connection is not private"** because nobody vouches for the certificate. It's good for testing, internal tools, or your own devices.

1. Generate a certificate and key valid for one year. Put **every address you'll use** in `subjectAltName`; browsers ignore the CN.
   ```bash
   mkdir -p ~/mini-site-ssl && cd ~/mini-site-ssl
   openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 \
     -keyout key.pem -out cert.pem \
     -subj "/CN=<PUBLIC_IP>" \
     -addext "subjectAltName=IP:<PUBLIC_IP>,IP:<LAN_IP>,IP:127.0.0.1,DNS:localhost"
   ```
2. Check it:
   ```bash
   openssl x509 -in cert.pem -noout -subject -ext subjectAltName -enddate
   ```
3. Serve:
   ```bash
   python3 scripts/serve_https.py --dir ~/mini-site --port 8443 --cert cert.pem --key key.pem
   ```
4. Forward port **8443** on the router to `<LAN_IP>:8443`, then open `https://<PUBLIC_IP>:8443`, click **Advanced**, then **Proceed**.
5. Optional, to remove the warning on **your own** Mac: trust the certificate.
   ```bash
   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain cert.pem
   ```
   Other visitors will still see the warning.

Command-line test: `curl --cacert cert.pem https://localhost:8443/` succeeds. Plain `curl https://localhost:8443/` fails, which is the expected behavior for an untrusted certificate.

**Never commit `key.pem` to git.** This repo's `.gitignore` blocks `*.pem` and `*.key`.

---

## Part 7: HTTPS via Cloudflare Tunnel ✅

This is the easiest way to get a trusted HTTPS link. It works behind CGNAT and ISP port blocks, and needs **no router rules**. This is what we ended up using.

1. Install cloudflared:
   ```bash
   brew install cloudflared
   ```
2. Make sure your local server is running (Part 2).
3. Start a quick tunnel (no account needed):
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
   The output includes a line like:
   ```
   https://gmc-thunder-miller-korea.trycloudflare.com
   ```
   Share that link. Cloudflare provides the trusted certificate.
4. If the link says *"site can't be found"* for the first minute, DNS is still propagating. Wait, or try from another device.
5. Run it in the background instead:
   ```bash
   nohup cloudflared tunnel --url http://localhost:8080 > tunnel.log 2>&1 &
   grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log
   ```

**Limitations of quick tunnels:** the URL is random and **changes every restart**, and quick tunnels have no uptime guarantee.

**Permanent URL:** create a free Cloudflare account, add a domain you own, then:

```bash
cloudflared tunnel login
cloudflared tunnel create mysite
cloudflared tunnel route dns mysite www.example.com
cloudflared tunnel run --url http://localhost:8080 mysite
```

(⚠️ not tested in our run: see <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/>.)

Once the tunnel works, you can **delete all router port-forward rules**. The tunnel doesn't use them.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `OSError: [Errno 48] Address already in use` | A server is already running on that port | `lsof -nP -iTCP:8080 -sTCP:LISTEN` to see it, `pkill -f "http.server 8080"` to stop it |
| Works on `localhost`, not from other home devices | Missing `--bind 0.0.0.0`, or macOS firewall | Add the flag, or allow `python3` in the firewall |
| Works at home, not on mobile data | No router rule, wrong `<LAN_IP>`, or CGNAT | Recheck Part 4, then the CGNAT check in Part 3 |
| Works on mobile data, not from home Wi-Fi via `<PUBLIC_IP>` | Router lacks NAT hairpin support | Normal. Use `<LAN_IP>` at home |
| Ports 80/443 time out, others work | ISP blocks low ports inbound | Use 6B, 6C (on 8443), or 7 |
| certbot: *Timeout during connect (likely firewall problem)* | Let's Encrypt can't reach port 80 | Same as above |
| `curl: (6) Could not resolve host …trycloudflare.com` | New tunnel's DNS not propagated yet | Wait 30–60 s |
| Link died after reboot | Server and tunnel don't auto-start | Re-run Part 2 and Part 7. The tunnel URL will be new |

Useful checks:

```bash
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(80|443|8080|8443) '   # what's listening
cat ~/mini-site/server.log                                     # did outside requests arrive?
```

---

## Shutting it all down

```bash
pkill cloudflared                    # stop the tunnel
pkill -f "http.server"               # stop Python HTTP servers
pkill -f serve_https.py              # stop HTTPS servers
```

Then **delete the port-forward rules** on the router, and remove any cron renewal job (`crontab -e`).

---

## Security checklist

* Everything in the served folder is public. Never serve your home directory or a folder with secrets.
* `python3 -m http.server` is meant for development. For long-term public hosting, put a real server (Caddy or nginx) or the tunnel in front.
* Keep private keys (`*.pem`, `*.key`) out of git and out of the served folder.
* Close port-forward rules when you're not using them. Prefer the tunnel, which opens no ports.
* Your public IP reveals your approximate location and ISP. A tunnel hides it from visitors.

---

## Repo layout

```
.
├── README.md              ← this playbook
├── site/index.html        ← sample page
├── scripts/serve_https.py ← tiny HTTPS static server (stdlib only)
└── .gitignore             ← keeps keys/certs/logs out of git
```
