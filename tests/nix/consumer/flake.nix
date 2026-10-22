{
  description = "Minimal GitHub consumer build of sqlit with PostgreSQL only";

  inputs = {
    sqlit.url = "github:lamalex/sqlit/hx";
    nixpkgs.follows = "sqlit/nixpkgs";
    flake-utils.follows = "sqlit/flake-utils";
  };

  outputs = { sqlit, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        sqlitBin = sqlit.lib.${system}.makeSqlit {
          extras = [ "postgres" ];
        };
      in {
        packages.default = sqlitBin;
        checks.default = sqlitBin;
        apps.default = {
          type = "app";
          program = "${sqlitBin}/bin/sqlit";
        };
      });
}
