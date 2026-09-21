# Leave burn-down

Annual leave planner and burn-down chart. The leave year runs 1 Sep to 31 Aug.

## Run it locally

You don't need Nix. You need **Python 3.14 or newer**, and then either route below
works from a checkout of this repository.

**With [uv](https://docs.astral.sh/uv/)** (it also fetches Python 3.14 if you don't have it):

```sh
uv run leave-burndown
```

**With plain pip:**

```sh
python3.14 -m venv .venv
source .venv/bin/activate
pip install .
leave-burndown
```

Then open <http://127.0.0.1:5050>. A new install shows one example entry; nothing is
written to disk until you save something.

| Environment variable | What it does |
| --- | --- |
| `LEAVE_DATA` | Where your data lives. Default: `leave_data.json` in the directory you run it from. |
| `LEAVE_DEBUG=1` | Flask's debugger and auto-reload. Off unless you ask; for development only. |
| `SECRET_KEY` | Signs the little confirmation messages. Optional: a random one is made on each start. |

It's a single-user tool with no login, and it only listens on `127.0.0.1`. Don't put it on
a network without something in front of it. The port is fixed at 5050; to use another, run it
under gunicorn (`pip install gunicorn`), keeping to one worker because the data file is
rewritten without locking:

```sh
gunicorn --workers 1 -b 127.0.0.1:8000 'leave_burndown:create_app()'
```

## Develop

```sh
uv sync                                                # the app plus the Python dev tools
LEAVE_DEBUG=1 uv run leave-burndown                    # with the debugger on
uv run pytest                                          # unit tests
```

The checks:

```sh
uv run ruff check && uv run ruff format --check        # Python lint and format
uv run ty check && uv run basedpyright                 # Python types
biome check                                            # CSS and JS: lint and format
tsc -p tsconfig.json                                   # JS types (strict, from JSDoc)
uv run djlint src/leave_burndown/templates --lint      # template lint
uv run djlint src/leave_burndown/templates --check     # template format (`--reformat` fixes)
```

`biome` and `tsc` aren't Python, so `uv` can't install them. With Nix, `nix develop` gives you
both at the versions this repository is checked with. Without Nix, use npm, keeping to these
major versions (`typescript` has since moved on to 7.x, which hasn't been tried here):

```sh
npm install --global @biomejs/biome@2.5 typescript@5.9
```

`nix flake check` runs the Biome, `tsc` and template-lint checks, plus a VM test of the service.
Ruff, ty, basedpyright and pytest are run with `uv` as above.

## Deploy (NixOS)

Add this flake as an input, import `nixosModules.default`, then:

```nix
services.leave-burndown = {
  enable = true;
  # port = 5050; host = "127.0.0.1"; openFirewall = false;
  # secretKeyFile = "/run/secrets/leave-burndown-key";
};
```

It runs under gunicorn as a systemd `DynamicUser` service. Data lives in
`/var/lib/leave-burndown/leave_data.json`. To import existing data, stop the service,
copy the file to `/var/lib/private/leave-burndown/`, give it the same owner as that directory
(the dynamic user's uid; systemd only fixes the directory, not files you add), and start it again:

```sh
sudo systemctl stop leave-burndown
sudo install -m 600 leave_data.json /var/lib/private/leave-burndown/
sudo chown --reference=/var/lib/private/leave-burndown /var/lib/private/leave-burndown/leave_data.json
sudo systemctl start leave-burndown
```

`nix flake check` builds the package and runs a VM test of the module.
