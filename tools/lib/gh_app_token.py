"""Mint (and cache) an installation token for the agents' GitHub App.

Agents run many `gh` calls. On one personal login they share that account's hourly GraphQL budget,
and on the owner's other project they used it up on 2026-10-16. An app installation token has its own budget, so agents use it
through tools/agent-bin/gh, and the account's own login keeps its budget for the board and for Ben.

Config: ~/.config/tvt/gh-app.env (never in the repo), lines KEY=VALUE:
  TVT_GH_APP_ID=<the app's numeric App ID>
  TVT_GH_APP_INSTALLATION_ID=<the installation's id, from its settings URL>
  TVT_GH_APP_KEY=<path to the app's private key .pem, mode 600>
  TVT_GH_APP_REPOS=treasure-valley-traffic   (optional; the default. Each token is scoped to these repositories,
                                comma-separated, even when the app is installed on more of them)
Cache: ~/.cache/tvt/gh-app-token.json (mode 600), reused until 10 minutes before expiry.
Prints the token on stdout. Exit 1 when it isn't configured (the wrapper then uses the login silently), 2 on any
error (it prints one line "gh-app-token: <ExceptionType>: <message>" to stderr, never the token).
Needs python3 and the openssl CLI (both on macOS and the project's VM).
"""
import base64, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error
from datetime import datetime, timezone

CONF = os.path.expanduser("~/.config/tvt/gh-app.env")
CACHE = os.path.expanduser("~/.cache/tvt/gh-app-token.json")
MARGIN_S = 600


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def load_conf() -> dict:
    if not os.path.exists(CONF):
        sys.exit(1)
    conf = {}
    with open(CONF) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip().strip('"')
    for k in ("TVT_GH_APP_ID", "TVT_GH_APP_INSTALLATION_ID", "TVT_GH_APP_KEY"):
        if not conf.get(k):
            print(f"gh-app-token: {k} missing in {CONF}", file=sys.stderr)
            sys.exit(2)
    conf["TVT_GH_APP_KEY"] = os.path.expanduser(conf["TVT_GH_APP_KEY"])
    return conf


def cached(conf: dict) -> str:
    try:
        with open(CACHE) as f:
            c = json.load(f)
        if c.get("repos") != conf.get("TVT_GH_APP_REPOS", "treasure-valley-traffic"):
            return ""
        exp = datetime.strptime(c["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        if exp - time.time() > MARGIN_S and isinstance(c["token"], str) and c["token"]:
            return c["token"]
    except Exception:  # a missing or malformed cache ([], null, a non-string field, ...) means: mint anew
        pass
    return ""


def jwt(app_id: str, key: str) -> str:
    now = int(time.time())
    head = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = b64url(json.dumps({"iat": now - 60, "exp": now + 540, "iss": app_id}, separators=(",", ":")).encode())
    signing = f"{head}.{body}".encode()
    sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key], input=signing, capture_output=True, check=True).stdout
    return f"{head}.{body}.{b64url(sig)}"


def mint(conf: dict) -> dict:
    url = f"https://api.github.com/app/installations/{conf['TVT_GH_APP_INSTALLATION_ID']}/access_tokens"
    repos = [r.strip() for r in conf.get("TVT_GH_APP_REPOS", "treasure-valley-traffic").split(",") if r.strip()]
    req = urllib.request.Request(url, method="POST", data=json.dumps({"repositories": repos}).encode(), headers={
        "Authorization": "Bearer " + jwt(conf["TVT_GH_APP_ID"], conf["TVT_GH_APP_KEY"]),
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "treasure-valley-traffic-gh-app-token (+https://github.com/Benten-Ben/treasure-valley-traffic)"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def store(conf: dict, res: dict) -> None:
    """Best-effort cache write: a temp file of our own (mkstemp: mode 600, a unique name, so concurrent mints
    never share one), then an atomic replace. Any failure (OSError included) removes the temp file and leaves the cache as it was; the token is still printed."""
    tmp = ""
    try:
        d = os.path.dirname(CACHE)
        os.makedirs(d, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".gh-app-token.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump({"token": res["token"], "expires_at": res["expires_at"],
                       "repos": conf.get("TVT_GH_APP_REPOS", "treasure-valley-traffic")}, f)
        os.replace(tmp, CACHE)
    except Exception:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def run() -> None:
    conf = load_conf()
    tok = cached(conf)
    if tok:
        print(tok)
        return
    try:
        res = mint(conf)
    except (urllib.error.URLError, subprocess.CalledProcessError, OSError, ValueError) as e:
        print(f"gh-app-token: could not mint a token: {e}", file=sys.stderr)
        sys.exit(2)
    store(conf, res)
    print(res["token"])


def main() -> None:
    try:
        run()
    except Exception as e:  # SystemExit (exit 1: not configured, exit 2: configured but failing) passes through
        print(f"gh-app-token: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
