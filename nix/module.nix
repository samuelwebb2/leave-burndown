self:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.leave-burndown;

  # gunicorn and the app in one interpreter, so `import leave_burndown` works.
  # withPackages skips applications, hence toPythonModule.
  pythonEnv = pkgs.python314.withPackages (ps: [
    (pkgs.python314Packages.toPythonModule cfg.package)
    ps.gunicorn
  ]);

  start = pkgs.writeShellScript "leave-burndown-start" ''
    ${lib.optionalString (cfg.secretKeyFile != null) ''
      SECRET_KEY="$(< "$CREDENTIALS_DIRECTORY/secret-key")"
      export SECRET_KEY
    ''}
    exec ${pythonEnv}/bin/gunicorn \
      --bind ${cfg.host}:${toString cfg.port} \
      --workers ${toString cfg.workers} \
      --no-control-socket \
      --access-logfile - \
      'leave_burndown:create_app()'
  '';
in
{
  options.services.leave-burndown = {
    enable = lib.mkEnableOption "the leave burn-down web app";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "leave-burndown.packages.\${system}.default";
      description = "The leave-burndown package to run.";
    };

    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Address gunicorn binds to. Put a reverse proxy in front for anything but loopback.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 5050;
      description = "Port gunicorn listens on.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open {option}`port` in the firewall.";
    };

    workers = lib.mkOption {
      type = lib.types.ints.positive;
      default = 1;
      description = ''
        Gunicorn worker processes. The data lives in a single JSON file that is
        rewritten without locking, so keep this at 1 unless you add locking.
      '';
    };

    secretKeyFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      example = "/run/secrets/leave-burndown-key";
      description = ''
        File containing Flask's SECRET_KEY, read as a systemd credential so it
        can be root-only. When null the app makes a random key on each start,
        which is harmless here (it only signs flash messages) but not stable
        across restarts.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.leave-burndown = {
      description = "Leave burn-down";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      environment.LEAVE_DATA = "/var/lib/leave-burndown/leave_data.json";

      serviceConfig = {
        ExecStart = start;
        DynamicUser = true;
        StateDirectory = "leave-burndown";
        LoadCredential = lib.mkIf (cfg.secretKeyFile != null) "secret-key:${cfg.secretKeyFile}";
        Restart = "on-failure";

        # Hardening
        NoNewPrivileges = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        RestrictAddressFamilies = [
          "AF_INET"
          "AF_INET6"
          "AF_UNIX"
        ];
        RestrictNamespaces = true;
        RestrictRealtime = true;
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        SystemCallArchitectures = "native";
        CapabilityBoundingSet = "";
        UMask = "0077";
      };
    };

    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
  };
}
