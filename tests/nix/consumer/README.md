# Minimal consumer flake

Build sqlit from `github:lamalex/sqlit/hx` with only the PostgreSQL driver:

```sh
nix build path:./tests/nix/consumer --no-link -L
nix flake check path:./tests/nix/consumer -L
nix run path:./tests/nix/consumer -- --version
```

The consumer lock file pins the GitHub revision. Refresh it after pushing changes
to `hx`:

```sh
nix flake update sqlit --flake path:./tests/nix/consumer
```

To test local sqlit changes through the same consumer without changing its lock
file:

```sh
nix build path:./tests/nix/consumer --override-input sqlit path:. --no-write-lock-file --no-link -L
```

Run these commands from the repository root. The default sqlit package includes
all packaged driver extras; this consumer deliberately uses `makeSqlit` instead.
