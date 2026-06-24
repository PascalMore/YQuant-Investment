#!/usr/bin/env python3
"""
Multi-platform Agent Profile Generator

Reads YQuant project Markdown files (AGENTS.md, CLAUDE.md, HEARTBEAT.md, etc.)
and generates platform-specific agent profiles.  First adapter: Hermes.

Usage:
    python generate_agent_profile.py --platform hermes --profile yquant --source-root . --output-dir dist/
    python generate_agent_profile.py --platform hermes --profile yquant --source-root . --apply --target-root ~/.hermes
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

HERMES_JOB_SCRIPT_MAP = {
    "每日全球市场日报": "daily-global-market-report.sh",
    "每日SmartMoney数据报告发送": "daily-smartmoney-data-report.sh",
    "每日Argus数据批处理": "daily-argus-batch-processing.sh",
    "每周酒店价格抓取": "weekly-hotel-price-scraper.sh",
    "每日自动代码提交": "daily-auto-code-commit.sh",
}

HERMES_REQUIRED_SOURCE_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "HEARTBEAT.md",
    "IDENTITY.md",
    "SOUL.md",
    "TOOLS.md",
    "USER.md",
]

HERMES_OPTIONAL_SOURCE_FILES = [
    "MEMORY.md",
    "skills/data/portfolio/config.py",
]

HERMES_OUTPUT_STRUCTURE = [
    "profile.yaml",
    "config.yaml",
    "SOUL.md",
    "memories/USER.md",
    "memories/MEMORY.md",
    "skills/skills_manifest.json",
    "cron/jobs.json",
    "migration/generated-manifest.json",
]


@dataclass
class ScheduledJob:
    name: str
    schedule: str
    enabled: bool
    schedule_type: str = "cron"
    source: str = "HEARTBEAT.md"
    script: Optional[str] = None
    no_agent: bool = True
    deliver: str = "local"


@dataclass
class SkillEntry:
    id: str
    name: str
    path: str
    description: Optional[str] = None


@dataclass
class AgentProfileModel:
    profile: str
    platform: str
    source_root: Path
    soul: Optional[str] = None
    user_memory: Optional[str] = None
    project_memory: Optional[str] = None
    agents_md: Optional[str] = None
    claude_md: Optional[str] = None
    identity_md: Optional[str] = None
    tools_md: Optional[str] = None
    heartbeat_md: Optional[str] = None
    scheduled_jobs: list[ScheduledJob] = field(default_factory=list)
    skills: list[SkillEntry] = field(default_factory=list)
    source_files_read: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# F-001: Source reader
# ---------------------------------------------------------------------------

def read_source_file(root: Path, filename: str) -> Optional[str]:
    """Read a source file, returning None if it doesn't exist."""
    path = root / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def load_profile_model(args: argparse.Namespace) -> AgentProfileModel:
    """F-001: Parse all source Markdown files into a common model."""
    root = Path(args.source_root).resolve()
    model = AgentProfileModel(
        profile=args.profile,
        platform=args.platform,
        source_root=root,
    )

    # Required sources
    for fname in HERMES_REQUIRED_SOURCE_FILES:
        content = read_source_file(root, fname)
        if content:
            model.source_files_read.append(fname)
            if fname == "SOUL.md":
                model.soul = content
            elif fname == "AGENTS.md":
                model.agents_md = content
            elif fname == "CLAUDE.md":
                model.claude_md = content
            elif fname == "IDENTITY.md":
                model.identity_md = content
            elif fname == "TOOLS.md":
                model.tools_md = content
            elif fname == "HEARTBEAT.md":
                model.heartbeat_md = content

    # Optional sources
    for fname in HERMES_OPTIONAL_SOURCE_FILES:
        content = read_source_file(root, fname)
        if content:
            model.source_files_read.append(fname)
            if fname == "MEMORY.md":
                # MEMORY.md is project-level memory, goes to memories/MEMORY.md
                model.project_memory = content

    # Read USER.md separately
    user_md = read_source_file(root, "USER.md")
    if user_md:
        if "USER.md" not in model.source_files_read:
            model.source_files_read.append("USER.md")
        model.user_memory = user_md

    # F-002: parse heartbeat
    if model.heartbeat_md:
        model.scheduled_jobs = parse_heartbeat_schedule(model.heartbeat_md)

    # F-004: scan skills
    model.skills = scan_skills(args.source_root)

    return model


# ---------------------------------------------------------------------------
# F-002: HEARTBEAT.md cron parser
# ---------------------------------------------------------------------------

_CRON_RE = re.compile(r"^([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s*$")


def _validate_cron(expr: str) -> bool:
    """Check basic 5-field cron structure: minute hour dom month dow."""
    # Strip backticks that may wrap the expression
    expr = expr.strip().strip("`").strip()
    m = _CRON_RE.match(expr)
    if not m:
        return False
    minute, hour, dom, month, dow = m.groups()

    def valid_field(val: str, lo: int, hi: int) -> bool:
        if val == "*":
            return True
        for part in val.split(","):
            for segment in part.split("/"):
                if segment == "*":
                    continue
                if "-" in segment:
                    start, end = segment.split("-", 1)
                    try:
                        s, e = int(start), int(end)
                        if s < lo or e > hi or s > e:
                            return False
                    except ValueError:
                        return False
                else:
                    try:
                        v = int(segment)
                        if v < lo or v > hi:
                            return False
                    except ValueError:
                        return False
        return True

    return (
        valid_field(minute, 0, 59)
        and valid_field(hour, 0, 23)
        and valid_field(dom, 1, 31)
        and valid_field(month, 1, 12)
        and valid_field(dow, 0, 7)
    )


def parse_heartbeat_schedule(heartbeat_md: str) -> list[ScheduledJob]:
    """F-002: Parse ## 调度汇总 table into ScheduledJob list.

    Raises ValueError on duplicate job names or invalid cron expressions.
    """
    jobs = []
    seen_names: dict[str, int] = {}

    for line in heartbeat_md.splitlines():
        # Match table rows with at least 4 pipe-separated columns
        if not line.strip().startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) < 4:
            continue
        # Skip header rows
        if any(c in parts[0] for c in ["任务", "---", "Task"]):
            continue

        job_name = parts[0]
        schedule_type = parts[1].lower()
        cron_expr = parts[2].strip().strip("`").strip()
        status = parts[3].lower()

        # Track duplicates
        seen_names.setdefault(job_name, 0)
        seen_names[job_name] += 1
        if seen_names[job_name] > 1:
            raise ValueError(f"Duplicate job name in HEARTBEAT.md: '{job_name}'")

        # Validate cron
        if not _validate_cron(cron_expr):
            raise ValueError(f"Invalid cron expression for job '{job_name}': '{cron_expr}'")

        script = HERMES_JOB_SCRIPT_MAP.get(job_name)

        jobs.append(ScheduledJob(
            name=job_name,
            schedule=cron_expr,
            enabled=(status == "active"),
            schedule_type=schedule_type,
            script=script,
            no_agent=True,
            deliver="local",
        ))

    return jobs


# ---------------------------------------------------------------------------
# F-004: Skills scanner
# ---------------------------------------------------------------------------

def scan_skills(source_root: str) -> list[SkillEntry]:
    """F-004: Scan skills/**/SKILL.md and build SkillEntry list."""
    root = Path(source_root).resolve()
    skills_dir = root / "skills"
    entries = []

    if not skills_dir.exists():
        return entries

    for skill_md in skills_dir.rglob("SKILL.md"):
        # Skip virtual environment and hidden directories
        if any(part.startswith(".") or part == ".venv" or part == "node_modules"
               for part in skill_md.parts):
            continue
        # Extract skill id from path: skills/<category>/<name>/SKILL.md
        parts = skill_md.parent.relative_to(skills_dir).parts
        if len(parts) >= 2:
            skill_id = parts[-1]
            category = parts[-2] if len(parts) > 1 else "unknown"
        elif len(parts) == 1:
            skill_id = parts[0]
            category = "root"
        else:
            continue

        # Extract name and description from frontmatter
        name = skill_id
        description = None
        content = skill_md.read_text(encoding="utf-8")
        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            fm_text = fm_match.group(1)
            n_match = re.search(r"^name:\s*(.+?)\s*$", fm_text, re.MULTILINE)
            if n_match:
                name = n_match.group(1).strip().strip("\"'")
            d_match = re.search(r"^description:\s*[\"']?(.+?)[\"']?\s*$", fm_text, re.MULTILINE)
            if d_match:
                desc_raw = d_match.group(1).strip()
                # Remove surrounding quotes if present
                description = desc_raw.strip("\"'")

        rel_path = str(skill_md.relative_to(root))

        entries.append(SkillEntry(
            id=skill_id,
            name=name,
            path=rel_path,
            description=description,
        ))

    # Check for duplicate ids
    seen_ids: dict[str, int] = {}
    for e in entries:
        seen_ids.setdefault(e.id, 0)
        seen_ids[e.id] += 1
        if seen_ids[e.id] > 1:
            raise ValueError(f"Duplicate skill id: '{e.id}'")

    return entries


# ---------------------------------------------------------------------------
# F-003: Hermes adapter
# ---------------------------------------------------------------------------

def generate_hermes_profile(model: AgentProfileModel) -> dict[str, str]:
    """F-003: Generate Hermes profile file set from common model.

    Returns {relative_path: content} dict.
    """
    outputs: dict[str, str] = {}
    p = model.profile  # profile name, e.g. "yquant"

    # profile.yaml
    profile_yaml = textwrap.dedent(f"""\
        name: {p}
        platform: hermes
        generator: scripts/generate_agent_profile.py
        generated_at: {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()}
    """).strip()
    outputs["profile.yaml"] = profile_yaml

    # config.yaml — mirrors current Hermes yquant profile conventions
    config_yaml = textwrap.dedent(f"""\
        model:
          provider: minimax
          model: MiniMax-M2.7

        profile:
          name: {p}
          storage: ~/.hermes/profiles/{p}

        agent:
          default_profile: {p}

        features:
          feishu:
            enabled: true
            oc_5519df69b0e5179552a477db071eab83: enabled
    """).strip()
    outputs["config.yaml"] = config_yaml

    # SOUL.md
    if model.soul:
        outputs["SOUL.md"] = model.soul
    elif model.agents_md:
        outputs["SOUL.md"] = model.agents_md

    # memories/USER.md
    if model.user_memory:
        outputs["memories/USER.md"] = model.user_memory

    # memories/MEMORY.md — project memory
    if model.project_memory:
        outputs["memories/MEMORY.md"] = model.project_memory

    # skills/skills_manifest.json
    manifest = {
        "schema_version": 1,
        "profile": p,
        "generated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "skills": [asdict(s) for s in model.skills],
    }
    outputs["skills/skills_manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2)

    # cron/jobs.json
    jobs_list = []
    missing_scripts = []
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    for job in model.scheduled_jobs:
        if job.enabled and job.script is None:
            missing_scripts.append(job.name)
        jobs_list.append({
            "name": job.name,
            "prompt": "",
            "skills": [],
            "skill": None,
            "model": None,
            "provider": None,
            "base_url": None,
            "script": job.script or None,
            "no_agent": job.no_agent,
            "context_from": None,
            "schedule": {
                "kind": "cron",
                "expr": job.schedule,
                "display": job.schedule,
            },
            "schedule_display": job.schedule,
            "repeat": {
                "times": None,
                "completed": 0,
            },
            "enabled": job.enabled,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "created_at": now,
            "next_run_at": None,
            "last_run_at": None,
            "last_status": None,
            "last_error": None,
            "last_delivery_error": None,
            "deliver": job.deliver,
            "origin": None,
            "enabled_toolsets": None,
            "workdir": "/home/pascal/workspace/yquant-investment",
        })
    jobs_out = {
        "schema_version": 1,
        "profile": p,
        "jobs": jobs_list,
        "_missing_scripts": missing_scripts if missing_scripts else None,
    }
    outputs["cron/jobs.json"] = json.dumps(jobs_out, ensure_ascii=False, indent=2)

    return outputs


# ---------------------------------------------------------------------------
# F-005/006: Output writing
# ---------------------------------------------------------------------------

def _safe_path(base: Path, rel: str) -> Path:
    """Resolve a relative path safely, preventing path traversal."""
    target = (base / rel).resolve()
    # Ensure target is under base
    try:
        target.relative_to(base)
    except ValueError:
        raise ValueError(f"Path traversal attempt detected: {rel}")
    return target


def write_outputs(outputs: dict[str, str], output_dir: Path, dry_run: bool = False) -> list[str]:
    """F-006: Write generated files to output directory.

    Returns list of written relative paths.
    """
    output_dir = output_dir.resolve()
    written = []

    if dry_run:
        for rel_path, content in outputs.items():
            print(f"[DRY] {rel_path}  ({len(content)} bytes)")
        return list(outputs.keys())

    output_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in outputs.items():
        target = _safe_path(output_dir, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(rel_path)

    return written


# ---------------------------------------------------------------------------
# F-008: Manifest generation
# ---------------------------------------------------------------------------

def compute_file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def generate_manifest(
    args: argparse.Namespace,
    model: AgentProfileModel,
    output_dir: Path,
    output_files: list[str],
) -> dict:
    """F-008: Generate migration/generated-manifest.json."""
    output_dir = output_dir.resolve()
    inputs = [{"path": f, "type": "source"} for f in model.source_files_read]

    outputs = []
    for rel_path in output_files:
        full_path = output_dir / rel_path
        outputs.append({
            "path": rel_path,
            "hash": compute_file_hash(full_path) if full_path.exists() else None,
        })

    manifest = {
        "schema_version": 1,
        "generator": "scripts/generate_agent_profile.py",
        "platform": args.platform,
        "profile": args.profile,
        "source_root": str(model.source_root),
        "generated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        "inputs": inputs,
        "outputs": outputs,
    }
    return manifest


# ---------------------------------------------------------------------------
# F-007: Apply to target
# ---------------------------------------------------------------------------

def apply_to_target(
    output_dir: Path,
    target_root: Path,
    force: bool = False,
    backup: bool = False,
) -> list[str]:
    """F-007: Copy generated profile to target Hermes directory.

    Returns list of installed relative paths.
    """
    target_root = target_root.resolve()
    installed = []

    if backup:
        backup_dir = target_root.parent / f"{target_root.name}.backup.{datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d%H%M%S')}"
        import shutil
        if target_root.exists():
            shutil.copytree(target_root, backup_dir)
            print(f"[backup] Created: {backup_dir}")

    target_root.mkdir(parents=True, exist_ok=True)

    for rel_path in HERMES_OUTPUT_STRUCTURE:
        src = output_dir / rel_path
        dst = target_root / rel_path
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
            installed.append(rel_path)

    return installed


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_hermes_profile(output_dir: Path) -> list[str]:
    """F-007/F-008: Validate generated Hermes profile structure.

    Returns list of error messages. Empty list means passed.
    """
    errors = []
    output_dir = output_dir.resolve()

    required = ["profile.yaml", "config.yaml", "SOUL.md"]
    for rel in required:
        if not (output_dir / rel).exists():
            errors.append(f"Missing required file: {rel}")

    # Validate JSON files
    for rel in ["skills/skills_manifest.json", "cron/jobs.json"]:
        json_path = output_dir / rel
        if json_path.exists():
            try:
                json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in {rel}: {e}")

    # Validate jobs.json schema
    jobs_path = output_dir / "cron/jobs.json"
    if jobs_path.exists():
        try:
            data = json.loads(jobs_path.read_text(encoding="utf-8"))
            if "jobs" not in data:
                errors.append("jobs.json missing 'jobs' key")
            else:
                for job in data["jobs"]:
                    if "name" not in job or "schedule" not in job:
                        errors.append(f"jobs.json: job missing required field: {job}")
        except json.JSONDecodeError:
            pass  # already caught above

    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-platform Agent Profile Generator — first adapter: Hermes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Dry run to stdout
              python generate_agent_profile.py --platform hermes --profile yquant

              # Generate to dist/
              python generate_agent_profile.py --platform hermes --profile yquant \\
                --source-root . --output-dir dist/

              # Validate a generated profile
              python generate_agent_profile.py --platform hermes --profile yquant \\
                --source-root . --output-dir dist/ --validate

              # Apply to ~/.hermes
              python generate_agent_profile.py --platform hermes --profile yquant \\
                --source-root . --output-dir dist/ --apply --target-root ~/.hermes
        """),
    )
    parser.add_argument(
        "--platform",
        default="hermes",
        choices=["hermes"],
        help="Target platform adapter (first edition: hermes only)",
    )
    parser.add_argument(
        "--profile",
        default="yquant",
        help="Profile name to generate",
    )
    parser.add_argument(
        "--source-root",
        default=".",
        help="Path to YQuant project root (default: .)",
    )
    parser.add_argument(
        "--output-dir",
        default="dist/agent-profiles",
        help="Output directory for generated profile (default: dist/agent-profiles)",
    )
    parser.add_argument(
        "--target-root",
        default="~/.hermes/profiles",
        help="Target Hermes profiles root for --apply (default: ~/.hermes/profiles)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show plan without writing files",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Install generated profile to --target-root",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite without backup when applying",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup of existing target profile before overwriting",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate generated profile after writing",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Resolve paths
    output_dir = Path(args.output_dir).resolve()
    target_dir = Path(args.target_root).expanduser() / args.profile
    profile_dir = output_dir / args.platform / args.profile

    try:
        # Load model
        model = load_profile_model(args)

        print(f"[INFO] Platform: {args.platform}")
        print(f"[INFO] Profile: {args.profile}")
        print(f"[INFO] Source root: {model.source_root}")
        print(f"[INFO] Source files read: {len(model.source_files_read)}")
        print(f"[INFO] Scheduled jobs found: {len(model.scheduled_jobs)}")
        print(f"[INFO] Skills found: {len(model.skills)}")

        # Generate
        if args.platform == "hermes":
            outputs = generate_hermes_profile(model)
        else:
            print(f"[ERROR] Unknown platform: {args.platform}")
            return 1

        # Dry run
        if args.dry_run:
            print(f"\n=== DRY RUN: would write {len(outputs)} file(s) to {profile_dir} ===")
            write_outputs(outputs, profile_dir, dry_run=True)
            return 0

        # Write files
        written = write_outputs(outputs, profile_dir)
        print(f"\n[INFO] Wrote {len(written)} file(s) to {profile_dir}")

        # Generate manifest
        manifest = generate_manifest(args, model, profile_dir, written)
        manifest_dir = profile_dir / "migration"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "generated-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] Manifest: {manifest_path}")

        # Validate
        if args.validate:
            errors = validate_hermes_profile(profile_dir)
            if errors:
                print(f"\n[VALIDATION ERRORS] {len(errors)} issue(s) found:")
                for e in errors:
                    print(f"  - {e}")
                return 1
            else:
                print(f"[PASS] Profile validation OK")

        # Apply
        if args.apply:
            installed = apply_to_target(profile_dir, target_dir, force=args.force, backup=args.backup)
            print(f"\n[INFO] Installed {len(installed)} file(s) to {target_dir}")

    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] Unexpected: {e}")
        raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
