{
  lib,
  buildPythonApplication,
  uv-build,
  flask,
}:

let
  pyproject = fromTOML (builtins.readFile ../pyproject.toml);
in
buildPythonApplication {
  pname = pyproject.project.name;
  version = pyproject.project.version;
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../README.md
      ../src
    ];
  };

  # pyproject pins uv_build to the version `uv init` used; nixpkgs may lag it.
  postPatch = ''
    substituteInPlace pyproject.toml \
      --replace-fail '"uv_build>=0.12.5,<0.13.0"' '"uv_build"'
  '';

  build-system = [ uv-build ];
  dependencies = [ flask ];

  pythonImportsCheck = [ "leave_burndown" ];

  meta = {
    description = "Annual leave burn-down chart and planner";
    mainProgram = "leave-burndown";
  };
}
