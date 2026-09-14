"""Regenerate the browsable Jira issue tree from JIRA_ACTIVE_ROADMAP.csv.

The CSV is the source of truth and the Jira import artifact. This script rebuilds
docs/project-review/jira/ from it: one file per issue, with the Epic -> Story/Task
-> Sub-task hierarchy expressed as directories.

It deletes and recreates that directory, so any hand-edit to the tree is lost.
Edit the CSV, then re-run:

    python tools/gen_jira_tree.py
"""

import csv, os, re, sys, shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(REPO, "docs", "project-review", "JIRA_ACTIVE_ROADMAP.csv")
OUT  = os.path.join(REPO, "docs", "project-review", "jira")

STOP = {"and","the","of","for","to","a","an","on","in","with"}
ID_RE = re.compile(r"^(E|ST|SP|S|T|B)\d+")

def slug(text, maxlen=55):
    w = re.sub(r"[^a-z0-9\s-]", " ", text.lower()).split()
    w = [x for x in w if x not in STOP]
    s = ""
    for x in w:
        if s and len(s) + 1 + len(x) > maxlen: break
        s = f"{s}-{x}" if s else x
    return s or "issue"

with open(SRC, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

by_id = {r["Issue ID"]: r for r in rows}
kids  = {r["Issue ID"]: [] for r in rows}
epic_kids = {r["Issue ID"]: [] for r in rows}
for r in rows:
    p, e, t = r["Parent ID"], r["Epic ID"], r["Issue Type"]
    if p:
        kids[p].append(r["Issue ID"])
    elif t != "Epic" and e:
        epic_kids[e].append(r["Issue ID"])

def is_container(i): return len(kids[i]) > 0

paths = {}
def stem(r): return f'{r["Issue ID"]}-{slug(r["Summary"])}'
for r in rows:
    if r["Issue Type"] != "Epic": continue
    ed = stem(r); paths[r["Issue ID"]] = f"{ed}/_epic.md"
    for cid in epic_kids[r["Issue ID"]]:
        c = by_id[cid]
        if is_container(cid):
            cd = f"{ed}/{stem(c)}"
            paths[cid] = f"{cd}/_{c['Issue Type'].lower().replace('-','')}.md"
            for sid in kids[cid]:
                paths[sid] = f"{cd}/{stem(by_id[sid])}.md"
        else:
            paths[cid] = f"{ed}/{stem(c)}.md"

missing = [r["Issue ID"] for r in rows if r["Issue ID"] not in paths]
if missing:
    sys.exit(f"FATAL: unplaced issues {missing}")

def rel(frm, to):
    p = os.path.relpath(paths[to], os.path.dirname(paths[frm])).replace("\\", "/")
    return p if p.startswith(".") else "./" + p

def split_deps(cell):
    deps, prereq = [], []
    for tok in (t.strip() for t in cell.split(";")):
        if not tok: continue
        if tok in by_id: deps.append((tok, None)); continue
        m = ID_RE.match(tok)
        if m and m.group(0) in by_id:
            deps.append((m.group(0), tok[m.end():].strip(" -,") or None))
        else:
            prereq.append(tok)
    return deps, prereq

def yl(items): return "[" + ", ".join(items) + "]" if items else "[]"

def render(r):
    i, t = r["Issue ID"], r["Issue Type"]
    deps, prereq = split_deps(r["Depends On"])
    labels = [x.strip() for x in r["Labels"].split(",") if x.strip()]
    pts = r["Story Points"]
    meta = [f'**{t}** · {r["Priority"]} · `{r["Status"]}`']
    if pts: meta.append(f'{pts} pts')
    meta.append(r["Components"])
    if r["Due Date"]: meta.append(f'due {r["Due Date"]}')
    if r["Fix Version"]: meta.append(r["Fix Version"])

    fm = [
        "---",
        f'id: {i}',
        f'type: {t}',
        f'summary: "{r["Summary"]}"',
        f'epic: {r["Epic ID"] or "~"}',
        f'parent: {r["Parent ID"] or "~"}',
        f'status: "{r["Status"]}"',
        f'priority: {r["Priority"]}',
        f'story_points: {pts or "~"}',
        f'component: "{r["Components"]}"',
        f'labels: {yl(labels)}',
        f'depends_on: {yl([d for d,_ in deps])}',
        f'assignee: {r["Assignee"] or "~"}',
        f'due_date: {r["Due Date"] or "~"}',
        f'fix_version: {r["Fix Version"] or "~"}',
        f'project_key: {r["Project Key"]}',
        "---", "",
        f'# {i} · {r["Summary"]}', "",
        " · ".join(meta), "",
        r["Description"], "",
        "## Acceptance criteria", "", r["Acceptance Criteria"], "",
    ]
    if is_container(i) or (t == "Epic" and epic_kids[i]):
        children = epic_kids[i] if t == "Epic" else kids[i]
        fm += ["## Children", ""]
        for cid in children:
            c = by_id[cid]
            fm.append(f'- [`{cid}`]({rel(i, cid)}) · {c["Issue Type"]} · '
                      f'`{c["Status"]}` · {c["Summary"]}')
        fm.append("")
    if deps:
        fm += ["## Depends on", ""]
        for d, note in deps:
            fm.append(f'- [`{d}`]({rel(i, d)}) — {by_id[d]["Summary"]}'
                      + (f' _({note})_' if note else ""))
        fm.append("")
    if prereq:
        fm += ["## External prerequisites", ""] + [f"- {p}" for p in prereq] + [""]
    if r["Source Reference"]:
        fm += ["## Source reference", ""]
        fm += [f"- `{s.strip()}`" for s in r["Source Reference"].split(";") if s.strip()]
        fm.append("")
    fm += ["---", "", "_Generated from `JIRA_ACTIVE_ROADMAP.csv`. "
           "That CSV remains the Jira import artifact; edit it, then regenerate._"]
    return "\n".join(fm) + "\n"

if os.path.isdir(OUT): shutil.rmtree(OUT)
for r in rows:
    dest = os.path.join(OUT, paths[r["Issue ID"]].replace("/", os.sep))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(r))

print(f"wrote {len(rows)} files")
print(f"dirs  {sum(1 for _,d,_ in os.walk(OUT) for _ in d)}")
