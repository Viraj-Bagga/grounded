# 07-distribute

The distribution node. It gets the model and corpus packs onto a phone that has
no internet after install. A laptop or a Raspberry Pi on the clinic's local
network runs `server.py`, and phones pull packs from it and check every byte
against a sha256 before using anything. The node needs no internet either.
Stdlib Python only, 3.9 or later. No venv needed.

## Run it

```bash
python3 07-distribute/build_pack.py 07-distribute/specs/*.json   # build or re-check packs
python3 07-distribute/server.py                                  # node on 127.0.0.1:8790
python3 07-distribute/server.py --host 0.0.0.0                   # serve the local network

python3 07-distribute/client.py list
python3 07-distribute/client.py pull corpus-base --dest /path/to/installed
python3 07-distribute/client.py verify /path/to/installed/corpus-base/2026.09.15

python3 07-distribute/selftest.py        # 51 checks, temp dir, loopback, about 5 s
07-distribute/demo.sh /tmp/pulled        # the live demo; pulls 2.84 GB, delete after
```

## Packs

| id | version | contents | licence |
|---|---|---|---|
| `model-nemotron3-nano-4b-q4km` | `2026.09.15-base` | `model.gguf`, `LICENSE.txt`, `LICENSE.pdf` | NVIDIA Nemotron Open Model License, amber |
| `corpus-base` | `2026.09.15` | `citations.csv`, `corpus.db` | public domain (US government works), green |

A pack is `packs/<id>/<version>/manifest.json` plus a `files/` tree. The
manifest lists every file's `path`, `size` and `sha256`, and carries `version`,
`license`, a total `size` and `pack_sha256`. `packs/` is built output and is
gitignored. The specs in `specs/` are the source.

`pack_sha256` is the sha256 of the `shasum -a 256` listing of the files in byte
order of path, so it can be checked with no project code:

```bash
cd packs/corpus-base/2026.09.15/files && shasum -a 256 citations.csv corpus.db | shasum -a 256
```

**A version never changes.** Rebuilding identical content does nothing, and
different content under a built version is refused. To change a pack, bump its
version.

## Node API

| request | returns |
|---|---|
| `GET /packs` | every valid pack's manifest, plus `manifest_url` and a `url` per file |
| `GET /packs/<id>/<version>/manifest.json` | the manifest, byte for byte |
| `GET`/`HEAD /packs/<id>/<version>/files/<path>` | the file. Single `Range`, `If-Range`; `ETag` is its sha256 |
| anything else | 404 |

## Where each check happens

| check | builder | node | client |
|---|---|---|---|
| sha256 of every file | computes it from the snapshot | re-hashes before listing, and after any change | hashes from disk after download |
| model hash equals the one in build-log.md | pinned in the spec | | |
| paths cannot escape | refuses to build | serves listed paths only, inside the pack | refuses the manifest |
| registry licence green or amber (constraint 6) | refuses to build | | |
| index text equals the frozen chunks (constraint 1) | refuses to build | | |
| no key shared by two corpus packs (constraint 9) | refuses to build | | |
| licence file ships with the model (licence clause 3a) | refuses to build | | |
| pack digest pinned out of band | | | `--expect` |

## Adding a regional pack

Write a spec in `specs/` and run `build_pack.py`. Or drop in a pack directory
built anywhere else. The node lists it on its next request. Nothing in
`server.py` or `client.py` changes, and `selftest.py` T12 proves that.

A regional corpus pack keeps the file names `citations.csv` and `corpus.db`,
and its citation keys must not reuse any other corpus pack's.

## Limits

- **Integrity, not authenticity.** The hashes catch corruption in transit and
  on disk, but anyone who controls a node can rewrite a file and its manifest
  together. The fix is a signed manifest checked against a key built into the
  app. That needs Ed25519, which the stdlib doesn't have. Until then, `--expect`
  pins a digest the app ships with.
- **The phone side is not built.** `client.py` is the reference a React Native
  port must copy. It will also need iOS Local Network permission, an ATS
  exception for plain HTTP, and cleartext allowed on Android. None of that has
  been tested.
- **The query embedder ships in neither pack.** The corpus cannot be queried
  without all-MiniLM-L6-v2, and reading its vectors needs the sqlite-vec
  extension.
- **Downstream assumes a single corpus.** The scope floor and the citation
  registry both assume these 22 chunks.
- **Loopback MB/s measures the software, not Wi-Fi.**
