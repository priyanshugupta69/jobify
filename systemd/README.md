# Systemd setup

User-level service (no root needed).

```bash
mkdir -p ~/.config/systemd/user
ln -s ~/projects/job_pipeline/systemd/job-pipeline.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now job-pipeline
systemctl --user status job-pipeline
journalctl --user -u job-pipeline -f
```

To survive logout you may need:

```bash
sudo loginctl enable-linger $USER
```

## Cutover from OpenClaw cron

After verifying this service runs and the 7 schedules show up in
`curl localhost:8000/scheduler/jobs`, edit `~/.openclaw/cron/jobs.json`
and set `enabled: false` on every job-pipeline / job-batch / job-daily-report
entry. Leave `memory-cleanup` alone — that's not part of this project.
