{
  inputs,
  ...
}:
{
  perSystem =
    {
      lib,
      pkgs,
      self',
      ...
    }:
    let
      pkg-name = import ./_package_name.nix { };
      inherit (self'.packages) python;
      hacks = pkgs.callPackage inputs.pyproject-nix.build.hacks { };
      workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ../.; };

      pyprojectOverlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };
      editableOverlay = workspace.mkEditablePyprojectOverlay {
        root = "$REPO_ROOT";
      };

      pyprojectOverrides = import ./_pyproject-overrides.nix {
        inherit python;
        inherit hacks;
        inherit pkgs;
      };

      pythonSet =
        (pkgs.callPackage inputs.pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              inputs.pyproject-build-systems.overlays.wheel
              pyprojectOverlay
              pyprojectOverrides
            ]
          );
      editablePythonSet = pythonSet.overrideScope editableOverlay;

    in
    {
      packages = {
        _pkg = pythonSet.${pkg-name};
        venv = pythonSet.mkVirtualEnv "${pkg-name}-env" workspace.deps.default;
        editableVenv = editablePythonSet.mkVirtualEnv "${pkg-name}-dev-env" workspace.deps.all;
      };
    };
}
