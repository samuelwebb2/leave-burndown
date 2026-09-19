# Leave burn-down

Annual leave planner and burn-down chart. The leave year runs 1 Sep to 31 Aug.

## Develop

```sh
nix develop                                            # a shell with uv, biome and tsc
uv sync
LEAVE_DEBUG=1 uv run leave-burndown                    # http://127.0.0.1:5050, debug is opt-in
uv run pytest                                          # unit tests
```

Checks. `nix flake check` also runs the Biome, `tsc` and template-lint ones, plus a VM test of the service:

```sh
uv run ruff check && uv run ruff format --check        # Python lint and format
uv run ty check && uv run basedpyright                 # Python types
biome check                                            # CSS and JS: lint and format
tsc -p tsconfig.json                                   # JS types (strict, from JSDoc)
uv run djlint src/leave_burndown/templates --lint      # template lint
uv run djlint src/leave_burndown/templates --check     # template format (`--reformat` fixes)
```

Data is stored in `leave_data.json` in the working directory, or wherever `LEAVE_DATA` points.

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
