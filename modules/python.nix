{ ... }:
{
  perSystem =
    {
      pkgs,
      ...
    }:
    {
      packages.python = pkgs.python314;
    };
}
