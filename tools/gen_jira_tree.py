"""Regenerate the browsable Jira issue tree from JIRA_ACTIVE_ROADMAP.csv.

The CSV is the source of truth and the Jira import artifact. This script rebuilds
docs/project-review/jira/ from it: one file per issue, with the Epic -> Story/Task
-> Sub-task hierarchy expressed as directories.

It deletes and recreates that directory, so any hand-edit to the tree is lost.
Edit the CSV, then re-run:

    python tools/gen_jira_tree.py
"""

import csv
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "docs", "project-review", "JIRA_ACTIVE_ROADMAP.csv")
OUT = os.path.join(REPO, "docs", "project-review", "jira")

STOP = {"and", "the", "of", "for", "to", "a", "an", "on", "in", "with"}
ID_RE = re.compile(r"^(E|ST|SP|S|T|B)\d+")


def slug(text, maxlen=55):
    """Build a readable directory/file stem from an issue summary."""
    words = re.sub(r"[^a-z0-9\s-]", " ", text.lower()).split()
    words = [w for w in words if w not in STOP]
    out = ""
    for word in words:
        if out and len(out) + 1 + len(word) > maxlen:
            break
        out = f"{out}-{word}" if out else word
    return out or "issue"


with open(SRC, newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

by_id = {r["Issue ID"]: r for r in rows}
kids = {r["Issue ID"]: [] for r in rows}
epic_kids = {r["Issue ID"]: [] for r in rows}
for row_ in rows:
    parent, epic_, type_ = row_["Parent ID"], row_["Epic ID"], row_["Issue Type"]
    if parent:
        kids[parent].append(row_["Issue ID"])
    elif type_ != "Epic" and epic_:
        epic_kids[epic_].append(row_["Issue ID"])


def is_container(issue_id):
    """True when the issue owns sub-tasks and therefore needs its own directory."""
    return len(kids[issue_id]) > 0


def stem(r):
    return f'{r["Issue ID"]}-{slug(r["Summary"])}'


paths = {}
for row_ in rows:
    if row_["Issue Type"] != "Epic":
        continue
    epic_dir = stem(row_)
    paths[row_["Issue ID"]] = f"{epic_dir}/_epic.md"
    for child_id in epic_kids[row_["Issue ID"]]:
        child = by_id[child_id]
        if is_container(child_id):
            child_dir = f"{epic_dir}/{stem(child)}"
            kind = child["Issue Type"].lower().replace("-", "")
            paths[child_id] = f"{child_dir}/_{kind}.md"
            for sub_id in kids[child_id]:
                paths[sub_id] = f"{child_dir}/{stem(by_id[sub_id])}.md"
        else:
            paths[child_id] = f"{epic_dir}/{stem(child)}.md"

unplaced = [r["Issue ID"] for r in rows if r["Issue ID"] not in paths]
if unplaced:
    sys.exit(f"FATAL: unplaced issues {unplaced}")


def rel(frm, to):
    """Relative markdown link from one issue's file to another's."""
    path = os.path.relpath(paths[to], os.path.dirname(paths[frm])).replace("\\", "/")
    return path if path.startswith(".") else "./" + path


def split_deps(cell):
    """Separate resolvable issue IDs from free-text prerequisites."""
    deps, prereq = [], []
    for token in (t.strip() for t in cell.split(";")):
        if not token:
            continue
        if token in by_id:
            deps.append((token, None))
            continue
        match = ID_RE.match(token)
        if match and match.group(0) in by_id:
            note = token[match.end():].strip(" -,") or None
            deps.append((match.group(0), note))
        else:
            prereq.append(token)
    return deps, prereq


def yaml_list(items):
    return "[" + ", ".join(items) + "]" if items else "[]"


def render(r):
    """Render one issue as a markdown file with YAML frontmatter."""
    issue_id, type_ = r["Issue ID"], r["Issue Type"]
    deps, prereq = split_deps(r["Depends On"])
    labels = [x.strip() for x in r["Labels"].split(",") if x.strip()]
    pts = r["Story Points"]

    meta = [f'**{type_}** · {r["Priority"]} · `{r["Status"]}`']
    if pts:
        meta.append(f"{pts} pts")
    meta.append(r["Components"])
    if r["Due Date"]:
        meta.append(f'due {r["Due Date"]}')
    if r["Fix Version"]:
        meta.append(r["Fix Version"])

    out = [
        "---",
        f"id: {issue_id}",
        f"type: {type_}",
        f'summary: "{r["Summary"]}"',
        f'epic: {r["Epic ID"] or "~"}',
        f'parent: {r["Parent ID"] or "~"}',
        f'status: "{r["Status"]}"',
        f'priority: {r["Priority"]}',
        f'story_points: {pts or "~"}',
        f'component: "{r["Components"]}"',
        f"labels: {yaml_list(labels)}",
        f"depends_on: {yaml_list([d for d, _ in deps])}",
        f'assignee: {r["Assignee"] or "~"}',
        f'due_date: {r["Due Date"] or "~"}',
        f'fix_version: {r["Fix Version"] or "~"}',
        f'project_key: {r["Project Key"]}',
        "---",
        "",
        f'# {issue_id} · {r["Summary"]}',
        "",
        " · ".join(meta),
        "",
        r["Description"],
        "",
        "## Acceptance criteria",
        "",
        r["Acceptance Criteria"],
        "",
    ]

    if is_container(issue_id) or (type_ == "Epic" and epic_kids[issue_id]):
        children = epic_kids[issue_id] if type_ == "Epic" else kids[issue_id]
        out += ["## Children", ""]
        for child_id in children:
            child = by_id[child_id]
            out.append(
                f"- [`{child_id}`]({rel(issue_id, child_id)}) · "
                f'{child["Issue Type"]} · `{child["Status"]}` · {child["Summary"]}'
            )
        out.append("")

    if deps:
        out += ["## Depends on", ""]
        for dep, note in deps:
            suffix = f" _({note})_" if note else ""
            out.append(
                f"- [`{dep}`]({rel(issue_id, dep)}) — "
                f'{by_id[dep]["Summary"]}{suffix}'
            )
        out.append("")

    if prereq:
        out += ["## External prerequisites", ""]
        out += [f"- {p}" for p in prereq]
        out.append("")

    if r["Source Reference"]:
        out += ["## Source reference", ""]
        out += [
            f"- `{s.strip()}`"
            for s in r["Source Reference"].split(";")
            if s.strip()
        ]
        out.append("")

    out += [
        "---",
        "",
        "_Generated from `JIRA_ACTIVE_ROADMAP.csv`. That CSV remains the Jira "
        "import artifact; edit it, then regenerate._",
    ]
    return "\n".join(out) + "\n"


if os.path.isdir(OUT):
    shutil.rmtree(OUT)
for row_ in rows:
    dest = os.path.join(OUT, paths[row_["Issue ID"]].replace("/", os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(row_))

print(f"wrote {len(rows)} files")
print(f"dirs  {sum(1 for _, dirnames, _ in os.walk(OUT) for _ in dirnames)}")
