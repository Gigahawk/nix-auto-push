{ inputs, ... }:
{
  perSystem =
    {
      self',
      pkgs,
      lib,
      ...
    }:
    let
      inherit (pkgs.callPackages inputs.pyproject-nix.build.util { }) mkApplication;
    in
    {
      packages = rec {
        nix-auto-push = mkApplication {
          inherit (self'.packages) venv;
          package = self'.packages._pkg;
        };

        default = nix-auto-push;
      };

    };
}
