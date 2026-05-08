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
      virtualenv = self'.packages.editableVenv;
    in
    {
      devShells = {
        default = pkgs.mkShell {
          packages = [
            virtualenv
            pkgs.uv
            pkgs.sphinx
            pkgs.git
          ];
          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = self'.packages.python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";
          }
          // lib.optionalAttrs pkgs.stdenv.isLinux {
            LD_LIBRARY_PATH = lib.makeLibraryPath pkgs.pythonManylinuxPackages.manylinux1;
          };

          shellHook = ''
            unset PYTHONPATH
            export REPO_ROOT=$(git rev-parse --show-toplevel)
            . ${virtualenv}/bin/activate
          '';

        };
        uv = pkgs.mkShell {
          pacakges = [
            pkgs.uv
          ];
        };
      };
    };
}
