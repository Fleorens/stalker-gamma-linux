#!/usr/bin/env python3
"""Détecte une nouvelle révision amont (Stalker_GAMMA, gamma-launcher).

Utilisé par `.github/workflows/upstream-watch.yml` (job `check-upstream`).

`Grokitach/Stalker_GAMMA` ne publie ni tags ni releases GitHub (vérifié via
l'API : listes vides) — on suit donc le dernier commit de sa branche par
défaut. `Mord3rca/gamma-launcher` publie de vraies GitHub Releases (c'est ce
que `pyproject.toml` épingle) — on suit `releases/latest`.

Écrit les sorties `changed`/`gamma_changed`/`gamma_sha`/`launcher_changed`/
`launcher_tag`/`launcher_sha`/`summary` dans `$GITHUB_OUTPUT`, et le nouvel
état (à committer seulement si le job d'intégration qui suit réussit) dans
`--new-state-file`.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "https://api.github.com"


def _api_get(path: str, token: str | None) -> Any:
    request = urllib.request.Request(f"{API_BASE}{path}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def latest_gamma_sha(repo: str, ref: str, token: str | None) -> str:
    data = _api_get(f"/repos/{repo}/commits/{ref}", token)
    sha: str = data["sha"]
    return sha


def latest_launcher_release(repo: str, token: str | None) -> tuple[str, str]:
    release = _api_get(f"/repos/{repo}/releases/latest", token)
    tag: str = release["tag_name"]
    tags = _api_get(f"/repos/{repo}/tags", token)
    for entry in tags:
        if entry["name"] == tag:
            sha: str = entry["commit"]["sha"]
            return tag, sha
    raise RuntimeError(f"tag {tag!r} introuvable dans /repos/{repo}/tags")


def load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.is_file():
        return {}
    return json.loads(state_file.read_text())  # type: ignore[no-any-return]


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    line = f"{name}={value}\n"
    if output_path is None:
        print(line, end="")
        return
    with open(output_path, "a") as handle:
        handle.write(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--new-state-file", type=Path, required=True)
    parser.add_argument("--gamma-repo", default="Grokitach/Stalker_GAMMA")
    parser.add_argument("--gamma-ref", default="main")
    parser.add_argument("--launcher-repo", default="Mord3rca/gamma-launcher")
    parser.add_argument("--force", action="store_true", help="Considère toujours changed=true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    old_state = load_state(args.state_file)
    gamma_sha = latest_gamma_sha(args.gamma_repo, args.gamma_ref, token)
    launcher_tag, launcher_sha = latest_launcher_release(args.launcher_repo, token)

    old_gamma_sha = old_state.get("stalker_gamma", {}).get("sha")
    old_launcher_sha = old_state.get("gamma_launcher", {}).get("sha")

    gamma_changed = gamma_sha != old_gamma_sha
    launcher_changed = launcher_sha != old_launcher_sha
    changed = gamma_changed or launcher_changed or args.force

    new_state = {
        "stalker_gamma": {"ref": args.gamma_ref, "sha": gamma_sha},
        "gamma_launcher": {"tag": launcher_tag, "sha": launcher_sha},
    }
    args.new_state_file.parent.mkdir(parents=True, exist_ok=True)
    args.new_state_file.write_text(json.dumps(new_state, indent=2) + "\n")

    summary_parts = []
    if gamma_changed:
        summary_parts.append(
            f"Grokitach/Stalker_GAMMA: {old_gamma_sha or '(aucun état précédent)'} -> {gamma_sha}"
        )
    if launcher_changed:
        summary_parts.append(
            f"Mord3rca/gamma-launcher: {old_launcher_sha or '(aucun état précédent)'} "
            f"-> {launcher_tag} ({launcher_sha})"
        )
    if not summary_parts:
        summary_parts.append("Aucun changement amont détecté.")
    summary = " ; ".join(summary_parts)

    write_output("changed", "true" if changed else "false")
    write_output("gamma_changed", "true" if gamma_changed else "false")
    write_output("gamma_sha", gamma_sha)
    write_output("launcher_changed", "true" if launcher_changed else "false")
    write_output("launcher_tag", launcher_tag)
    write_output("launcher_sha", launcher_sha)
    write_output("summary", summary)

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
