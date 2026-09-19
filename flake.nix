{
  description = "Annual leave burn-down";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        leave-burndown = pkgs.python314Packages.callPackage ./nix/package.nix { };
        default = leave-burndown;
      });

      nixosModules.default = import ./nix/module.nix self;

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          # uv runs the Python tools; biome and tsc cover the CSS and JS.
          packages = [
            pkgs.uv
            pkgs.biome
            pkgs.typescript
          ];
        };
      });

      checks = forAllSystems (pkgs: {
        frontend = pkgs.callPackage ./nix/frontend-check.nix { };

        # Boots a VM with the service enabled and fetches the page.
        nixos-module = pkgs.testers.runNixOSTest (import ./nix/test.nix self);
      });
    };
}
