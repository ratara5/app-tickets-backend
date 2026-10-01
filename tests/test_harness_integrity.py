"""Guards for the agent harness itself: exposure, references, and portability.

The harness is the part of this repository that no test exercises and every agent
depends on. Its failure modes are silent. A skill that exists canonically but is
never exposed is never loaded, and nothing reports it. A standards file that names
a command the harness does not install sends an agent to a command that does not
exist, and the agent either improvises or stops.

These tests read files only. They build nothing, need no database, and run in the
unit tier.

The three properties enforced here are the ones that were violated when this file
was written:

1. **Every canonical artifact is exposed.** `ai-specs/skills/<name>` must be
   reachable from the committed surface (`.opencode/skills/<name>`) as a relative
   symlink, or a fresh clone has no way to load it.
2. **Every reference resolves.** A command or skill named in a standards document
   or an OpenSpec artifact must exist. `docs/base-standards.md` instructed agents to
   run `opsx:continue` and `opsx:ff` for years of this project's life while the
   committed surface contained neither, because the OpenSpec CLI only emits the
   workflows its *machine-global* config lists and a default install lists five.
3. **Nothing is exposed through an untracked path.** `.claude_example/` and
   `openspec_example/` are excluded by `.gitignore`, so a symlink placed there
   never reaches the repository and cannot survive a clone.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_SPECS = REPO_ROOT / "ai-specs"
OPENCODE_SKILLS = REPO_ROOT / ".opencode" / "skills"
OPENCODE_COMMANDS = REPO_ROOT / ".opencode" / "commands"
OPENCODE_AGENTS = REPO_ROOT / ".opencode" / "agent"
GITIGNORE = REPO_ROOT / ".gitignore"

# Folders gitignore excludes, so nothing inside them reaches the repository. A
# symlink pointing here is dangling on every other machine.
UNTRACKED_SURFACES = (".claude_example", "openspec_example")

# Vendor output. The OpenSpec CLI owns these; the harness must not restructure
# them, and the agnosticism guards deliberately do not apply.
VENDOR_SKILL_PREFIX = "openspec-"
VENDOR_COMMAND_PREFIX = "opsx-"


def _git_tracked(path: Path) -> bool:
    """True when git would commit this path. Falls back to the ignore file.

    A fresh clone has no index for untracked files, and `git check-ignore` still
    answers, so the fallback keeps the test meaningful before the first commit.
    """
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True
    return not _git_ignored(path)


def _git_ignored(path: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path.relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
    )
    return result.returncode == 0


# ── 1. Exposure: a canonical skill with no exposure is never loaded ─────────


def _canonical_skills() -> list[Path]:
    return sorted(p for p in (AI_SPECS / "skills").iterdir() if p.is_dir())


def test_canonical_skills_exist() -> None:
    """A vacuous pass is a false pass.

    If the skills folder were empty or moved, every parametrized test below would
    report success while the harness exposed nothing. The count is asserted so a
    rename that breaks discovery fails loudly instead of silently testing nothing.
    """
    skills = _canonical_skills()
    assert skills, f"no skills found under {AI_SPECS / 'skills'}"
    assert len(skills) >= 12, (
        f"only {len(skills)} canonical skills found ({[p.name for p in skills]}); "
        "expected the documented set. A drop means a skill was moved or lost."
    )


@pytest.mark.parametrize(
    "skill", _canonical_skills(), ids=lambda p: p.name
)
def test_canonical_skill_is_exposed_as_a_relative_symlink(skill: Path) -> None:
    """Exposure is a symlink into `ai-specs`, not a copy.

    A copy is the failure this repository already paid for: `docs/deployment-guide.md`
    and the `deploying-backend-vps` skill drifted into being two runbooks, and the
    stale one is the one a human opens. A relative link also survives the repository
    being cloned at a different absolute path, which an absolute link does not.
    """
    link = OPENCODE_SKILLS / skill.name
    assert link.is_symlink(), (
        f"{link.relative_to(REPO_ROOT)} is missing or is not a symlink. A canonical "
        "skill that is not exposed is never loaded, and no failure is reported."
    )
    target = Path(link.readlink())
    assert not target.is_absolute(), (
        f"{link.relative_to(REPO_ROOT)} points at the absolute path {target}. An "
        "absolute symlink breaks on every machine whose checkout lives elsewhere."
    )
    assert target == Path("..") / ".." / "ai-specs" / "skills" / skill.name, (
        f"{link.relative_to(REPO_ROOT)} points at {target}, not at the canonical "
        "location. Canonical source is ai-specs/; see ai-specs/harness-ia.md §4."
    )
    assert link.resolve() == skill.resolve(), (
        f"{link.relative_to(REPO_ROOT)} resolves to {link.resolve()}, which is not "
        f"the canonical {skill.resolve()}"
    )
    assert link.is_dir(), f"{link.relative_to(REPO_ROOT)} is a broken symlink"


def test_no_authored_skill_exists_only_as_a_copy() -> None:
    """A real directory where a symlink belongs means a copy was pasted.

    The vendor skills are real directories, written by the CLI, and are excluded by
    name. Everything else must be a link, or there are two sources of truth.
    """
    copies = [
        path.name
        for path in sorted(OPENCODE_SKILLS.iterdir())
        if not path.is_symlink() and not path.name.startswith(VENDOR_SKILL_PREFIX)
    ]
    assert not copies, (
        f".opencode/skills/{copies} are real directories, not symlinks into "
        "ai-specs/skills/. A copy diverges silently; the canonical file is edited "
        "and the copy keeps the old text."
    )


def test_nothing_authored_under_ai_specs_is_exposed_via_an_untracked_folder() -> None:
    """`.claude_example/` and `openspec_example/` are gitignored.

    `docs/base-standards.md` §5 used to instruct that new artifacts be exposed
    through `.claude_example`, which cannot satisfy that instruction on a machine
    that is not this one. This guard fails if that instruction is ever reintroduced,
    so the contradiction is caught rather than inherited.
    """
    # A gitignore pattern is matched by suffix, so `**/.claude_example/` and
    # `.claude_example` both mean the same folder. Compare on the final path
    # component, which is what the assertion is about.
    ignored_names = {
        line.strip().rstrip("/").split("/")[-1]
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for surface in UNTRACKED_SURFACES:
        assert surface in ignored_names, (
            f"{surface} is expected to be gitignored. If it was un-ignored on "
            "purpose, this guard and base-standards.md §5 both need updating: an "
            "un-ignored surface would be a real second harness surface."
        )


def test_vendor_surface_is_not_adopted_into_ai_specs() -> None:
    """The OpenSpec CLI owns its `openspec-*` skills and `opsx-*` commands.

    Canonicalising them would put this repository in a fight with the tool on every
    upgrade, and would lose the per-agent command syntax the tool emits. This is a
    policy guard, not a style preference.
    """
    vendor_in_canonical = [
        path.name
        for path in _canonical_skills()
        if path.name.startswith(VENDOR_SKILL_PREFIX)
    ]
    assert not vendor_in_canonical, (
        f"ai-specs/skills/{vendor_in_canonical} are OpenSpec CLI output and must not "
        "be canonicalised here. Reinstall them; do not restructure. See "
        "ai-specs/harness-ia.md §5."
    )


# ── 2. References: a command named in standards must exist ──────────────────

# Command references appear in several documented syntaxes, because each harness
# surface spells them differently: Claude uses `/opsx:apply`, opencode uses
# `/opsx-apply`, and prose may write either with or without the slash.
_COMMAND_REFERENCE = re.compile(r"/?opsx[:-]([a-z][a-z-]*)")
_DOCUMENTS = (
    "docs/base-standards.md",
    "ai-specs/harness-ia.md",
    "openspec/config.yaml",
    "README.md",
)


def _installed_commands() -> set[str]:
    return {path.stem for path in OPENCODE_COMMANDS.glob("*.md")}


def test_commands_are_installed() -> None:
    """Same reason as the skill count: a discovery failure must not read as a pass."""
    commands = _installed_commands()
    assert commands, f"no commands found under {OPENCODE_COMMANDS}"
    assert commands, "the committed command surface is empty"


@pytest.mark.parametrize("document", _DOCUMENTS)
def test_every_command_referenced_in_a_document_is_installed(document: str) -> None:
    """The defect this exists for.

    `docs/base-standards.md` §6 told agents to run `opsx:continue` or `opsx:ff` when
    a change needed artifact regeneration. Neither command existed in the committed
    surface, because the OpenSpec CLI emits only the workflows named in the
    *machine-global* config, and the default profile lists five. An agent following
    the standards reached a step it could not perform, and the standards were the
    authority it was required to obey.

    The failure is invisible to a reader and to every other test: the document is
    well-formed, and the command set is whatever the tool last wrote.
    """
    path = REPO_ROOT / document
    assert path.exists(), f"{document} is referenced by this guard but does not exist"
    installed = _installed_commands()
    referenced = {
        f"opsx-{match}"
        for match in _COMMAND_REFERENCE.findall(path.read_text(encoding="utf-8"))
    }
    missing = sorted(name for name in referenced if name not in installed)
    assert not missing, (
        f"{document} references {missing}, which are not installed in "
        f".opencode/commands/ (installed: {sorted(installed)}). Either install the "
        "workflow or correct the document. To install: add the workflow name to the "
        "`workflows` list in the OpenSpec global config and run "
        "`openspec update --force`. See ai-specs/harness-ia.md §5."
    )


def test_workflows_required_by_the_standards_are_pinned_in_the_repository() -> None:
    """The committed surface is not reproducible from this repository alone.

    The OpenSpec CLI decides which commands to write from a machine-global config
    file. So the six commands `docs/base-standards.md` depends on exist here only
    because of an edit to `~/.config/openspec/config.json`, and the next person who
    runs `openspec update --force` on a default install has them deleted while the
    standards still name them.

    Recording the requirement in the repository is what makes the surface
    reproducible. The value is asserted rather than documented, so a tool upgrade
    that changes the workflow names fails here instead of in an agent session.
    """
    declared = REPO_ROOT / ".opencode" / "workflows.txt"
    assert declared.exists(), (
        ".opencode/workflows.txt is missing. It records which OpenSpec workflows this "
        "repository depends on, so `openspec update --force` can be reproduced on a "
        "machine that has never run this project. Without it the committed command "
        "surface silently shrinks to the tool's default five."
    )
    # The file records bare workflow names (`continue`); the installed files are
    # named after the command surface (`opsx-continue.md`).
    recorded = {
        f"opsx-{line.strip()}"
        for line in declared.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    installed = _installed_commands()
    assert recorded <= installed, (
        f".opencode/workflows.txt declares {sorted(recorded - installed)}, which are "
        f"not installed. Run `openspec update --force` after adding them to the "
        "OpenSpec global config."
    )
    referenced_by_standards: set[str] = set()
    for document in _DOCUMENTS:
        path = REPO_ROOT / document
        if path.exists():
            referenced_by_standards |= {
                f"opsx-{match}"
                for match in _COMMAND_REFERENCE.findall(path.read_text(encoding="utf-8"))
            }
    undeclared = sorted(referenced_by_standards - recorded)
    assert not undeclared, (
        f"standards reference {undeclared}, which .opencode/workflows.txt does not "
        "record. A command that is used but not recorded is one a fresh clone loses."
    )


# ── 3. Agents: a persona that is not exposed is never adopted ───────────────


def test_canonical_agents_are_exposed_to_the_committed_surface() -> None:
    """`ai-specs/agents/` is the canonical home of the personas.

    They were exposed only into `.claude_example/agents/`, which `.gitignore`
    excludes, so on a fresh clone no agent could be adopted at all and nothing
    reported it. `docs/frontend-standards.md` instructs the frontend persona to be
    adopted for a project that cannot see it.
    """
    agents = sorted((AI_SPECS / "agents").glob("*.md"))
    assert agents, f"no agents found under {AI_SPECS / 'agents'}"
    assert OPENCODE_AGENTS.is_dir(), (
        f"{OPENCODE_AGENTS.relative_to(REPO_ROOT)} does not exist. The personas in "
        "ai-specs/agents/ are unreachable from the committed surface, so an agent "
        "cannot adopt one."
    )
    missing = [agent.name for agent in agents if not (OPENCODE_AGENTS / agent.name).exists()]
    assert not missing, (
        f"agents {missing} are not exposed in .opencode/agent/. Expose each with a "
        "relative symlink; see ai-specs/harness-ia.md §4."
    )
    for agent in agents:
        link = OPENCODE_AGENTS / agent.name
        assert link.is_symlink(), (
            f".opencode/agent/{agent.name} is not a symlink into ai-specs/agents/; "
            "a copy is a second persona that drifts"
        )
        assert not Path(link.readlink()).is_absolute(), (
            f".opencode/agent/{agent.name} uses an absolute symlink target and will "
            "break on a checkout at a different path"
        )


# ── 4. The declared tree is a claim ─────────────────────────────────────────


def test_declared_ai_specs_tree_matches_the_filesystem() -> None:
    """`ai_specs_structure` in `openspec/config.yaml` declares the canonical tree.

    `docs/base-standards.md` §5 states the rule this enforces: if the declaration
    disagrees with the filesystem, the declaration is the defect. The block is
    free text, so nothing else notices when a skill is added and not declared, and
    the next agent reads a tree that does not exist.
    """
    config = (REPO_ROOT / "openspec" / "config.yaml").read_text(encoding="utf-8")
    assert "ai_specs_structure" in config, (
        "openspec/config.yaml has no ai_specs_structure block; docs/base-standards.md "
        "§5 relies on it as the declaration of the canonical tree"
    )
    block = config.split("ai_specs_structure", 1)[1]
    block = block.split("\npaths:", 1)[0]
    for directory in (AI_SPECS / "skills", AI_SPECS / "agents", AI_SPECS / "scripts"):
        assert directory.name + "/" in block, (
            f"ai_specs_structure does not declare {directory.name}/, which exists. "
            "The declared tree is a claim; an undeclared folder is invisible to the "
            "next agent."
        )
    for skill in _canonical_skills():
        assert skill.name in block, (
            f"ai_specs_structure does not declare the skill {skill.name!r}. Fix the "
            "declaration, not the tree."
        )
    for file_path in ("harness-ia.md", "specboot-instructions.md"):
        assert file_path in block, (
            f"ai_specs_structure does not declare {file_path!r}"
        )


# ── 5. Skills are loadable documents, not stubs ──────────────────────────────


@pytest.mark.parametrize("skill", _canonical_skills(), ids=lambda p: p.name)
def test_skill_has_frontmatter_with_a_triggering_description(skill: Path) -> None:
    """A skill whose description does not state its trigger is never loaded.

    `code-auditing` shipped with the description "Task-focused project skill." A
    harness loads a skill by matching that description against the request, and this
    one matches nothing, so a skill carrying a full audit methodology was invisible
    to the agent that needed it. The rule is written in this repository's own
    `writing-skills` skill, and nothing enforced it.
    """
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill.name}/SKILL.md has no YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    assert re.search(r"^name:\s*\S", frontmatter, re.MULTILINE), (
        f"{skill.name}/SKILL.md frontmatter has no name"
    )
    description_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    assert description_match, f"{skill.name}/SKILL.md frontmatter has no description"
    description = description_match.group(1).strip().strip("\"'")
    assert len(description) >= 40, (
        f"{skill.name} description is {len(description)} characters: {description!r}. "
        "It is too short to state a trigger. State the conditions under which the "
        "skill applies, not what the skill does; see writing-skills CSO."
    )
    assert not description.lower().startswith("use this skill"), (
        f"{skill.name} description restates the workflow instead of its trigger"
    )
    # A placeholder is the specific failure: it parses as a description and matches
    # nothing at load time.
    for placeholder in ("task-focused", "todo", "tbd", "description here", "a skill"):
        assert placeholder not in description.lower(), (
            f"{skill.name} description contains the placeholder {placeholder!r}: "
            f"{description!r}. A placeholder makes the skill untriggerable."
        )


@pytest.mark.parametrize("skill", _canonical_skills(), ids=lambda p: p.name)
def test_skill_body_is_a_procedure_not_a_pointer(skill: Path) -> None:
    """A skill that delegates its whole body to another document does nothing.

    `update-docs` was thirteen lines whose entire instruction was "Use
    `docs/documentation-standards.md` to update whatever documentation is needed".
    An agent that loads it learns nothing it could not get by reading the repository
    layout, and the mandatory documentation step in `docs/base-standards.md` §6 then
    passes as satisfied.
    """
    body = (skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
    lines = [line for line in body.splitlines() if line.strip()]
    assert len(lines) >= 20, (
        f"{skill.name}/SKILL.md has {len(lines)} non-empty body lines. A skill that "
        "is a pointer is not a skill: it cannot be followed without the reader "
        "already knowing what to do."
    )
    headings = re.findall(r"^#{2,3}\s+\S", body, re.MULTILINE)
    assert len(headings) >= 2, (
        f"{skill.name}/SKILL.md has {len(headings)} section headings. A procedure "
        "needs at least a trigger section and a step section to be followable."
    )


@pytest.mark.parametrize("skill", _canonical_skills(), ids=lambda p: p.name)
def test_skill_references_resolve(skill: Path) -> None:
    """Every `references/*.md` and relative path a skill names must exist.

    A skill that points at a file which is not there fails at exactly the moment it
    is most expensive: mid-deployment, when the reader has already committed to the
    procedure.

    Three kinds of backticked text are not repo-relative paths and are skipped:
    a glob (`*/SKILL.md`) describes a set the reader expands, a path under another
    tool's namespace (`@skills/...`, `.claude/...`) is that tool's own convention
    and is resolved by that tool, and a bare filename with no directory component
    is prose rather than a reference.
    """
    root = REPO_ROOT
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    candidates = set(re.findall(r"`([^`\s]+\.md)`", text))
    for reference in sorted(candidates):
        if reference.startswith(("http://", "https://")):
            continue
        if any(token in reference for token in ("*", "?", "@")):
            continue
        if reference.startswith(UNTRACKED_SURFACES + (".claude/", ".cursor/")):
            continue
        if "/" not in reference:
            continue
        resolved = (skill / reference).resolve()
        if not resolved.exists():
            alt = (root / reference.lstrip("./")).resolve()
            assert alt.exists(), (
                f"{skill.name}/SKILL.md references {reference!r}, which does not exist "
                f"at {resolved} or {alt}. A dangling reference fails mid-procedure."
            )
