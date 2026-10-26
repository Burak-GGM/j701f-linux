# Maintaining this wiki

## The rule

**When the project changes, the wiki changes in the same piece of work.** A new driver, a new script on the phone, a different kernel version, a newly found pitfall — each belongs here before the work is called finished. This applies to everyone who touches the project, people and AI assistants alike.

The wiki is written for people. It should stay readable by someone who was not there: explain what a thing is before saying what was done to it, prefer a sentence to a list of keywords, and leave out the blow-by-blow.

## What goes where

| Kind of change | Update |
| --- | --- |
| Hardware starts or stops working | [Hardware and status](reference/hardware.md), and the table on the [home page](index.md) if it is a headline item |
| New or changed kernel patch, configuration option, device-tree layer | [Kernel, patches, device tree](reference/kernel.md) |
| New or changed file installed on the phone, package choice, control | [Userspace](reference/userspace.md) |
| Boot flow, slots, a new safety mechanism | [Boot chain and safety nets](reference/boot-chain.md) |
| New tool or changed workflow | [Tools and workflow](reference/tools.md) |
| A problem that took real time to understand | [Lessons and pitfalls](reference/lessons.md) |
| A whole new area of work (modem, camera, display driver…) | A new chapter in *The journey*, added to `mkdocs.yml` |

*The journey* chapters are history. Extend them when a stage is finished; do not rewrite earlier chapters to match the present — that is what the reference pages are for.

## Two languages

Every page exists twice: `page.md` in English, which is the primary text, and `page.tr.md` in Turkish. Change both. If only one can be updated, update the English page and say so at the top of the Turkish one, so nobody takes a stale translation for the truth.

Commands, file names, register names and kernel terms stay as they are in both languages.

## More than one person at work

When two people or assistants work on the project at the same time, they share the phone and the kernel build tree through `tools/coord.sh`: a lock for each shared resource, a board that says who is doing what, and a message inbox for questions. The rules are in `docs/coordination/README.md`; that folder stays on the working computer and is not part of the public repository. Claim a wiki page on the board before a larger edit, so two edits do not collide.

## Relation to `docs/`

`docs/` holds the working notes: long, dated, detailed, written while the work was happening. `docs/j701f-mainline.md` in particular is the complete log, and passages added by a particular assistant are marked with who wrote them. Those notes are the source; the wiki is the digest. When they disagree, check the phone and fix both.

## The public repository

The project is published on GitHub under GPL-2.0-only (since 2026-10-26). Before anything is pushed, check that it carries no firmware, no partition backups, no passwords or keys and no home-network details: those stay in ignored paths (`build/`, `original/`, `tools/downloads/`, `docs/coordination/`, `.phone-ip`). IP addresses in the notes use `192.168.1.0/24`.

Every push to `main` runs the unit tests and `mkdocs build --strict` on GitHub; when both pass, the built wiki is published to <https://burak-ggm.github.io/j701f-linux/> (`.github/workflows/ci.yml`). A page that fails the strict build therefore never reaches the public site.

## Building the wiki

```sh
python3 -m venv build/wiki-venv
build/wiki-venv/bin/pip install -r wiki/requirements.txt

# live preview at http://127.0.0.1:8000
build/wiki-venv/bin/mkdocs serve

# static site in build/wiki-site/
build/wiki-venv/bin/mkdocs build --strict
```

`--strict` turns broken links and missing pages into errors. Run it before finishing a change.

## Style

- Say what is true now, and how it is known. "Verified on the phone", "written but untested" and "not started" are three different states; keep them apart.
- Give numbers with units.
- Do not record secrets: no passwords, no Wi-Fi keys, no serial numbers, no real MAC addresses.
- Keep pages short enough to read in one sitting. If a page grows past that, split it.
