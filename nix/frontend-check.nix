# Lints and type-checks what uv can't install: the CSS and JavaScript (Biome, and
# TypeScript over the JSDoc types) and the Jinja template (djLint).
{
  lib,
  runCommand,
  biome,
  typescript,
  djlint,
}:

runCommand "leave-burndown-frontend-checks"
  {
    nativeBuildInputs = [
      biome
      typescript
      djlint
    ];
    src = lib.fileset.toSource {
      root = ../.;
      fileset = lib.fileset.unions [
        ../biome.json
        ../tsconfig.json
        ../pyproject.toml # djLint's settings live here
        ../src
      ];
    };
  }
  ''
    cp -r $src work
    chmod -R u+w work
    cd work

    biome check
    tsc -p tsconfig.json
    # Lint only: nixpkgs' djLint formats a little differently from the one in uv.lock,
    # so formatting is checked with `uv run djlint --check`, not here.
    djlint src/leave_burndown/templates --lint

    touch $out
  ''
