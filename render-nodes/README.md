# render-nodes/: external render workers (planned, Milestone 10)

The Claude Code Cloud development VM (4 vCPU, no GPU, ephemeral) renders previews and short
finals only. Long films and GPU work (diffusion plates, optional Blender Grease Pencil)
will run on external workers built from the same locked environment (`uv.lock`).

Planned contents:
- a container definition (Dockerfile) and setup script for CPU workers, tested in CI;
- a GPU worker variant for the optional `comfyui` image provider;
- a job-manifest format: project, shot range, render profile, engine version, input hashes.

Nothing is provisioned, purchased or configured yet. No secrets ever go in this folder.
