{
  self,
  moduleWithSystem,
  ...
}:
{
  flake =
    { config, ... }:
    {
      nixosModules.default = moduleWithSystem (
        perSystem@{ config }:
        nixos@{
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.services.nix-auto-push;
          pkg = perSystem.config.packages.default;
          serviceDesc = "Service to automatically push locally built derivations to a remote cache";
          inherit (lib)
            mkEnableOption
            mkOption
            mkIf
            types
            ;
          socketPath = "${cfg.dataDir}/${cfg.socketName}";
          queuePath = "${cfg.dataDir}/${cfg.queueName}";
          defaultNetworkCheckScriptName = "_nix-auto-push-network-check";
          defaultNetworkCheckScript = pkgs.writeShellApplication {
            name = defaultNetworkCheckScriptName;
            runtimeInputs = [
              pkgs.iputils
            ];
            text = ''
              ping -c 1 ${cfg.target}
            '';
          };
          defaultVerifyScriptName = "_nix-auto-push-pkg-check";
          defaultVerifyScript = pkgs.writeShellApplication {
            name = defaultVerifyScriptName;
            runtimeInputs = [
              pkgs.nix
            ];
            text = ''
              set -f
              nix-store --verify-path "$OUT_PATH"
            '';
          };

          defaultPushScriptName = "_nix-auto-push-push";
          defaultPushScript = pkgs.writeShellApplication {
            name = defaultPushScriptName;
            runtimeInputs = [
              pkgs.nix
              pkgs.openssh
            ];
            text = ''
              set -f
              set -euo pipefail

              nix-store --verify-path "$OUT_PATH"

              export NIX_SSHOPTS="${cfg.sshOpts}"

              nix copy --to "${cfg.targetCopy}" "$OUT_PATH"
            '';
          };
          postBuildHookName = "_nix-auto-push-post-build-hook";
          postBuildHook = pkgs.writeShellApplication {
            name = postBuildHookName;
            runtimeInputs = [
              pkg
              pkgs.nix
            ];
            text = ''
              # Always exit as if we passed, otherwise builds stop working
              # set -eu
              set +e
              set -f
              export IFS=' '
              echo "Pushing paths to upload queue $OUT_PATHS"
              nix-auto-push \
                --socket-path ${socketPath} \
                --verify-cmd ${cfg.verifyCmd} \
                --log-level ${cfg.logLevel} \
                "$OUT_PATHS"
              exit 0
            '';
          };
        in
        {
          options.services.nix-auto-push = {
            enable = mkEnableOption serviceDesc;

            target = mkOption {
              description = "Host/domain name of target machine";
              type = types.str;
            };
            targetUser = mkOption {
              description = "Username to login to on the target machine";
              type = types.str;
              default = cfg.serviceUser;
            };
            targetCopy = mkOption {
              description = ''
                Value to pass to the --to argument of nix copy
              '';
              type = types.str;
              default = "ssh://${cfg.targetUser}@${cfg.target}";
            };

            dataDir = mkOption {
              description = "Directory the daemon will store data in";
              type = types.str;
              default = "/var/nix-auto-pushd";
            };
            socketName = mkOption {
              description = "Name of ths socket file created by the daemon";
              type = types.str;
              default = "nix-auto-pushd.sock";
            };

            queueName = mkOption {
              description = "Name of sqlite job queue";
              type = types.str;
              default = "nix-auto-push.sqlite";
            };

            networkCheckCmd = mkOption {
              description = "Path to executable that checks if the target server can be reached";
              type = types.str;
              default = "${defaultNetworkCheckScript}/bin/${defaultNetworkCheckScriptName}";
            };

            verifyCmd = mkOption {
              description = ''
                Path to executable to verify that a particular store path is in the store and valid.
                The store path is passed in via the $OUT_PATH variable
              '';
              type = types.str;
              default = "${defaultVerifyScript}/bin/${defaultVerifyScriptName}";
            };

            pushCmd = mkOption {
              description = ''
                Path to executable to push a store path to the target server.
                The store path is passed in via the $OUT_PATH variable
              '';
              type = types.str;
              default = "${defaultPushScript}/bin/${defaultPushScriptName}";
            };

            sshOpts = mkOption {
              description = ''
                Options to pass as NIX_SSHOPTS in the pushCmd.
                Only used by the default pushCmd.
              '';
              type = types.coercedTo (types.listOf types.str) (from: lib.concatStringsSep " " from) types.str;
              default = [ ];
            };

            retryAttempts = mkOption {
              description = "Number of times daemon will reattempt pushing a failed path without a daemon restart";
              type = types.int;
              default = 5;
            };

            deleteAttempts = mkOption {
              description = "Total number of times daemon will ever attempt pushing a failed path";
              type = types.int;
              default = cfg.retryAttempts * 2;
            };

            logLevel = mkOption {
              description = "Log level";
              type = types.str;
              default = "info";
            };

            serviceUser = mkOption {
              description = "User to run the daemon under";
              type = types.str;
              default = "nix-auto-push";
            };
          };
          config = mkIf cfg.enable {
            # TODO: make this configurable?
            # TODO: figure out if user can supply SSH key to this user easily
            users.users.${cfg.serviceUser} = {
              group = cfg.serviceUser;
              isSystemUser = true;
              description = "nix-auto-pushd daemon user";
            };

            users.groups.${cfg.serviceUser} = { };
            systemd = {
              #sockets.nix-auto-pushd = {
              #  description = serviceDesc + " (socket)";

              #  wantedBy = [ "sockets.target" ];

              #  socketConfig = {
              #    ListenStream = socketPath;

              #    SocketUser = cfg.serviceUser;
              #    SocketGroup = cfg.serviceUser;
              #    SocketMode = "0660";

              #    DirectoryMode = "0755";
              #  };
              #};
              tmpfiles.rules = [
                "d ${cfg.dataDir} 0755 ${cfg.serviceUser} ${cfg.serviceUser} -"
              ];
              services.nix-auto-pushd = {
                description = serviceDesc;
                wantedBy = [ "multi-user.target" ];
                #requires = [ "nix-auto-pushd.socket" ];
                after = [
                  "network-online.target"
                  # "nix-auto-pushd.socket"
                ];
                wants = [ "network-online.target" ];

                serviceConfig = {
                  User = cfg.serviceUser;
                  Group = cfg.serviceUser;

                  ExecStart = ''
                    ${pkg}/bin/nix-auto-pushd \
                      --queue-path ${queuePath} \
                      --socket-path ${socketPath} \
                      --network-check-cmd ${cfg.networkCheckCmd} \
                      --retry-attempts ${builtins.toString cfg.retryAttempts} \
                      --delete-attempts ${builtins.toString cfg.deleteAttempts} \
                      --verify-cmd ${cfg.verifyCmd} \
                      --log-level ${cfg.logLevel} \
                      --cmd ${cfg.pushCmd}
                  '';
                };
              };
            };

            nix.settings.post-build-hook = "${postBuildHook}/bin/${postBuildHookName}";
          };
        }
      );

    };
}
