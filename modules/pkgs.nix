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
      pkg-name = import ./_package_name.nix { };
    in
    {
      packages = {
        ${pkg-name} = mkApplication {
          inherit (self'.packages) venv;
          package = self'.packages._pkg;
        };

        default = self'.packages.${pkg-name};
      };

    };
}
