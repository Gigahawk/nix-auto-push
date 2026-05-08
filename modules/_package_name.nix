{ ... }:
let
  pyproject = builtins.fromTOML (builtins.readFile ../pyproject.toml);
in
pyproject.project.name
