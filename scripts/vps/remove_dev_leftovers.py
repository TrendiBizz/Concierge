#!/usr/bin/env python3
"""Inspect and safely remove leftover dev-* container resources on the VPS.

Approved by Jo (2026-11-21):
1. List all dev-* containers and their images, volumes, and networks.
2. Confirm none of those resources are used by production (trendi-* / asterisk-* / any non-dev-* container).
3. Back up any candidate volume that contains data to
   /opt/trendi/releases/20261108-vps/removed/20261121/dev-volumes/<volume>.tar.gz before removal.
4. Remove dev-* containers, then their unused volumes, networks, and images.
5. Remove containerd ONLY if Podman (and all other installed packages/runtime config) does not
   depend on it; otherwise keep it and report why.

Never reads or prints container environment variables or /opt/trendi/shared secret files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_RELEASE = "/opt/trendi/releases/20261108-vps"
DEFAULT_BACKUP_DATE = "20261121"
BUILTIN_PROTECTED_NETWORKS = frozenset({
    "podman",
    "bridge",
    "host",
    "none",
    "default",
    "trendi_default",
    "asterisk_phone",
})
PROTECTED_IMAGE_PREFIXES = (
    "localhost/trendi-",
    "trendi-",
    "localhost/asterisk-",
    "asterisk-",
)

Runner = Callable[[list[str]], tuple[int, str, str]]


def default_runner(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, "", f"timeout: {exc}"


def _clean_name(raw: str) -> str:
    return (raw or "").lstrip("/").strip()


def _is_dev_name(name: str) -> bool:
    low = _clean_name(name).lower()
    return low.startswith("dev-") or low.startswith("dev_")


def _is_dev_container(name: str) -> bool:
    return _clean_name(name).startswith("dev-")


def _normalize_image_id(raw: str) -> str:
    val = (raw or "").strip()
    if val.startswith("sha256:"):
        val = val[len("sha256:"):]
    return val


@dataclass
class ContainerInfo:
    name: str
    cid: str
    status: str
    image_id: str
    image_name: str
    compose_project: str
    volumes: list[str] = field(default_factory=list)
    bind_sources: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)


@dataclass
class VolumeInfo:
    name: str
    mountpoint: str
    compose_project: str
    file_count: int = 0
    total_bytes: int = 0


@dataclass
class NetworkInfo:
    name: str
    nid: str
    driver: str
    compose_project: str
    containers: list[str] = field(default_factory=list)


@dataclass
class ImageInfo:
    image_id: str
    names: list[str] = field(default_factory=list)
    size: int = 0


@dataclass
class CleanupPlan:
    dev_containers: list[ContainerInfo]
    non_dev_containers: list[ContainerInfo]
    candidate_volumes: list[VolumeInfo]
    candidate_networks: list[NetworkInfo]
    candidate_images: list[ImageInfo]
    skipped_volumes: dict[str, str]
    skipped_networks: dict[str, str]
    skipped_images: dict[str, str]
    conflicts: list[str]


@dataclass
class ContainerdDecision:
    installed_packages: list[str]
    service_active: str
    service_enabled: str
    podman_depends: list[str]
    rdepends: list[str]
    simulated_removals: list[str]
    runtime_uses_containerd: bool
    should_remove: bool
    reason: str


def parse_containers(inspect_data: list[dict[str, Any]]) -> list[ContainerInfo]:
    out: list[ContainerInfo] = []
    for item in inspect_data or []:
        name = _clean_name(item.get("Name", ""))
        cid = str(item.get("Id", ""))[:12]
        state = item.get("State") or {}
        status = str(state.get("Status") or "")
        image_id = _normalize_image_id(str(item.get("Image") or ""))
        image_name = str(item.get("ImageName") or (item.get("Config") or {}).get("Image") or "")
        labels = (item.get("Config") or {}).get("Labels") or {}
        compose_project = str(labels.get("com.docker.compose.project") or "")

        volumes: list[str] = []
        bind_sources: list[str] = []
        for m in item.get("Mounts") or []:
            mtype = str(m.get("Type") or "").lower()
            mname = str(m.get("Name") or "").strip()
            msrc = str(m.get("Source") or "").strip()
            if mtype == "volume" and mname:
                volumes.append(mname)
            elif msrc:
                bind_sources.append(msrc)

        net_map = (item.get("NetworkSettings") or {}).get("Networks") or {}
        networks = sorted(str(k) for k in net_map.keys())

        out.append(ContainerInfo(
            name=name,
            cid=cid,
            status=status,
            image_id=image_id,
            image_name=image_name,
            compose_project=compose_project,
            volumes=sorted(set(volumes)),
            bind_sources=sorted(set(bind_sources)),
            networks=networks,
        ))
    out.sort(key=lambda c: c.name)
    return out


def build_cleanup_plan(
    containers: list[ContainerInfo],
    volumes: list[VolumeInfo],
    networks: list[NetworkInfo],
    images: list[ImageInfo],
) -> CleanupPlan:
    dev_containers = sorted((c for c in containers if _is_dev_container(c.name)), key=lambda c: c.name)
    non_dev_containers = sorted((c for c in containers if not _is_dev_container(c.name)), key=lambda c: c.name)

    protected_volumes: set[str] = set()
    protected_networks: set[str] = set(BUILTIN_PROTECTED_NETWORKS)
    protected_image_ids: set[str] = set()
    protected_image_names: set[str] = set()

    for c in non_dev_containers:
        protected_volumes.update(c.volumes)
        protected_networks.update(c.networks)
        if c.image_id:
            protected_image_ids.add(c.image_id)
            protected_image_ids.add(c.image_id[:12])
        if c.image_name:
            protected_image_names.add(c.image_name)

    dev_container_names = {c.name for c in dev_containers}
    dev_attached_volumes: set[str] = set()
    dev_attached_networks: set[str] = set()
    dev_image_ids: set[str] = set()

    for c in dev_containers:
        dev_attached_volumes.update(c.volumes)
        dev_attached_networks.update(c.networks)
        if c.image_id:
            dev_image_ids.add(c.image_id)

    conflicts: list[str] = []

    # Volumes
    vol_by_name = {v.name: v for v in volumes}
    candidate_volumes: list[VolumeInfo] = []
    skipped_volumes: dict[str, str] = {}

    for v in sorted(volumes, key=lambda x: x.name):
        belongs_to_dev = (
            v.name in dev_attached_volumes
            or _is_dev_name(v.name)
            or _is_dev_name(v.compose_project)
        )
        if not belongs_to_dev:
            continue
        if v.name in protected_volumes:
            msg = f"volume {v.name} is mounted by a non-dev container"
            skipped_volumes[v.name] = msg
            conflicts.append(msg)
        else:
            candidate_volumes.append(v)

    for vname in sorted(dev_attached_volumes):
        if vname not in vol_by_name and vname in protected_volumes:
            msg = f"volume {vname} is mounted by a non-dev container"
            skipped_volumes[vname] = msg
            conflicts.append(msg)

    # Networks
    candidate_networks: list[NetworkInfo] = []
    skipped_networks: dict[str, str] = {}

    for n in sorted(networks, key=lambda x: x.name):
        belongs_to_dev = (
            n.name in dev_attached_networks
            or _is_dev_name(n.name)
            or _is_dev_name(n.compose_project)
        )
        if not belongs_to_dev:
            continue
        external_members = [m for m in n.containers if m not in dev_container_names]
        if n.name in protected_networks or external_members:
            if n.name in BUILTIN_PROTECTED_NETWORKS:
                reason = f"network {n.name} is a built-in/production network"
            else:
                reason = f"network {n.name} is used by non-dev container(s): {', '.join(sorted(external_members)) or 'protected'}"
            skipped_networks[n.name] = reason
            if n.name not in BUILTIN_PROTECTED_NETWORKS:
                conflicts.append(reason)
        else:
            candidate_networks.append(n)

    # Images: only images used by dev-* containers (or named with dev-*), and never used by any non-dev container.
    candidate_images: list[ImageInfo] = []
    skipped_images: dict[str, str] = {}

    for img in sorted(images, key=lambda x: (x.names[0] if x.names else x.image_id)):
        img_id = _normalize_image_id(img.image_id)
        used_by_dev = img_id in dev_image_ids or any(img_id.startswith(d) or d.startswith(img_id) for d in dev_image_ids if d)
        named_dev = any(_is_dev_name(n.split("/")[-1].split(":")[0]) for n in img.names)
        if not (used_by_dev or named_dev):
            continue

        used_by_non_dev = (
            img_id in protected_image_ids
            or img_id[:12] in protected_image_ids
            or any(n in protected_image_names for n in img.names)
        )
        is_prod_image = any(n.startswith(PROTECTED_IMAGE_PREFIXES) for n in img.names)

        if used_by_non_dev:
            skipped_images[img_id[:12]] = f"shared with non-dev container ({', '.join(img.names) or img_id[:12]})"
        elif is_prod_image:
            skipped_images[img_id[:12]] = f"matches protected production image prefix ({', '.join(img.names)})"
        else:
            candidate_images.append(img)

    return CleanupPlan(
        dev_containers=dev_containers,
        non_dev_containers=non_dev_containers,
        candidate_volumes=candidate_volumes,
        candidate_networks=candidate_networks,
        candidate_images=candidate_images,
        skipped_volumes=skipped_volumes,
        skipped_networks=skipped_networks,
        skipped_images=skipped_images,
        conflicts=conflicts,
    )


def evaluate_containerd(
    installed_packages: list[str],
    service_active: str,
    service_enabled: str,
    podman_depends_text: str,
    rdepends_output: str,
    apt_simulate_output: str,
    podman_info_text: str,
    active_ctr_tasks: list[str] | None = None,
) -> ContainerdDecision:
    installed = sorted(set(p.strip() for p in installed_packages if p.strip()))
    if not installed:
        return ContainerdDecision(
            installed_packages=[],
            service_active=service_active,
            service_enabled=service_enabled,
            podman_depends=[],
            rdepends=[],
            simulated_removals=[],
            runtime_uses_containerd=False,
            should_remove=False,
            reason="containerd is not installed",
        )

    podman_deps = [
        tok.strip()
        for tok in re.split(r"[,|\n]", podman_depends_text or "")
        if "containerd" in tok.lower()
    ]

    rdeps: list[str] = []
    in_rdeps = False
    for line in (rdepends_output or "").splitlines():
        s = line.strip()
        if s.startswith("Reverse Depends:"):
            in_rdeps = True
            continue
        if in_rdeps and s and not s.startswith("containerd"):
            pkg = s.lstrip("|").strip()
            if pkg and pkg not in installed:
                rdeps.append(pkg)
    rdeps = sorted(set(rdeps))

    sim_removals = sorted(set(
        m.group(1)
        for m in re.finditer(r"^Remv\s+(\S+)", apt_simulate_output or "", re.MULTILINE)
    ))
    extra_removals = [p for p in sim_removals if p not in installed]

    runtime_uses = "containerd" in (podman_info_text or "").lower()
    tasks = [t for t in (active_ctr_tasks or []) if t.strip()]

    reasons: list[str] = []
    if podman_deps:
        reasons.append(f"podman package metadata references containerd ({', '.join(podman_deps)})")
    if runtime_uses:
        reasons.append("podman info references containerd")
    if any(p.startswith(("podman", "conmon", "crun", "runc", "netavark", "aardvark", "buildah", "skopeo", "containers-common", "slirp4netns")) for p in extra_removals):
        reasons.append(f"removing containerd would also remove podman stack package(s): {', '.join(extra_removals)}")
    elif extra_removals:
        reasons.append(f"removing containerd would also remove installed package(s): {', '.join(extra_removals)}")
    if rdeps:
        reasons.append(f"installed reverse dependencies exist: {', '.join(rdeps)}")
    if tasks:
        reasons.append(f"containerd has active task(s): {', '.join(tasks)}")

    if reasons:
        return ContainerdDecision(
            installed_packages=installed,
            service_active=service_active,
            service_enabled=service_enabled,
            podman_depends=podman_deps,
            rdepends=rdeps,
            simulated_removals=sim_removals,
            runtime_uses_containerd=runtime_uses,
            should_remove=False,
            reason="; ".join(reasons),
        )

    return ContainerdDecision(
        installed_packages=installed,
        service_active=service_active,
        service_enabled=service_enabled,
        podman_depends=podman_deps,
        rdepends=rdeps,
        simulated_removals=sim_removals,
        runtime_uses_containerd=runtime_uses,
        should_remove=True,
        reason=(
            f"podman does not depend on {', '.join(installed)} "
            f"(no installed reverse dependencies; apt removal affects only {', '.join(sim_removals or installed)}; "
            f"no active containerd tasks)"
        ),
    )


def _dir_stats(path: str) -> tuple[int, int]:
    if not path or not os.path.isdir(path):
        return 0, 0
    file_count = 0
    total_bytes = 0
    for root, dirs, files in os.walk(path):
        file_count += len(files)
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if not os.path.islink(fpath):
                    total_bytes += os.path.getsize(fpath)
            except OSError:
                pass
    return file_count, total_bytes


def backup_volume_mountpoint(volume_name: str, mountpoint: str, backup_dir: Path) -> Path | None:
    """Tar+gzip a volume mountpoint if it contains any entries; verify the archive."""
    if not mountpoint or not os.path.isdir(mountpoint):
        return None
    entries = os.listdir(mountpoint)
    if not entries:
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_dir, 0o700)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", volume_name)
    archive_path = backup_dir / f"{safe_name}.tar.gz"
    tmp_path = backup_dir / f"{safe_name}.tar.gz.tmp"

    with tarfile.open(tmp_path, "w:gz") as tf:
        for entry in sorted(entries):
            full = os.path.join(mountpoint, entry)
            tf.add(full, arcname=entry, recursive=True)

    # Verify archive can be read back before replacing final path.
    with tarfile.open(tmp_path, "r:gz") as tf:
        members = tf.getmembers()
        if not members:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"backup verification failed: empty archive for volume {volume_name}")

    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, archive_path)
    return archive_path


def _podman_json(run: Runner, args: list[str]) -> Any:
    rc, out, err = run(["podman", *args])
    if rc != 0:
        raise RuntimeError(f"podman {' '.join(args)} failed (rc={rc}): {err.strip()}")
    text = out.strip()
    if not text or text == "null":
        return []
    return json.loads(text)


def collect_live_state(run: Runner) -> tuple[list[ContainerInfo], list[VolumeInfo], list[NetworkInfo], list[ImageInfo]]:
    ps_rows = _podman_json(run, ["ps", "-a", "--format", "json"])
    cids = [str(row.get("Id") or row.get("ID") or "") for row in ps_rows if row]
    inspect_rows: list[dict[str, Any]] = []
    if cids:
        inspect_rows = _podman_json(run, ["inspect", *cids])
    containers = parse_containers(inspect_rows)

    vol_rows = _podman_json(run, ["volume", "ls", "--format", "json"])
    volumes: list[VolumeInfo] = []
    for row in vol_rows or []:
        name = str(row.get("Name") or "")
        mp = str(row.get("Mountpoint") or "")
        labels = row.get("Labels") or {}
        project = str(labels.get("com.docker.compose.project") or "")
        fcount, tbytes = _dir_stats(mp)
        volumes.append(VolumeInfo(
            name=name,
            mountpoint=mp,
            compose_project=project,
            file_count=fcount,
            total_bytes=tbytes,
        ))

    net_rows = _podman_json(run, ["network", "ls", "--format", "json"])
    networks: list[NetworkInfo] = []
    for row in net_rows or []:
        nname = str(row.get("name") or row.get("Name") or "")
        nid = str(row.get("id") or row.get("ID") or "")[:12]
        driver = str(row.get("driver") or row.get("Driver") or "")
        labels = row.get("labels") or row.get("Labels") or {}
        project = str(labels.get("com.docker.compose.project") or "")
        # Cross-reference connected containers from container inspect data
        connected = [c.name for c in containers if nname in c.networks]
        networks.append(NetworkInfo(
            name=nname,
            nid=nid,
            driver=driver,
            compose_project=project,
            containers=sorted(connected),
        ))

    img_rows = _podman_json(run, ["images", "--format", "json"])
    images_by_id: dict[str, ImageInfo] = {}
    for row in img_rows or []:
        iid = _normalize_image_id(str(row.get("Id") or row.get("ID") or ""))
        if not iid:
            continue
        names = [str(n) for n in (row.get("Names") or []) if n]
        if not names:
            repo = str(row.get("Repository") or "")
            tag = str(row.get("Tag") or "")
            if repo and repo != "<none>":
                names = [f"{repo}:{tag}" if tag else repo]
        size = int(row.get("Size") or 0)
        if iid in images_by_id:
            merged = sorted(set(images_by_id[iid].names).union(names))
            images_by_id[iid].names = merged
        else:
            images_by_id[iid] = ImageInfo(image_id=iid, names=sorted(set(names)), size=size)
    images = list(images_by_id.values())

    return containers, volumes, networks, images


def collect_containerd_decision(run: Runner) -> ContainerdDecision:
    rc, out, _ = run(["dpkg-query", "-W", "-f=${Package}\t${db:Status-Status}\n", "containerd*"])
    installed: list[str] = []
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and parts[1].strip() == "installed":
                installed.append(parts[0].strip())

    _, svc_active, _ = run(["systemctl", "is-active", "containerd"])
    _, svc_enabled, _ = run(["systemctl", "is-enabled", "containerd"])
    svc_active = svc_active.strip() or "unknown"
    svc_enabled = svc_enabled.strip() or "unknown"

    _, podman_deps_text, _ = run([
        "dpkg-query", "-W",
        "-f=${Pre-Depends}\n${Depends}\n${Recommends}\n${Suggests}\n",
        "podman",
    ])

    rdeps_chunks: list[str] = []
    for pkg in installed:
        _, rout, _ = run(["apt-cache", "rdepends", "--installed", pkg])
        rdeps_chunks.append(rout)

    sim_out = ""
    if installed:
        _, sim_out, _ = run(["apt-get", "-s", "remove", *installed])

    _, podman_info, _ = run(["podman", "info", "--format", "json"])

    active_tasks: list[str] = []
    if svc_active == "active":
        rc_ns, ns_out, _ = run(["ctr", "namespaces", "ls", "-q"])
        if rc_ns != 0:
            active_tasks.append("ctr-unavailable")
        else:
            namespaces = [line.strip() for line in ns_out.splitlines() if line.strip()] or ["default"]
            for ns in namespaces:
                rc_t, t_out, _ = run(["ctr", "-n", ns, "tasks", "ls", "-q"])
                if rc_t != 0:
                    active_tasks.append(f"{ns}:ctr-error")
                else:
                    for line in t_out.splitlines():
                        if line.strip():
                            active_tasks.append(f"{ns}:{line.strip()}")
        rc_shim, shim_out, _ = run(["pgrep", "-f", "containerd-shim"])
        if rc_shim == 0 and shim_out.strip():
            active_tasks.append("containerd-shim-running")

    return evaluate_containerd(
        installed_packages=installed,
        service_active=svc_active,
        service_enabled=svc_enabled,
        podman_depends_text=podman_deps_text,
        rdepends_output="\n".join(rdeps_chunks),
        apt_simulate_output=sim_out,
        podman_info_text=podman_info,
        active_ctr_tasks=active_tasks,
    )


def print_report(
    plan: CleanupPlan,
    cd: ContainerdDecision,
    all_images: list[ImageInfo],
    all_volumes: list[VolumeInfo],
    all_networks: list[NetworkInfo],
) -> None:
    print("=== Production / non-dev containers (protected) ===")
    for c in plan.non_dev_containers:
        print(f"  KEEP  {c.name}  [{c.status}]  image={c.image_name} ({c.image_id[:12]})  vols={c.volumes}  nets={c.networks}")

    print("\n=== Leftover dev-* containers (targets) ===")
    if not plan.dev_containers:
        print("  (none)")
    for c in plan.dev_containers:
        print(f"  TARGET  {c.name}  [{c.status}]  image={c.image_name} ({c.image_id[:12]})  vols={c.volumes}  binds={c.bind_sources}  nets={c.networks}")

    print("\n=== Candidate dev-* volumes ===")
    if not plan.candidate_volumes:
        print("  (none)")
    for v in plan.candidate_volumes:
        print(f"  TARGET  {v.name}  files={v.file_count}  bytes={v.total_bytes}  mountpoint={v.mountpoint}")
    for vname, reason in sorted(plan.skipped_volumes.items()):
        print(f"  SKIP    {vname}  ({reason})")

    print("\n=== Candidate dev-* networks ===")
    if not plan.candidate_networks:
        print("  (none)")
    for n in plan.candidate_networks:
        print(f"  TARGET  {n.name}  driver={n.driver}  containers={n.containers}")
    for nname, reason in sorted(plan.skipped_networks.items()):
        print(f"  SKIP    {nname}  ({reason})")

    print("\n=== Candidate unused dev-* images ===")
    if not plan.candidate_images:
        print("  (none)")
    for img in plan.candidate_images:
        mb = img.size / (1024 * 1024)
        print(f"  TARGET  {img.image_id[:12]}  names={img.names}  size={mb:.1f}MB")
    for iid, reason in sorted(plan.skipped_images.items()):
        print(f"  SKIP    {iid}  ({reason})")

    print("\n=== All volumes on host (for visibility) ===")
    for v in sorted(all_volumes, key=lambda x: x.name):
        print(f"  VOL  {v.name}  project={v.compose_project or '-'}  files={v.file_count}  bytes={v.total_bytes}")

    print("\n=== All networks on host (for visibility) ===")
    for n in sorted(all_networks, key=lambda x: x.name):
        print(f"  NET  {n.name}  driver={n.driver}  project={n.compose_project or '-'}  containers={n.containers}")

    print("\n=== All images on host (for visibility) ===")
    for img in sorted(all_images, key=lambda x: (x.names[0] if x.names else x.image_id)):
        mb = img.size / (1024 * 1024)
        print(f"  IMG  {img.image_id[:12]}  names={img.names}  size={mb:.1f}MB")

    print("\n=== Production safety confirmation ===")
    if plan.conflicts:
        for c in plan.conflicts:
            print(f"  CONFLICT: {c}")
    else:
        print("  CONFIRMED: zero candidate dev-* containers, volumes, networks, or images are used by production (trendi-* / non-dev stack).")

    print("\n=== containerd assessment ===")
    print(f"  installed: {cd.installed_packages or '(none)'}")
    print(f"  service:   active={cd.service_active}  enabled={cd.service_enabled}")
    print(f"  podman_depends_on_containerd: {cd.podman_depends or '(none)'}")
    print(f"  installed_rdepends: {cd.rdepends or '(none)'}")
    print(f"  apt_simulated_removals: {cd.simulated_removals or '(none)'}")
    print(f"  runtime_uses_containerd: {cd.runtime_uses_containerd}")
    print(f"  decision:  {'REMOVE' if cd.should_remove else 'KEEP'} — {cd.reason}")


def apply_cleanup(
    run: Runner,
    plan: CleanupPlan,
    cd: ContainerdDecision,
    release: str,
    backup_date: str,
) -> dict[str, Any]:
    if plan.conflicts:
        raise RuntimeError("Refusing to apply: production safety conflicts detected: " + "; ".join(plan.conflicts))

    removed_root = Path(release) / "removed" / backup_date
    vol_backup_dir = removed_root / "dev-volumes"
    removed_root.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "containers_stopped": [],
        "volumes_backed_up": {},
        "volumes_empty_skipped_backup": [],
        "containers_removed": [],
        "volumes_removed": [],
        "networks_removed": [],
        "images_removed": [],
        "containerd": {
            "installed_before": cd.installed_packages,
            "decision": "remove" if cd.should_remove else "keep",
            "reason": cd.reason,
            "removed": [],
        },
    }

    # 1. Stop any running dev-* containers first so volume backups are quiescent/consistent.
    for c in plan.dev_containers:
        if c.status.lower() in {"running", "restarting", "paused"}:
            rc, _, err = run(["podman", "stop", "-t", "15", c.name])
            if rc != 0:
                raise RuntimeError(f"failed to stop {c.name}: {err.strip()}")
            summary["containers_stopped"].append(c.name)
            print(f"stopped dev container: {c.name}")

    # 2. Back up any candidate volume that has data before removing anything.
    for v in plan.candidate_volumes:
        if v.file_count > 0 or v.total_bytes > 0:
            archive = backup_volume_mountpoint(v.name, v.mountpoint, vol_backup_dir)
            if archive is None:
                summary["volumes_empty_skipped_backup"].append(v.name)
                print(f"volume {v.name}: empty at backup time, no tarball needed")
            else:
                size = archive.stat().st_size
                summary["volumes_backed_up"][v.name] = {"archive": str(archive), "archive_bytes": size}
                print(f"backed up volume {v.name} -> {archive} ({size} bytes)")
        else:
            # Double-check mountpoint in case non-regular entries (subdirs/symlinks) exist.
            archive = backup_volume_mountpoint(v.name, v.mountpoint, vol_backup_dir)
            if archive is not None:
                size = archive.stat().st_size
                summary["volumes_backed_up"][v.name] = {"archive": str(archive), "archive_bytes": size}
                print(f"backed up volume {v.name} -> {archive} ({size} bytes)")
            else:
                summary["volumes_empty_skipped_backup"].append(v.name)
                print(f"volume {v.name}: empty, no backup needed")

    # 3. Remove dev-* containers.
    for c in plan.dev_containers:
        rc, _, err = run(["podman", "rm", "-f", c.name])
        if rc != 0:
            raise RuntimeError(f"failed to remove container {c.name}: {err.strip()}")
        summary["containers_removed"].append(c.name)
        print(f"removed container: {c.name}")

    # 4. Remove candidate dev-* volumes (only after backup succeeded).
    for v in plan.candidate_volumes:
        rc, _, err = run(["podman", "volume", "rm", v.name])
        if rc != 0:
            raise RuntimeError(f"failed to remove volume {v.name}: {err.strip()}")
        summary["volumes_removed"].append(v.name)
        print(f"removed volume: {v.name}")

    # 5. Remove candidate dev-* networks.
    for n in plan.candidate_networks:
        rc, _, err = run(["podman", "network", "rm", n.name])
        if rc != 0:
            raise RuntimeError(f"failed to remove network {n.name}: {err.strip()}")
        summary["networks_removed"].append(n.name)
        print(f"removed network: {n.name}")

    # 6. Remove candidate unused dev-* images (without --force so Podman itself refuses if referenced).
    for img in plan.candidate_images:
        rc, _, err = run(["podman", "rmi", img.image_id])
        if rc != 0:
            print(f"WARN: image {img.image_id[:12]} ({img.names}) not removed: {err.strip()}")
        else:
            summary["images_removed"].append({"id": img.image_id[:12], "names": img.names})
            print(f"removed image: {img.image_id[:12]} ({img.names})")

    # 7. Conditionally remove containerd ONLY if Podman does not depend on it.
    if cd.should_remove and cd.installed_packages:
        run(["systemctl", "stop", "containerd"])
        run(["systemctl", "disable", "containerd"])
        rc, _, err = run(["apt-get", "remove", "-y", *cd.installed_packages])
        if rc != 0:
            raise RuntimeError(f"apt-get remove {' '.join(cd.installed_packages)} failed: {err.strip()}")
        summary["containerd"]["removed"] = cd.installed_packages
        print(f"removed containerd package(s): {', '.join(cd.installed_packages)}")
    else:
        print(f"containerd kept/unchanged: {cd.reason}")

    # 8. Post-cleanup runtime verification (socket link + compose config).
    sock = "/var/run/docker.sock"
    if not os.path.islink(sock) or os.readlink(sock) != "/run/podman/podman.sock":
        raise RuntimeError(f"docker.sock link invalid: {sock}")
    compose_file = os.path.join(release, "product/scripts/vps/compose.yml")
    rc, _, err = run([
        "podman", "compose",
        "-f", compose_file,
        "--env-file", "/opt/trendi/shared/compose.env",
        "--profile", "public",
        "config", "-q",
    ])
    if rc != 0:
        raise RuntimeError(f"podman compose config failed after cleanup: {err.strip()}")
    print("post-check: docker.sock -> /run/podman/podman.sock and compose config ok")

    manifest_path = removed_root / "dev-cleanup-manifest.json"
    manifest_path.write_text(json.dumps(summary, indent=2) + "\n")
    os.chmod(manifest_path, 0o600)
    print(f"manifest written: {manifest_path}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List and safely clean up dev-* container leftovers on the VPS.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="List and confirm safety without removing anything (default).")
    mode.add_argument("--apply", action="store_true", help="Back up data volumes and remove confirmed dev-* leftovers.")
    parser.add_argument("--release", default=os.environ.get("REL", DEFAULT_RELEASE))
    parser.add_argument("--backup-date", default=DEFAULT_BACKUP_DATE)
    args = parser.parse_args(argv)

    containers, volumes, networks, images = collect_live_state(default_runner)
    plan = build_cleanup_plan(containers, volumes, networks, images)
    cd = collect_containerd_decision(default_runner)

    print_report(plan, cd, images, volumes, networks)

    if not args.apply:
        print("\nDRY RUN complete: no changes made.")
        return 1 if plan.conflicts else 0

    print("\n=== Applying cleanup ===")
    apply_cleanup(default_runner, plan, cd, args.release, args.backup_date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
