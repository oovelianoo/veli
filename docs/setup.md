# VELI profile package — setup

This package is designed to become the public profile README for `oovelianoo`.
It has no frontend runtime and no build step for the visual layer: GitHub renders
the local SVG assets directly from the repository.

> GitHub only displays a README as the account profile surface when it lives in
> the special repository `oovelianoo/oovelianoo`. If you keep this package in
> `oovelianoo/veli`, it will render as the README for the `veli` repository, which
> is still fully supported by this package.

## 1. Install it as the profile repository

1. Create or open the repository named exactly `oovelianoo` under the GitHub account `oovelianoo`.
   The profile repository must match the username character-for-character.
2. Copy the contents of this package into the repository root.
3. Commit the files to the default branch and open the profile page at
   `https://github.com/oovelianoo`.
4. Confirm that the repository is public and that the root file is named `README.md`.

The minimum runtime package is:

```text
README.md
assets/
  hero.svg
  whoami.svg
  systems.svg
  stack.svg
  telemetry.svg
  footer.svg
scripts/
  update_telemetry.py
.github/workflows/
  update-profile.yml
```

## 2. Refresh telemetry locally

The generator uses Python's standard library only. Python 3.10 or newer is
recommended.

```bash
python scripts/update_telemetry.py --username oovelianoo
```

The command reads public endpoints from the GitHub REST API and rewrites
`assets/telemetry.svg`. A local `GITHUB_TOKEN` or `GH_TOKEN` is optional; using
one simply provides a higher API rate limit.

The panel intentionally reports public repositories, followers, active days,
push events, recent activity, and primary language signals. It does not pretend
to know private contribution data and it does not call a third-party stats image.

## 3. Enable the scheduled workflow

`.github/workflows/update-profile.yml` refreshes telemetry every Monday and can
also be run manually.

1. Push the workflow to the profile repository.
2. Open **Settings → Actions → General**.
3. Under **Workflow permissions**, allow read and write permissions if the
   repository or organization has restricted the default.
4. Open **Actions → Update profile telemetry → Run workflow** for the first
   refresh.

The workflow uses the built-in `GITHUB_TOKEN`; no personal access token is
required. It commits only when `assets/telemetry.svg` has changed.

## 4. Customize the identity

The package keeps copy and rendering intentionally easy to edit:

| file | change here |
| --- | --- |
| `README.md` | positioning, product descriptions, build log, and contact links |
| `assets/hero.svg` | name, title, hero labels, palette, and intro motion |
| `assets/whoami.svg` | founder statement and cross-disciplinary roles |
| `assets/systems.svg` | product names, descriptions, status labels, and progress lines |
| `assets/stack.svg` | toolchain labels and discipline groupings |
| `assets/footer.svg` | closing line and system status |
| `scripts/update_telemetry.py` | telemetry fields, colors, and API-derived layout |
| `.github/workflows/update-profile.yml` | schedule, username, and workflow permissions |

The safest order is to change the visible copy in `README.md` first, then edit
the matching SVG text nodes. Keep the `viewBox` unchanged if you only need to
change labels; that preserves the responsive layout.

## 5. Verify before publishing

Run these checks from the package root:

```bash
python -m py_compile scripts/update_telemetry.py
python scripts/update_telemetry.py --username oovelianoo
```

Then check that every local asset referenced by `README.md` exists:

```bash
python - <<'PY'
from pathlib import Path
import re

readme = Path("README.md").read_text(encoding="utf-8")
paths = sorted(set(re.findall(r'(?:src|\]\()="?([^" )]+)', readme)))
for path in paths:
    if path.startswith("./") and path.endswith((".svg", ".md")):
        assert Path(path).exists(), path
print("local README references: OK")
PY
```

If your shell does not provide a heredoc, simply open `README.md` and confirm
that `assets/hero.svg`, `assets/whoami.svg`, `assets/systems.svg`,
`assets/stack.svg`, `assets/telemetry.svg`, `assets/footer.svg`, and
`docs/setup.md` are present.

## Notes on GitHub rendering

- The README uses ordinary Markdown, HTML image tags, and local SVG files.
- There is no JavaScript, embedded iframe, external font, or mandatory stats service.
- SVG motion is deliberately quiet: cursor blink, status pulse, scanline drift,
  and telemetry-bar breathing. The important information remains visible in a
  static render.
- GitHub may cache images for a short time after a commit. Give the profile page
  a moment or open the raw asset URL when checking a fresh telemetry update.
- Before publishing, verify the Telegram URL in `README.md`; it currently uses
  `https://t.me/oovelianoo` as the identity-matching default.
