{
  hacks,
  python,
  pkgs,
  ...
}:
final: prev: {
  oldest-supported-numpy = hacks.nixpkgsPrebuilt {
    from = pkgs.pythonPackages.oldest-supported-numpy;
  };
  # Example overrides to fix build
  # psycopg2 = prev.psycopg2.overrideAttrs (old: {
  #   buildInputs = (old.buildInputs or [ ]) ++ [
  #     prev.setuptools
  #     pkgs.libpq.pg_config
  #   ];
  # });
  # casadi = hacks.nixpkgsPrebuilt {
  #   from = pkgs.python312Packages.casadi;
  #   prev = prev.casadi;
  # };

  ## TODO: Add tests to package?
  ## Based on https://pyproject-nix.github.io/uv2nix/patterns/testing.html
  ## Doesn't seem to work, nix-auto-push package isn't found
  #nix-auto-push = prev.nix-auto-push.overrideAttrs (old: {
  #  passthru = old.passthru // {
  #    tests =
  #      let
  #        _virtualenv = final.mkVirtualEnv "nix-auto-push-pytest-env" workspace.deps.all // {
  #          nix-auto-push = [ "dev" ];
  #        };
  #      in
  #      (old.tests or { })
  #      // {
  #        pytest = pkgs.stdenv.mkDerivation {
  #          name = "${final.nix-auto-push.name}-pytest";
  #          inherit (final.nix-auto-push) src;
  #          nativeBuildInputs = [
  #            virtualenv
  #            _virtualenv
  #          ];
  #          dontConfigure = true;
  #          buildPhase = ''
  #            runHook preBuild
  #            pytest
  #            runHook postBuild
  #          '';
  #        };
  #      };
  #  };
  #});

}
